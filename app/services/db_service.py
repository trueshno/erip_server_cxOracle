# -*- coding: utf-8 -*-
import structlog
import secrets
import json
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import or_
from app.models import Transaction, Account, TransactionError
from app.db import SessionLocal

logger = structlog.get_logger()

def get_stored_response(request_id: str) -> Optional[str]:
    """Возвращает сохранённый XML из metadata_json (идемпотентность)"""
    db = SessionLocal()
    try:
        row = db.query(Transaction).filter(
            Transaction.erip_request_id == request_id
        ).first()  # type: ignore[call-arg]
        
        if row and row.metadata_json:
            try:
                meta_raw = row.metadata_json
                if meta_raw:
                    return json.loads(meta_raw).get("response_xml")
            except (json.JSONDecodeError, TypeError):
                logger.warning("json_parse_failed", request_id=request_id)
                return None
        return None
    except Exception as e:
        logger.error("db_query_error", error=str(e), request_id=request_id)
        return None
    finally:
        db.close()

def update_transaction_status(
    erip_trx_id: Optional[str], 
    service_trx_id: Optional[str], 
    status: str, 
    error_text: Optional[str] = None
) -> bool:
    """Обновляет статус транзакции. Параметры ID могут быть None."""
    db = SessionLocal()
    try:
        # Если оба ID None — ничего не делаем
        if not erip_trx_id and not service_trx_id:
            logger.warning("no_ids_provided_for_update")
            return False
            
        # Фильтр: ищем по любому из предоставленных ID
        filters = []
        if erip_trx_id:
            filters.append(Transaction.erip_transaction_id == erip_trx_id)
        if service_trx_id:
            filters.append(Transaction.service_trx_id == service_trx_id)
        
        trx = db.query(Transaction).filter(or_(*filters)).first() # type: ignore[call-arg]
        
        if not trx:
            logger.warning("transaction_not_found_for_update", 
                          erip_trx_id=erip_trx_id, service_trx_id=service_trx_id)
            return False
        
        trx.status = status
        trx.processed_at = datetime.now()
        if error_text:
            trx.error_text = error_text[:4000] if len(error_text) > 4000 else error_text
        
        db.commit()
        logger.info("transaction_status_updated", 
                   erip_trx_id=erip_trx_id, service_trx_id=service_trx_id, new_status=status)
        return True
    except Exception as e:
        db.rollback()
        logger.error("db_update_error", error=str(e), erip_trx_id=erip_trx_id)
        return False
    finally:
        db.close()

def get_account_info(personal_account: str) -> Optional[Dict[str, Any]]:
    """Получает данные счёта из таблицы accounts"""
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
            "min_amount": fmt(acc.min_amount),
            "max_amount": fmt(acc.max_amount),
            "surname": acc.holder_surname or "",
            "firstname": acc.holder_firstname or "",
            "patronymic": acc.holder_patronymic or "",
            "city": acc.city or "",
            "street": acc.street or "",
            "house": acc.house or "",
            "apartment": acc.apartment or ""
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

        # Собираем метаданные
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
            # ← Новые поля:
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