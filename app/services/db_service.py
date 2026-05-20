import structlog
import secrets
from datetime import datetime
from typing import Optional, Dict
from app.db import SessionLocal
from app.models import Transaction, Account

logger = structlog.get_logger()

def get_stored_response(request_id: str) -> Optional[str]:
    db = SessionLocal()
    try:
        row = db.query(Transaction).filter(Transaction.erip_request_id == request_id).first()
        # Fallback на metadata_json, если response_xml ещё не добавлен в БД
        return row.response_xml or row.metadata_json if row else None
    except Exception as e:
        logger.error("db_query_error", error=str(e), request_id=request_id)
        return None
    finally:
        db.close()

def get_account_info(personal_account: str) -> Optional[Dict]:
    db = SessionLocal()
    try:
        acc = db.query(Account).filter(Account.account_number == personal_account).first()
        if not acc:
            return None
        return {
            "debt": f"{acc.debt_amount:.2f}".replace(".", ","),
            "editable": acc.editable_flag,
            "min_amount": f"{acc.min_amount:.2f}".replace(".", ","),
            "max_amount": f"{acc.max_amount:.2f}".replace(".", ","),
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

def save_transaction(req_id: str, req_type: str, account: str, currency: str, 
                     amount_byn: float, erip_trx_id: str, response_xml: str,
                     terminal_id: str = "", terminal_type: int = 0, agent_code: int = 0, auth_type: str = "") -> Optional[str]:
    db = SessionLocal()
    try:
        # Генерация строго 8-значного ID (как согласовано)
        svc_trx_id = "".join([str(secrets.randbelow(10)) for _ in range(8)])
        
        trx = Transaction(
            erip_request_id=req_id,
            request_type=req_type,
            personal_account=account,
            currency=currency,
            amount=amount_byn,
            erip_transaction_id=erip_trx_id,
            service_trx_id=svc_trx_id,
            status="started" if req_type == "TransactionStart" else "success",
            created_at=datetime.now(),
            terminal_id=terminal_id,
            terminal_type=terminal_type,
            agent_code=agent_code,
            auth_type=auth_type
        )
        
        # Сохраняем XML. Пробуем response_xml, если нет fallback в metadata_json
        try:
            trx.response_xml = response_xml
        except Exception:
            trx.metadata_json = response_xml

        db.add(trx)
        db.commit()
        logger.info("transaction_saved", req_id=req_id, svc_trx_id=svc_trx_id)
        return svc_trx_id
    except Exception as e:
        db.rollback()
        logger.error("db_insert_error", error=str(e), req_id=req_id)
        return None
    finally:
        db.close()