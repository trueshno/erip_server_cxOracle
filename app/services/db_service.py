# -*- coding: utf-8 -*-
import structlog
import secrets
import json
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import or_, text
from app.models import Transaction, Account, TransactionError
from app.db import SessionLocal

ERROR_ACCOUNT_NOT_FOUND = "Заказ {account}. Информация для оплаты не найдена. Проверьте номер заказа. vagr.by"
ERROR_ZERO_DEBT = "Заказ {account}. Оплата при нулевой задолженности запрещена. vagr.by"
ERROR_ACCOUNT_LOCKED = "Оплата по счету {account} временно заблокирована. vagr.by"

logger = structlog.get_logger()

def get_stored_response(request_id: str, request_type: str) -> Optional[str]:
    """
    Возвращает сохранённый XML-ответ по паре (request_id, request_type).
    """
    if not request_id or not request_type:
        return None
        
    db = SessionLocal()
    try:
        row = db.query(Transaction).filter(
            Transaction.erip_request_id == request_id,
            Transaction.request_type == request_type
        ).first()  # type: ignore[call-arg]
        
        if row and row.metadata_json:
            try:
                meta = json.loads(row.metadata_json)
                return meta.get("response_xml")
            except (json.JSONDecodeError, TypeError):
                logger.warning("cache_parse_error", request_id=request_id, request_type=request_type)
                return None
        return None
    except Exception as e:
        logger.error("cache_query_error", error=str(e), request_id=request_id, request_type=request_type)
        return None
    finally:
        db.close()

def update_transaction_status(
    erip_trx_id: Optional[str], 
    service_trx_id: Optional[str], 
    status: str, 
    error_text: Optional[str] = None
) -> bool:
    """Обновляет статус и логирует ошибку в TRANSACTION_ERRORS при статусе failed"""
    db = SessionLocal()
    try:
        filters = []
        if erip_trx_id:
            filters.append(Transaction.erip_transaction_id == erip_trx_id)
        if service_trx_id:
            filters.append(Transaction.service_trx_id == service_trx_id)
            
        if not filters:
            logger.warning("no_ids_for_status_update")
            return False
            
        trx = db.query(Transaction).filter(or_(*filters)).first()  # type: ignore[call-arg]
        if not trx:
            logger.warning("transaction_not_found_for_update", erip_trx_id=erip_trx_id, service_trx_id=service_trx_id)
            return False
        
        # 1. Обновляем основную транзакцию
        trx.status = status
        trx.processed_at = datetime.now()
        if error_text:
            trx.error_text = error_text[:4000] if len(error_text) > 4000 else error_text
            
        # 2. 🔹 ЛОГИРОВАНИЕ ОШИБКИ В TRANSACTION_ERRORS
        if error_text and status == "failed":
            # 🔹 Добавили # type: ignore[call-arg] для Pylance
            error_record = TransactionError(
                transaction_id=trx.id,  # type: ignore[call-arg]
                error_stage="TransactionResult",  # type: ignore[call-arg]
                error_code=400,  # type: ignore[call-arg]
                error_text=error_text[:4000] if len(error_text) > 4000 else error_text,  # type: ignore[call-arg]
                created_at=datetime.now()  # type: ignore[call-arg]
            )
            db.add(error_record)
            logger.info("error_logged_to_db", transaction_id=trx.id, error=error_text[:50])
            
        db.commit()
        logger.info("transaction_status_updated", trx_id=trx.id, status=status)
        return True
    except Exception as e:
        db.rollback()
        logger.error("db_update_error", error=str(e), exc_info=True)
        return False
    finally:
        db.close()

def get_account_info_alex(personal_account: str) -> Optional[Dict[str, Any]]:
    """
    Получает данные счёта из рабочей схемы ALEX.
    Возвращает None или маркер ошибки {"_error": "текст"} для Примера 7.
    """
    db = SessionLocal()
    try:
        try:
            num_erip = int(personal_account.strip())
        except ValueError:
            logger.warning("invalid_num_erip_format", account=personal_account)
            return None
        
        # Проверяем наличие записей
        check_query = text("""
            SELECT COUNT(*)
            FROM ALEX.PAYMENTS
            WHERE NUM_ERIP = :num_erip
        """)
        count = db.execute(check_query, {"num_erip": num_erip}).scalar() or 0
        
        if count == 0:
            # 🔹 Формируем текст ошибки ПО СПЕЦИФИКАЦИИ (Пример 7 из PDF)
            error_msg = (
                f"Заказ {personal_account}. "
                f"Информация для оплаты не найдена. Проверьте номер заказа. "
                f"vagr.by"
            )
            logger.info("alex_account_not_found", num_erip=num_erip, error=error_msg)
            return {"_error": error_msg}
        
        # Считаем задолженность
        debt_query = text("""
            SELECT NVL(SUM(SUMMA), 0)
            FROM ALEX.PAYMENTS
            WHERE NUM_ERIP = :num_erip
        """)
        debt_val = db.execute(debt_query, {"num_erip": num_erip}).scalar() or 0

        # 🔹 ПРОВЕРКА НА НУЛЕВУЮ ЗАДОЛЖЕННОСТЬ
        if float(debt_val) <= 0:
            error_msg = ERROR_ZERO_DEBT.format(account=personal_account)
            logger.info("alex_zero_debt", num_erip=num_erip, error=error_msg)
            return {"_error": error_msg}    
        
        # Получаем адрес
        addr_query = text("""
            SELECT obj.PRIMADR
            FROM ALEX.PAYMENTS p
            JOIN ALEX.ORDEROBJ obj ON p.IDORDER = obj.IDORDER
            WHERE p.NUM_ERIP = :num_erip AND ROWNUM = 1
        """)
        addr_result = db.execute(addr_query, {"num_erip": num_erip}).fetchone()
        
        if not addr_result or not addr_result[0]:
            error_msg = (
                f"Заказ {personal_account}. "
                f"Информация для оплаты не найдена. Проверьте номер заказа. "
                f"vagr.by"
            )
            return {"_error": error_msg}
        
        def fmt(val: float) -> str:
            return f"{val:.2f}".replace(".", ",")
        
        street = addr_result[0].strip() if addr_result and addr_result[0] else ""
        
        return {
            "debt": fmt(float(debt_val)),
            "editable": "Y",
            "min_amount": "0,01",
            "max_amount": "100000,00",
            "surname": "Ф***в",
            "firstname": "Имя",
            "patronymic": "Отчество",
            "city": "",
            "street": street,
            "house": "",
            "apartment": ""
        }
        
    except Exception as e:
        logger.error("alex_db_error", error=str(e), personal_account=personal_account, exc_info=True)
        return None
    finally:
        db.close()

def save_transaction(
    req_id: str,
    req_type: str,
    account: str,
    currency: str,
    amount_byn: float,
    erip_trx_id: str,
    response_xml: str,
    terminal_id: str = "",
    terminal_type: str = "0",
    agent_code: int = 0,
    auth_type: str = "",
    svc_trx_id: Optional[str] = None
) -> Optional[str]:

    db = SessionLocal()
    try:
        if svc_trx_id is None:
            svc_trx_id = "".join([str(secrets.randbelow(10)) for _ in range(8)])

        metadata = {
            "request_type": req_type,
            "erip_trx_id": erip_trx_id,
            "terminal_id": terminal_id,
            "terminal_type": terminal_type,
            "agent_code": agent_code,
            "auth_type": auth_type,
            "response_xml": response_xml 
        }

        trx = Transaction(
            erip_request_id=req_id,  # type: ignore[call-arg]
            personal_account=account,  # type: ignore[call-arg]
            currency=currency,  # type: ignore[call-arg]
            amount=amount_byn,  # type: ignore[call-arg]
            transaction_id=(erip_trx_id[:32] if erip_trx_id else None),  # type: ignore[call-arg]
            service_trx_id=svc_trx_id,  # type: ignore[call-arg]
            status="started" if req_type == "TransactionStart" else "success",  # type: ignore[call-arg]
            created_at=datetime.now(),  # type: ignore[call-arg]
            auth_type=(auth_type[:50] if auth_type else None),  # type: ignore[call-arg]
            terminal_type=(terminal_type[:50] if terminal_type else None),  # type: ignore[call-arg]
            metadata_json=json.dumps(metadata, ensure_ascii=False),  # type: ignore[call-arg]
            request_type=req_type,  # type: ignore[call-arg]
            erip_transaction_id=erip_trx_id  # type: ignore[call-arg]
        )

        db.add(trx)
        db.commit()
        logger.info("transaction_saved", req_id=req_id, svc_trx_id=svc_trx_id)
        return svc_trx_id

    except Exception as e:
        db.rollback()
        logger.error("db_insert_error", error=str(e), req_id=req_id, exc_info=True)
        return None
    finally:
        db.close()