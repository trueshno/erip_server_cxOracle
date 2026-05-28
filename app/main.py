import os, re, secrets
os.environ.setdefault("LD_LIBRARY_PATH", "/usr/lib/oracle/12.2/client64/lib")

from fastapi import FastAPI, Response, Form, Request
import structlog
import xml.etree.ElementTree as ET
from app.services.db_service import get_stored_response, save_transaction, get_account_info
from app.services.xml_generator import build_serviceinfo_response, build_transactionstart_response, build_error_response

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(20),
    processors=[
        structlog.stdlib.filter_by_level, structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level, structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(), cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
app = FastAPI(title="ERIP Provider API", docs_url=None, redoc_url=None)


def _detect_xml_encoding(xml_input) -> str:
    """Определяет кодировку из XML-декларации или возвращает дефолт"""
    if isinstance(xml_input, bytes):
        snippet = xml_input[:200].decode("ascii", errors="ignore")
    else:
        snippet = xml_input[:200]
    
    match = re.search(r'encoding=["\']([^"\']+)["\']', snippet)
    return match.group(1) if match else "windows-1251"


def parse_xml(xml_input) -> dict:
    """
    Универсальный парсер: принимает bytes или str
    """
    encoding = _detect_xml_encoding(xml_input)
    
    # Декодируем если пришли байты
    if isinstance(xml_input, bytes):
        xml_str = xml_input.decode(encoding, errors="replace")
    elif isinstance(xml_input, str):
        xml_str = xml_input
    else:
        raise ValueError(f"Unexpected XML type: {type(xml_input)}")
    
    # Удаляем BOM если есть
    if xml_str.startswith('\ufeff'):
        xml_str = xml_str[1:]
    
    root = ET.fromstring(xml_str.strip())
    
    # Парсим базовые поля
    terminal_elem = root.find(".//Terminal")
    data = {
        "request_type": root.findtext("RequestType"),
        "request_id": root.findtext("RequestId"),
        "personal_account": root.findtext("PersonalAccount"),
        "currency": root.findtext("Currency"),
        "terminal_id": root.findtext("Terminal"),
        "terminal_type": terminal_elem.get("Type", "0") if terminal_elem is not None else "0"
    }
    
    # Парсим специфичные поля по типу запроса
    if data["request_type"] == "ServiceInfo":
        agent_el = root.find(".//ServiceInfo/Agent")
        data["agent"] = agent_el.text.strip() if agent_el is not None and agent_el.text else None
    elif data["request_type"] == "TransactionStart":
        amount_el = root.find(".//TransactionStart/Amount")
        amount_raw = amount_el.text.strip() if amount_el is not None and amount_el.text else "0"
        try:
            data["amount_byn"] = int(amount_raw) / 100.0
        except ValueError:
            data["amount_byn"] = 0.0
        data["erip_trx_id"] = root.findtext(".//TransactionStart/TransactionId")
        data["auth_type"] = root.findtext(".//TransactionStart/AuthorizationType")
    
    return data


@app.post("/", response_class=Response)
async def erip_endpoint(request: Request):
    form = await request.form()
    XML = form.get("XML")
    
    # === Обработка UploadFile (когда отправляют @файл) ===
    from starlette.datastructures import UploadFile
    
    xml_content: str = ""
    
    if isinstance(XML, UploadFile):
        # Читаем файл
        file_content = await XML.read()
        if isinstance(file_content, bytes):
            # Определяем кодировку из декларации или используем дефолт
            xml_content = file_content.decode("windows-1251", errors="replace")
        else:
            xml_content = str(file_content)
    elif isinstance(XML, bytes):
        xml_content = XML.decode("windows-1251", errors="replace")
    elif isinstance(XML, str):
        xml_content = XML
    else:
        logger.error("unexpected_xml_type", xml_type=type(XML).__name__)
        return Response(content=build_error_response("Missing or invalid XML"), media_type="text/xml; charset=windows-1251", status_code=200)
    
    if not xml_content.strip():
        return Response(content=build_error_response("Empty XML"), media_type="text/xml; charset=windows-1251", status_code=200)
    
    logger.info("request_received", xml_len=len(xml_content))
    
    # Парсим XML (теперь точно строка)
    try:
        data = parse_xml(xml_content)
    except Exception as e:
        logger.error("parse_error", error=str(e), xml_preview=xml_content[:150])
        return Response(content=build_error_response("Invalid XML"), media_type="text/xml; charset=windows-1251", status_code=200)

    req_id, req_type = data.get("request_id"), data.get("request_type")
    if not req_id or not req_type:
        return Response(content=build_error_response("Missing required fields"), media_type="text/xml; charset=windows-1251", status_code=200)

    # Идемпотентность
    stored = get_stored_response(req_id)
    if stored:
        logger.info("idempotent_hit", request_id=req_id)
        return Response(content=stored.encode("windows-1251"), media_type="text/xml; charset=windows-1251", status_code=200)

    try:
        if req_type == "ServiceInfo":
            acc = get_account_info(data["personal_account"])
            if not acc:
                return Response(content=build_error_response("Account not found"), media_type="text/xml; charset=windows-1251", status_code=200)
            resp_xml = build_serviceinfo_response(acc)
            save_transaction(
                req_id=req_id, req_type=req_type, account=data["personal_account"],
                currency=data["currency"], amount_byn=0.0, erip_trx_id="",
                response_xml=resp_xml.decode("windows-1251"),
                terminal_id=data.get("terminal_id", ""), terminal_type=data.get("terminal_type", "0"),
                agent_code=int(data.get("agent", 0) or 0)
            )
            return Response(content=resp_xml, media_type="text/xml; charset=windows-1251", status_code=200)
            # return Response(content=resp_xml, media_type="text/xml; charset=utf-8", status_code=200)

        elif req_type == "TransactionStart":
            svc_trx_id = "".join([str(secrets.randbelow(10)) for _ in range(8)])
            resp_xml = build_transactionstart_response(svc_trx_id)
            save_transaction(
                req_id=req_id, req_type=req_type, account=data["personal_account"],
                currency=data["currency"], amount_byn=data.get("amount_byn", 0.0),
                erip_trx_id=data.get("erip_trx_id", ""),
                response_xml=resp_xml.decode("windows-1251"),
                terminal_id=data.get("terminal_id", ""), terminal_type=data.get("terminal_type", "0"),
                agent_code=int(data.get("agent", 0) or 0), auth_type=data.get("auth_type", ""),
                svc_trx_id=svc_trx_id
            )
            return Response(content=resp_xml, media_type="text/xml; charset=windows-1251", status_code=200)
        else:
            return Response(content=build_error_response("Unsupported RequestType"), media_type="text/xml; charset=windows-1251", status_code=200)
    except Exception as e:
        logger.error("processing_error", error=str(e), req_type=req_type, exc_info=True)
        return Response(content=build_error_response("Internal error"), media_type="text/xml; charset=windows-1251", status_code=200)


@app.get("/health")
async def health():
    return {"status": "ok"}