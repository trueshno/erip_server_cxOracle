from fastapi import FastAPI, Response, Form, HTTPException
from fastapi.responses import PlainTextResponse
import structlog
from app.services.xml_parser import parse_erip_xml, get_request_type
from app.db import get_db

# Инициализация логгера
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(20), # INFO
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
app = FastAPI(title="ERIP Provider API", docs_url=None, redoc_url=None)

@app.post("/", response_class=Response)
async def erip_endpoint(XML: str = Form(...)):
    """
    Принимает multipart/form-data с полем XML.
    Декодирует из windows-1251, парсит, логирует.
    Возвращает заглушку в той же кодировке.
    """
    logger.info("request_received", form_field="XML")
 
    xml_bytes = XML.encode("windows-1251", errors="replace")
    root = parse_erip_xml(xml_bytes)
    if root is None:
        raise HTTPException(status_code=400, detail="Invalid XML or encoding")

    req_type = get_request_type(root)
    if req_type not in ("ServiceInfo", "TransactionStart", "TransactionResult", "StornStart", "StornResult"):
        logger.warn("unknown_request_type", type=req_type)
        raise HTTPException(status_code=400, detail="Unsupported RequestType")

    # Пока возвращаем минимальный валидный ответ-заглушку
    response_xml = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        f'  <RequestType>{req_type}</RequestType>\n'
        '  <Status>Accepted</Status>\n'
        '</ServiceProvider_Response>'
    )
    return Response(
        content=response_xml.encode("windows-1251"),
        media_type="text/xml; charset=windows-1251",
        status_code=200
    )

@app.get("/health")
async def health():
    return {"status": "ok"}