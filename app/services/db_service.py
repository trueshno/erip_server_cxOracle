# -*- coding: utf-8 -*-
import structlog
import secrets
import json
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import or_, text
from app.models import Transaction, Account, TransactionError
from app.db import SessionLocal

logger = structlog.get_logger()

def get_stored_response(request_id: str, request_type: str) -> Optional[str]:
    """
    Возвращает сохранённый XML-ответ по паре (request_id, request_type).
    Если не найдено — возвращает None.
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
            error_record = TransactionError(
                transaction_id=trx.id,
                error_stage="TransactionResult",
                error_code=400,  # Код ошибки (можно вынести в параметр или парсить из XML)
                error_text=error_text[:4000] if len(error_text) > 4000 else error_text,
                created_at=datetime.now()
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

def get_account_info(personal_account: str) -> Optional[Dict[str, Any]]:
    """Получаем данные счёта из таблицы accounts"""
    db = SessionLocal()
    try:
        acc = db.query(Account).filter(
            Account.account_number == personal_account
        ).first()  # type: ignore[call-arg]
        
        if not acc:
            return None
        
        # Форматируем числа с запятой (требование ЕРИП)
        def fmt(val: Optional[float]) -> str:
            return f"{val:.2f}".replace(".", ",") if val is not None else "0,00"
        
        return {
            "debt": fmt(acc.debt_amount),
            "editable": acc.editable_flag or "Y",
            # "min_amount": fmt(acc.min_amount),
            # "max_amount": fmt(acc.max_amount),
            # "surname": acc.holder_surname or "",
            # "firstname": acc.holder_firstname or "",
            # "patronymic": acc.holder_patronymic or "",
            # "city": acc.city or "",
            "street": acc.street or "",
            # "house": acc.house or "",
            # "apartment": acc.apartment or ""
        }
    except Exception as e:
        logger.error("db_account_query_error", error=str(e))
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
        # Генерация 8-значного ID, если не передан
        if svc_trx_id is None:
            svc_trx_id = "".join([str(secrets.randbelow(10)) for _ in range(8)])

        # Метаданные
        metadata = {
            "request_type": req_type,
            "erip_trx_id": erip_trx_id,
            "terminal_id": terminal_id,
            "terminal_type": terminal_type,
            "agent_code": agent_code,
            "auth_type": auth_type,
            "response_xml": response_xml 
        }

        # Объект модели
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

def get_account_info_alex(personal_account: str) -> Optional[Dict[str, Any]]:
    """
    Получает данные счёта из рабочей схемы ALEX.
    personal_account: NUM_ERIP из ALEX.PAYMENTS
    """
    db = SessionLocal()
    try:
        # Проверяем, что NUM_ERIP — число
        try:
            num_erip = int(personal_account.strip())
        except ValueError:
            logger.warning("invalid_num_erip_format", account=personal_account)
            return None
        
        # 1. Считаем задолженность: сумма SUMMA для данного NUM_ERIP
        debt_query = text("""
            SELECT NVL(SUM(SUMMA), 0)
            FROM ALEX.PAYMENTS
            WHERE NUM_ERIP = :num_erip
        """)
        debt_val = db.execute(debt_query, {"num_erip": num_erip}).scalar() or 0
        
        # 2. Получаем адрес: берём PRIMADR из первого найденного ORDEROBJ
        addr_query = text("""
            SELECT obj.PRIMADR
            FROM ALEX.PAYMENTS p
            JOIN ALEX.ORDEROBJ obj ON p.IDORDER = obj.IDORDER
            WHERE p.NUM_ERIP = :num_erip AND ROWNUM = 1
        """)
        addr_result = db.execute(addr_query, {"num_erip": num_erip}).fetchone()
        
        # 3. Формируем ответ
        def fmt(val: float) -> str:
            return f"{val:.2f}".replace(".", ",")
        
        # 🔹 Весь адрес из PRIMADR → в street, остальное пусто
        street = addr_result[0].strip() if addr_result and addr_result[0] else ""
        
        return {
            "debt": fmt(float(debt_val)),
            "editable": "Y",
            "street": street
        }
        
    except Exception as e:
        logger.error("alex_db_error", error=str(e), personal_account=personal_account, exc_info=True)
        return None
    finally:
        db.close()