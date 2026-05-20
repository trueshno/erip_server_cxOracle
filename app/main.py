import os
os.environ.setdefault("LD_LIBRARY_PATH", "/usr/lib/oracle/12.2/client64/lib")

from fastapi import FastAPI, Response, Form, HTTPException
import structlog
from app.services.xml_parser import parse_erip_xml
from app.services.db_service import get_stored_response, save_transaction, get_client_info
from app.services.xml_generator import (
    build_serviceinfo_response, 
    build_transactionstart_response, 
    build_error_response
)

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(20),
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
app = FastAPI(title="ERIP Provider API", docs_url=None, redoc_url=None)

@app.post("/", response_class=Response)
async def erip_endpoint(XML: str = Form(...)):
    logger.info("request_received", endpoint="/")
    
    # 1. Парсинг входящего XML
    try:
        xml_bytes = XML.encode("windows-1251", errors="replace")
        data = parse_erip_xml(xml_bytes)
    except Exception as e:
        logger.error("parse_failed", error=str(e))
        return Response(content=build_error_response("Invalid XML format"), media_type="text/xml; charset=windows-1251", status_code=200)

    if not data or not data.get("request_id"):
        return Response(content=build_error_response("Missing RequestId"), media_type="text/xml; charset=windows-1251", status_code=200)

    req_id = data["request_id"]
    req_type = data["request_type"]

    # 2. Идемпотентность: если ответ уже сохранён -> возвращаем его
    stored_resp = get_stored_response(req_id)
    if stored_resp:
        logger.info("idempotent_return", request_id=req_id)
        return Response(content=stored_resp.encode("windows-1251"), media_type="text/xml; charset=windows-1251", status_code=200)

    # 3. Маршрутизация по типу запроса
    try:
        if req_type == "ServiceInfo":
            client = get_client_info(data["personal_account"])
            if not client:
                return Response(content=build_error_response(f"Account {data['personal_account']} not found"), media_type="text/xml; charset=windows-1251", status_code=200)
            resp_xml_bytes = build_serviceinfo_response(client)
            save_transaction(req_id, data["personal_account"], data["currency"], 0.0, "", resp_xml_bytes.decode("windows-1251"))
            return Response(content=resp_xml_bytes, media_type="text/xml; charset=windows-1251", status_code=200)

        elif req_type == "TransactionStart":
            svc_trx_id = save_transaction(
                req_id=req_id,
                account=data["personal_account"],
                currency=data["currency"],
                amount_byn=data.get("amount_byn", 0.0),
                erip_trx_id=data.get("erip_trx_id", "0"),
                response_xml="", # Временная заглушка, обновим после генерации
                status="started"
            )
            if not svc_trx_id:
                return Response(content=build_error_response("DB save failed"), media_type="text/xml; charset=windows-1251", status_code=200)
            
            resp_xml_bytes = build_transactionstart_response(svc_trx_id)
            # Обновляем сохранённый ответ на финальный
            from app.db import SessionLocal
            from app.models import Transaction
            db = SessionLocal()
            try:
                db.query(Transaction).filter(Transaction.erip_request_id == req_id).update(
                    {"response_xml": resp_xml_bytes.decode("windows-1251")}
                )
                db.commit()
            finally:
                db.close()
            return Response(content=resp_xml_bytes, media_type="text/xml; charset=windows-1251", status_code=200)

        else:
            return Response(content=build_error_response(f"Unsupported RequestType: {req_type}"), media_type="text/xml; charset=windows-1251", status_code=200)

    except Exception as e:
        logger.error("processing_error", error=str(e), req_type=req_type)
        return Response(content=build_error_response("Internal processing error"), media_type="text/xml; charset=windows-1251", status_code=200)

@app.get("/health")
async def health():
    return {"status": "ok"}