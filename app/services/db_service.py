import structlog
import secrets
import json
from datetime import datetime
from typing import Optional, Dict, Any
from app.db import SessionLocal
from app.models import Transaction, Account

logger = structlog.get_logger()


def get_stored_response(request_id: str) -> Optional[str]:
    """Возвращает сохранённый XML из metadata_json (идемпотентность)"""
    db = SessionLocal()
    try:
        row = db.query(Transaction).filter(Transaction.erip_request_id == request_id).first()
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


def get_account_info(personal_account: str) -> Optional[Dict[str, Any]]:
    """Получает данные счёта из accounts"""
    db = SessionLocal()
    try:
        acc = db.query(Account).filter(Account.account_number == personal_account).first()
        if not acc:
            return None
        return {
            "debt": f"{acc.debt_amount:.2f}".replace(".", ",") if acc.debt_amount else "0,00",
            "editable": acc.editable_flag or "Y",
            "min_amount": f"{acc.min_amount:.2f}".replace(".", ",") if acc.min_amount else "0,01",
            "max_amount": f"{acc.max_amount:.2f}".replace(".", ",") if acc.max_amount else "100000,00",
            "surname": acc.holder_surname or "И***в",
            "firstname": acc.holder_firstname or "Иван",
            "patronymic": acc.holder_patronymic or "Иванович",
            "city": acc.city or "М***к",
            "street": acc.street or "П***а",
            "house": acc.house or "10",
            "apartment": acc.apartment or "100"
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
    """
    Сохраняет транзакцию в БД.
    Возвращает service_trx_id (8 цифр) при успехе, None при ошибке.
    """
    db = SessionLocal()
    try:
        # Генерация 8-значного ID
        if svc_trx_id is None:
            svc_trx_id = "".join([str(secrets.randbelow(10)) for _ in range(8)])

        metadata = {
            "request_type": req_type,
            "erip_trx_id": erip_trx_id,
            "terminal_id": terminal_id,
            "terminal_type": terminal_type,
            "agent_code": agent_code,
            "auth_type": auth_type,
            "response_xml": response_xml  # Для идемпотентности
        }

        # Объект модели.
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
            metadata_json=json.dumps(metadata, ensure_ascii=False)  # type: ignore[call-arg]
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