import os
os.environ.setdefault("LD_LIBRARY_PATH", "/usr/lib/oracle/12.2/client64/lib")
from fastapi import FastAPI, Response, Form, Request, UploadFile
import structlog
import xml.etree.ElementTree as ET
from typing import Optional
from app.services.db_service import get_stored_response, save_transaction, get_account_info
from app.services.xml_generator import build_serviceinfo_response, build_transactionstart_response, build_error_response

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(20),
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
app = FastAPI(title="ERIP Provider API", docs_url=None, redoc_url=None)

def parse_xml(xml_bytes: bytes) -> dict:
    root = ET.fromstring(xml_bytes.decode("windows-1251", errors="replace"))
    terminal_elem = root.find(".//Terminal")
    data = {
        "request_type": root.findtext("RequestType"),
        "request_id": root.findtext("RequestId"),
        "personal_account": root.findtext("PersonalAccount"),
        "currency": root.findtext("Currency"),
        "terminal_id": root.findtext("Terminal"),
        "terminal_type": terminal_elem.get("Type", "0") if terminal_elem is not None else "0"
    }
    if data["request_type"] == "ServiceInfo":
        data["agent"] = root.findtext(".//ServiceInfo/Agent")
    elif data["request_type"] == "TransactionStart":
        amount_raw = root.findtext(".//TransactionStart/Amount", "0")
        data["amount_byn"] = int(amount_raw) / 100.0
        data["erip_trx_id"] = root.findtext(".//TransactionStart/TransactionId")
        data["auth_type"] = root.findtext(".//TransactionStart/AuthorizationType")
    return data

@app.post("/", response_class=Response)
async def erip_endpoint(request: Request):
    form = await request.form()
    XML = form.get("XML")
    
    xml_content: Optional[str] = None
    
    if XML is not None and hasattr(XML, 'read'):
        content = await XML.read() if hasattr(XML, 'read') and callable(getattr(XML, 'read')) else XML.read()
        if isinstance(content, bytes):
            xml_content = content.decode("windows-1251", errors="replace")
        else:
            xml_content = str(content)
    elif isinstance(XML, bytes):
        xml_content = XML.decode("windows-1251", errors="replace")
    elif isinstance(XML, str):
        xml_content = XML
    
    if xml_content is None:
        logger.error("Missing or invalid XML in request")
        return Response(content=build_error_response("Missing XML"), media_type="text/xml; charset=windows-1251", status_code=200)
    
    logger.info("request_received")
    xml_bytes = xml_content.encode("windows-1251", errors="replace")
    
    try:
        data = parse_xml(xml_bytes)
    except Exception as e:
        logger.error("parse_error", error=str(e))
        return Response(content=build_error_response("Invalid XML"), media_type="text/xml; charset=windows-1251", status_code=200)

    req_id = data.get("request_id")
    req_type = data.get("request_type")
    if not req_id or not req_type:
        return Response(content=build_error_response("Missing required fields"), media_type="text/xml; charset=windows-1251", status_code=200)

    # 1. Идемпотентность
    stored = get_stored_response(req_id)
    if stored:
        logger.info("idempotent_hit", request_id=req_id)
        return Response(content=stored.encode("windows-1251"), media_type="text/xml; charset=windows-1251", status_code=200)

    # 2. Обработка по типу
    try:
        if req_type == "ServiceInfo":
            acc = get_account_info(data["personal_account"])
            if not acc:
                return Response(content=build_error_response("Account not found"), media_type="text/xml; charset=windows-1251", status_code=200)
            resp_xml = build_serviceinfo_response(acc)
            save_transaction(req_id, req_type, data["personal_account"], data["currency"], 0.0, "", resp_xml.decode("windows-1251"),
                             data.get("terminal_id", ""), int(data.get("terminal_type", 0)), int(data.get("agent", 0) or 0))
            return Response(content=resp_xml, media_type="text/xml; charset=windows-1251", status_code=200)

        elif req_type == "TransactionStart":
            resp_xml = build_transactionstart_response("00000000") # Временный ID
            svc_trx = save_transaction(req_id, req_type, data["personal_account"], data["currency"], data.get("amount_byn", 0.0),
                                       data.get("erip_trx_id", ""), resp_xml.decode("windows-1251"),
                                       data.get("terminal_id", ""), int(data.get("terminal_type", 0)), 
                                       int(data.get("agent", 0) or 0), data.get("auth_type", ""))
            if not svc_trx:
                return Response(content=build_error_response("DB save failed"), media_type="text/xml; charset=windows-1251", status_code=200)
            resp_xml = build_transactionstart_response(svc_trx)
            # Обновляем сохранённый XML на финальный
            from app.db import SessionLocal
            from app.models import Transaction
            db = SessionLocal()
            try:
                tx = db.query(Transaction).filter_by(erip_request_id=req_id).first()
                if tx is not None:
                    tx.response_xml = resp_xml.decode("windows-1251")
                    db.commit()
            finally:
                db.close()
            return Response(content=resp_xml, media_type="text/xml; charset=windows-1251", status_code=200)
        else:
            return Response(content=build_error_response("Unsupported RequestType"), media_type="text/xml; charset=windows-1251", status_code=200)
    except Exception as e:
        logger.error("processing_error", error=str(e))
        return Response(content=build_error_response("Internal error"), media_type="text/xml; charset=windows-1251", status_code=200)

@app.get("/health")
async def health():
    return {"status": "ok"}