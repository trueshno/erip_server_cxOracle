import structlog
from datetime import datetime
import secrets
from typing import Optional, Dict
from app.db import SessionLocal
from app.models import Transaction, MockClient

logger = structlog.get_logger()

def get_stored_response(request_id: str) -> Optional[str]:
    db = SessionLocal()
    try:
        row = db.query(Transaction).filter(Transaction.erip_request_id == request_id).first()
        return row.response_xml if row and row.response_xml else None
    except Exception as e:
        logger.error("db_query_error", error=str(e), request_id=request_id)
        return None
    finally:
        db.close()

def get_client_info(personal_account: str) -> Optional[Dict[str, str]]:
    db = SessionLocal()
    try:
        client = db.query(MockClient).filter(MockClient.personal_account == personal_account).first()
        if client:
            return {
                "debt": client.debt or "0,00",
                "surname": client.surname or "И***в",
                "firstname": client.firstname or "Иван",
                "patronymic": client.patronymic or "Иванович",
                "city": client.city or "М***к",
                "street": client.street or "П***а",
                "house": client.house or "10",
                "apartment": client.apartment or "100"
            }
        return None
    except Exception as e:
        logger.error("mock_db_query_error", error=str(e))
        return None
    finally:
        db.close()

def save_transaction(
    req_id: str, account: str, currency: str, amount_byn: float,
    erip_trx_id: str, response_xml: str, status: str = "pending"
) -> Optional[str]:
    db = SessionLocal()
    try:
        # Генерация строго 8-значного номера провайдера
        svc_trx_id = "".join([str(secrets.randbelow(10)) for _ in range(8)])
        
        trx = Transaction(
            erip_request_id=req_id,
            personal_account=account,
            currency=currency,
            amount=amount_byn,
            erip_transaction_id=erip_trx_id,
            service_trx_id=svc_trx_id,
            status=status,
            created_at=datetime.now(),
            response_xml=response_xml
        )
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