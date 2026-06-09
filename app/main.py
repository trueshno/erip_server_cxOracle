# -*- coding: utf-8 -*-
import os, re, secrets, json
os.environ.setdefault("NLS_LANG", "RUSSIAN_RUSSIA.CL8MSWIN1251")
os.environ.setdefault("LD_LIBRARY_PATH", "/usr/lib/oracle/12.2/client64/lib")

from fastapi import FastAPI, Response, Request
from starlette.middleware.base import BaseHTTPMiddleware
import structlog
import xml.etree.ElementTree as ET
from starlette.datastructures import UploadFile

from app.logging_config import setup_logging
from app.services.db_service import (
    get_stored_response, save_transaction, get_account_info, update_transaction_status
)
from app.services.xml_generator import (
    build_serviceinfo_response, build_transactionstart_response, 
    build_error_response, build_transactionresult_response
)

setup_logging(level="DEBUG")  # Изменить на INFO для продакшена
logger = structlog.get_logger()

app = FastAPI(title="ERIP Provider API", docs_url=None, redoc_url=None)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True
    )
    return Response(
        content='<?xml version="1.0" encoding="windows-1251"?>\n'
                '<ServiceProvider_Response>\n'
                '  <Error>\n'
                '    <ErrorLine>Внутренняя ошибка сервера</ErrorLine>\n'
                '  </Error>\n'
                '</ServiceProvider_Response>',
        media_type="text/xml; charset=windows-1251",
        status_code=200
    )

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        import time
        start = time.time()
        response = await call_next(request)
        duration = round((time.time() - start) * 1000, 2)
        logger.info(
            "request_processed",
            method=request.method,
            url=str(request.url).split("?")[0],
            status_code=response.status_code,
            duration_ms=duration
        )
        return response

app.add_middleware(RequestLoggingMiddleware)

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
    Универсальный парсер: принимает bytes или str.
    Возвращает dict с распарсенными данными.
    """
    import xml.etree.ElementTree as ET
    
    encoding = _detect_xml_encoding(xml_input)
    
    if isinstance(xml_input, bytes):
        xml_str = xml_input.decode(encoding, errors="replace")
    elif isinstance(xml_input, str):
        xml_str = xml_input
    else:
        raise ValueError(f"Unexpected XML type: {type(xml_input)}")
    
    if xml_str.startswith('\ufeff'):
        xml_str = xml_str[1:]
    
    root = ET.fromstring(xml_str.strip())
    terminal_elem = root.find(".//Terminal")
    
    data = {
        "request_type": root.findtext("RequestType"),
        "request_id": root.findtext("RequestId"),
        "personal_account": root.findtext("PersonalAccount"),
        "currency": root.findtext("Currency"),
        "terminal_id": root.findtext("Terminal"),
        "terminal_type": terminal_elem.get("Type", "0") if terminal_elem is not None else "0"
    }
    
    req_type = data["request_type"]
    
    # Парсинг специфичных полей по типу запроса
    if req_type == "ServiceInfo":
        agent_el = root.find(".//ServiceInfo/Agent")
        data["agent"] = agent_el.text.strip() if (agent_el is not None and agent_el.text) else None
        
    elif req_type == "TransactionStart":
        amount_el = root.find(".//TransactionStart/Amount")
        amount_raw = amount_el.text.strip() if (amount_el is not None and amount_el.text) else "0"
        try:
            data["amount_byn"] = int(amount_raw) / 100.0
        except ValueError:
            data["amount_byn"] = 0.0
        data["erip_trx_id"] = root.findtext(".//TransactionStart/TransactionId")
        data["auth_type"] = root.findtext(".//TransactionStart/AuthorizationType")
        
    elif req_type == "TransactionResult":
        data["erip_trx_id"] = root.findtext(".//TransactionResult/TransactionId")
        data["service_trx_id"] = root.findtext(".//TransactionResult/ServiceProvider_TrxId")
        error_text_el = root.find(".//TransactionResult/ErrorText")
        data["error_text"] = error_text_el.text.strip() if (error_text_el is not None and error_text_el.text) else None
        
    elif req_type == "StornStart":
        data["erip_trx_id"] = root.findtext(".//StornStart/TransactionId")
        data["service_trx_id"] = root.findtext(".//StornStart/ServiceProvider_TrxId")
        amount_el = root.find(".//StornStart/Amount")
        data["amount_raw"] = amount_el.text.strip() if (amount_el is not None and amount_el.text) else "0"
        
    elif req_type == "StornResult":
        data["erip_trx_id"] = root.findtext(".//StornResult/TransactionId")
        data["service_trx_id"] = root.findtext(".//StornResult/ServiceProvider_TrxId")
        amount_el = root.find(".//StornResult/Amount")
        data["amount_raw"] = amount_el.text.strip() if (amount_el is not None and amount_el.text) else "0"
        storned_el = root.find(".//StornResult/Storned")
        data["storned"] = storned_el.text.strip() if (storned_el is not None and storned_el.text) else None
    
    return data 

@app.post("/", response_class=Response)
async def erip_endpoint(request: Request):
    """Обработчик всех входящих запросов ЕРИП"""
    form = await request.form()
    XML = form.get("XML")
    
    xml_content: str = ""
    
    if isinstance(XML, UploadFile):
        file_content = await XML.read()
        if isinstance(file_content, bytes):
            xml_content = file_content.decode("windows-1251", errors="replace")
        else:
            xml_content = str(file_content)
    elif isinstance(XML, bytes):
        xml_content = XML.decode("windows-1251", errors="replace")
    elif isinstance(XML, str):
        xml_content = XML
    else:
        logger.error("unexpected_xml_type", xml_type=type(XML).__name__)
        return Response(content=build_error_response("Missing or invalid XML"), 
                       media_type="text/xml; charset=windows-1251", status_code=200)
    
    if not xml_content.strip():
        return Response(content=build_error_response("Empty XML"), 
                       media_type="text/xml; charset=windows-1251", status_code=200)
    
    logger.info("request_received", xml_len=len(xml_content))
    
    try:
        data = parse_xml(xml_content)
    except Exception as e:
        logger.error("parse_error", error=str(e), xml_preview=xml_content[:150])
        return Response(content=build_error_response("Invalid XML"), 
                       media_type="text/xml; charset=windows-1251", status_code=200)

    req_id = data.get("request_id")
    req_type = data.get("request_type")
    
    if not req_id or not req_type:
        return Response(content=build_error_response("Missing required fields"), 
                       media_type="text/xml; charset=windows-1251", status_code=200)

    stored = get_stored_response(req_id)
    if stored:
        logger.info("idempotent_hit", request_id=req_id)
        return Response(content=stored.encode("windows-1251"), 
                       media_type="text/xml; charset=windows-1251", status_code=200)

    try:
        if req_type == "ServiceInfo":
            acc = get_account_info(data["personal_account"])
            if not acc:
                return Response(content=build_error_response("Account not found"), 
                               media_type="text/xml; charset=windows-1251", status_code=200)
            resp_xml = build_serviceinfo_response(acc)
            save_transaction(
                req_id=req_id, req_type=req_type, account=data["personal_account"],
                currency=data["currency"], amount_byn=0.0, erip_trx_id="",
                response_xml=resp_xml.decode("windows-1251", errors="replace"),
                terminal_id=data.get("terminal_id", ""), 
                terminal_type=data.get("terminal_type", "0"),
                agent_code=int(data.get("agent", 0) or 0)
            )
            return Response(content=resp_xml, 
                           media_type="text/xml; charset=windows-1251", status_code=200)

        elif req_type == "TransactionStart":
            svc_trx_id = "".join([str(secrets.randbelow(10)) for _ in range(8)])
            resp_xml = build_transactionstart_response(svc_trx_id)
            save_transaction(
                req_id=req_id, req_type=req_type, account=data["personal_account"],
                currency=data["currency"], amount_byn=data.get("amount_byn", 0.0),
                erip_trx_id=data.get("erip_trx_id", ""),
                response_xml=resp_xml.decode("windows-1251", errors="replace"),
                terminal_id=data.get("terminal_id", ""), 
                terminal_type=data.get("terminal_type", "0"),
                agent_code=int(data.get("agent", 0) or 0), 
                auth_type=data.get("auth_type", ""),
                svc_trx_id=svc_trx_id
            )
            return Response(content=resp_xml, 
                           media_type="text/xml; charset=windows-1251", status_code=200)

        elif req_type == "TransactionResult":
            erip_trx_id = data.get("erip_trx_id") or ""
            service_trx_id = data.get("service_trx_id") or ""
            error_text = data.get("error_text")
            
            if error_text:
                status = "failed"
                resp_xml = build_transactionresult_response(False)  # "Оплата аннулирована!"
                logger.info("transaction_result_with_error", request_id=req_id, error=error_text[:100])
            else:
                status = "success"
                resp_xml = build_transactionresult_response(True)  # "Задолженность оплачена"
                logger.info("transaction_result_success", request_id=req_id)
            
            update_transaction_status(erip_trx_id, service_trx_id, status, error_text)
            
            return Response(content=resp_xml, 
                           media_type="text/xml; charset=windows-1251", status_code=200)

        elif req_type == "StornStart":
            erip_trx_id = data.get("erip_trx_id") or ""
            service_trx_id = data.get("service_trx_id") or ""
            amount_raw = data.get("amount_raw", "0")
            
            logger.info("storn_start_received", 
                       request_id=req_id,
                       erip_trx_id=erip_trx_id,
                       service_trx_id=service_trx_id,
                       amount=amount_raw)
            
            xml = '<?xml version="1.0" encoding="windows-1251"?>\n<ServiceProvider_Response></ServiceProvider_Response>\n'
            return Response(content=xml.encode("windows-1251"), 
                           media_type="text/xml; charset=windows-1251", status_code=200)
     
        elif req_type == "StornResult":
            # Извлекаем данные из запроса
            erip_trx_id = data.get("erip_trx_id") or ""
            service_trx_id = data.get("service_trx_id") or ""
            storned = data.get("storned")  # "Y" = успешно, "N" = не удалось
            
            # Обновляем статус транзакции в БД
            if storned == "Y":
                update_transaction_status(erip_trx_id, service_trx_id, "storned")
                logger.info("storn_confirmed", 
                           request_id=req_id,
                           erip_trx_id=erip_trx_id,
                           service_trx_id=service_trx_id)
            elif storned == "N":
                update_transaction_status(erip_trx_id, service_trx_id, "storn_failed")
                logger.warning("storn_failed", 
                              request_id=req_id,
                              erip_trx_id=erip_trx_id,
                              service_trx_id=service_trx_id)
            else:
                logger.warning("storned_value_unknown", 
                              request_id=req_id,
                              storned=storned)
            
            # Даже если транзакция не найдена — ответ должен быть пустым положительным
            xml = (
                '<?xml version="1.0" encoding="windows-1251"?>\n'
                '<ServiceProvider_Response></ServiceProvider_Response>\n'
            )
            return Response(
                content=xml.encode("windows-1251"), 
                media_type="text/xml; charset=windows-1251", 
                status_code=200
            )        

        else:
            return Response(content=build_error_response("Unsupported RequestType"), 
                           media_type="text/xml; charset=windows-1251", status_code=200)                           

    except Exception as e:
        logger.error("processing_error", error=str(e), req_type=req_type, exc_info=True)
        return Response(content=build_error_response("Internal error"), 
                       media_type="text/xml; charset=windows-1251", status_code=200)
    

@app.get("/health")
async def health():
    return {"status": "ok"}