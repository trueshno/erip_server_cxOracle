# -*- coding: utf-8 -*-
import os, re, secrets, json
os.environ.setdefault("NLS_LANG", "RUSSIAN_RUSSIA.CL8MSWIN1251")
os.environ.setdefault("LD_LIBRARY_PATH", "/usr/lib/oracle/12.2/client64/lib")

from fastapi import FastAPI, Response, Request
from starlette.middleware.base import BaseHTTPMiddleware
import structlog
from sqlalchemy import text
import xml.etree.ElementTree as ET
from starlette.datastructures import UploadFile
from datetime import datetime

from app.logging_config import setup_logging
from app.db import get_db_session
from app.services.db_service import (
    get_stored_response, save_transaction, update_transaction_status,
    get_account_info_alex, record_payment_in_alex, storn_payment_in_alex,
    ERROR_ACCOUNT_NOT_FOUND, ERROR_ZERO_DEBT, ERROR_ACCOUNT_LOCKED,
    ERROR_INVALID_FORMAT
)
from app.services.xml_generator import (
    build_serviceinfo_response, build_transactionstart_response,
    build_error_response, build_transactionresult_response
)

setup_logging(level="DEBUG")  # Изменить на INFO для продакшена
logger = structlog.get_logger()
audit_logger = structlog.get_logger("audit")

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
                '    <ErrorLine>Сервер vagr.by временно недоступен. Повторите платеж позже.</ErrorLine>\n'
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

    # Формат номер/год
    personal_account_raw = root.findtext("PersonalAccount") or ""

    if "/" in personal_account_raw:
        parts = personal_account_raw.split("/")
        personal_account = parts[0].strip()
        year_suffix = parts[1].strip()
        order_year = f"20{year_suffix}" if len(year_suffix) == 2 else year_suffix
    else:
        personal_account = personal_account_raw.strip()
        order_year = None

    data = {
        "request_type": root.findtext("RequestType"),
        "request_id": root.findtext("RequestId"),
        "personal_account": personal_account,
        "order_year": order_year,
        "currency": root.findtext("Currency"),
        "terminal_id": root.findtext("Terminal"),
        "terminal_type": terminal_elem.get("Type", "0") if terminal_elem is not None else "0",
        "datetime": root.findtext("DateTime"),
        "service_no": root.findtext("ServiceNo"),
        "service_id": root.findtext("ServiceId"),
        "agent": None,
        "amount_byn": 0.0,
        "erip_trx_id": None,
        "auth_type": None,
        "service_trx_id": None,
        "error_text": None,
        "amount_raw": "0",
        "storned": None,
    }

    req_type = data["request_type"]

    if req_type == "ServiceInfo":
        agent_el = root.find(".//ServiceInfo/Agent")
        data["agent"] = agent_el.text.strip() if (agent_el is not None and agent_el.text) else None

    elif req_type == "TransactionStart":
        amount_el = root.find(".//TransactionStart/Amount")
        amount_raw = amount_el.text.strip() if (amount_el is not None and amount_el.text) else "0"
        try:
            amount_clean = amount_raw.replace(",", ".")
            data["amount_byn"] = float(amount_clean)
        except ValueError:
            logger.warning("invalid_amount_format", amount_raw=amount_raw)
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
        amount_raw = amount_el.text.strip() if (amount_el is not None and amount_el.text) else "0"
        try:
            data["amount_raw"] = float(amount_raw.replace(",", "."))
        except ValueError:
            data["amount_raw"] = "0"

    elif req_type == "StornResult":
        data["erip_trx_id"] = root.findtext(".//StornResult/TransactionId")
        data["service_trx_id"] = root.findtext(".//StornResult/ServiceProvider_TrxId")
        amount_el = root.find(".//StornResult/Amount")
        amount_raw = amount_el.text.strip() if (amount_el is not None and amount_el.text) else "0"
        try:
            data["amount_raw"] = float(amount_raw.replace(",", "."))
        except ValueError:
            data["amount_raw"] = "0"

        storned_el = root.find(".//StornResult/Storned")
        data["storned"] = storned_el.text.strip() if (storned_el is not None and storned_el.text) else None

    return data


@app.post("/healthcheck", response_class=Response)
async def erip_endpoint(request: Request):
    # Обработчик всех входящих запросов ЕРИП
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
    service_no = str(data.get("service_no") or "200")

    # Аудит входящего запроса
    logger.info(
        "erip_request_audit",
        request_id=req_id,
        request_type=req_type,
        service_no=service_no,
        service_id=data.get("service_id"),
        personal_account=data.get("personal_account"),
        order_year=data.get("order_year"),
        terminal_id=data.get("terminal_id"),
        terminal_type=data.get("terminal_type"),
        currency=data.get("currency"),
        agent=data.get("agent"),
        erip_trx_id=data.get("erip_trx_id")
    )

    if not req_id or not req_type:
        return Response(content=build_error_response("Missing required fields"),
                       media_type="text/xml; charset=windows-1251", status_code=200)

    # Проверка формата номера заказа (только для ServiceInfo и TransactionStart)
    if req_type in ("ServiceInfo", "TransactionStart"):
        personal_account = data.get("personal_account", "")
        order_year = data.get("order_year")

        if (not personal_account.isdigit() or len(personal_account) < 2 or
                not order_year or not order_year.isdigit() or len(order_year) != 4):
            logger.warning("invalid_format", personal_account=personal_account, order_year=order_year)
            return Response(
                content=build_error_response(ERROR_INVALID_FORMAT),
                media_type="text/xml; charset=windows-1251",
                status_code=200
            )

    # ============================================================
    # 🔹 ОТКРЫВАЕМ ОДНУ СЕССИЮ БД НА ВЕСЬ ЗАПРОС (маршрутизация по service_no)
    # ============================================================
    db = get_db_session(service_no)

    try:
        # Проверка идемпотентности
        stored = get_stored_response(db, req_id, req_type)
        if stored:
            logger.info("idempotent_hit", request_id=req_id, request_type=req_type, service_no=service_no)
            return Response(
                content=stored.encode("windows-1251"),
                media_type="text/xml; charset=windows-1251",
                status_code=200
            )

        # ============================================================
        # ServiceInfo
        # ============================================================
        if req_type == "ServiceInfo":
            audit_logger.info(
                "AUDIT_SERVICE_INFO_RECEIVED",
                request_id=req_id,
                datetime=data.get("datetime"),
                service_no=service_no,
                personal_account=data.get("personal_account"),
                order_year=data.get("order_year"),
                currency=data.get("currency"),
                terminal_id=data.get("terminal_id"),
                terminal_type=data.get("terminal_type"),
                agent=data.get("agent")
            )

            order_year = data.get("order_year")
            acc = get_account_info_alex(db, data["personal_account"], order_year)

            if acc is None or (isinstance(acc, dict) and acc.get("_error")):
                error_msg = str(acc["_error"]) if (acc and "_error" in acc) else "Лицевой счет не найден"
                logger.info("service_info_error", request_id=req_id, error=error_msg[:100])
                return Response(
                    content=build_error_response(error_msg),
                    media_type="text/xml; charset=windows-1251",
                    status_code=200
                )

            resp_xml = build_serviceinfo_response(acc)

            save_transaction(
                db=db,
                req_id=req_id, req_type=req_type, account=data["personal_account"],
                currency=data["currency"], amount_byn=0.0, erip_trx_id="",
                response_xml=resp_xml.decode("windows-1251", errors="replace"),
                terminal_id=data.get("terminal_id", ""),
                terminal_type=data.get("terminal_type", "0"),
                agent_code=int(data.get("agent", 0) or 0),
                order_year=order_year,
                idorder=acc.get("idorder")
            )

            return Response(content=resp_xml, media_type="text/xml; charset=windows-1251", status_code=200)

        # ============================================================
        # TransactionStart
        # ============================================================
        elif req_type == "TransactionStart":
            audit_logger.info(
                "AUDIT_TRANSACTION_START_RECEIVED",
                request_id=req_id,
                datetime=data.get("datetime"),
                service_no=service_no,
                service_id=data.get("service_id"),
                personal_account=data.get("personal_account"),
                order_year=data.get("order_year"),
                currency=data.get("currency"),
                terminal_id=data.get("terminal_id"),
                terminal_type=data.get("terminal_type"),
                amount_byn=data.get("amount_byn"),
                erip_trx_id=data.get("erip_trx_id"),
                auth_type=data.get("auth_type")
            )

            order_year = data.get("order_year")
            acc = get_account_info_alex(db, data["personal_account"], order_year)

            if acc is None or (isinstance(acc, dict) and acc.get("_error")):
                error_msg = str(acc["_error"]) if (acc and "_error" in acc) else "Лицевой счет не найден"
                logger.info("transaction_start_error", request_id=req_id, error=error_msg[:100])
                return Response(
                    content=build_error_response(error_msg),
                    media_type="text/xml; charset=windows-1251",
                    status_code=200
                )

            # Проверка суммы
            debt_float = float(acc.get("debt", "0").replace(",", "."))
            amount_byn = data.get("amount_byn", 0.0)

            if amount_byn > debt_float:
                error_msg = (
                    f"Сумма платежа превышает задолженность. "
                    f"Сумма платежа максимум {acc['debt']} BYN. "
                    f"Изменение суммы операции запрещено"
                )
                logger.warning("amount_exceeds_debt", amount=amount_byn, debt=debt_float)
                return Response(
                    content=build_error_response(error_msg),
                    media_type="text/xml; charset=windows-1251",
                    status_code=200
                )

            if amount_byn <= 0:
                error_msg = "Сумма платежа минимум 0,01 BYN. Скорректируйте сумму и повторите платеж"
                logger.warning("zero_or_negative_amount", amount=amount_byn)
                return Response(
                    content=build_error_response(error_msg),
                    media_type="text/xml; charset=windows-1251",
                    status_code=200
                )

            idorder = acc.get("idorder")
            logger.info("transaction_start_idorder",
                       idorder=idorder,
                       order_year=order_year,
                       personal_account=data["personal_account"])

            # 🔹 Проверка блокировки одновременной оплаты (логика 15 минут)
            lock_query = text("""
                SELECT id, created_at
                FROM transactions
                WHERE personal_account = :acc
                  AND status = 'started'
            """)
            active_trx = db.execute(lock_query, {"acc": data["personal_account"]}).fetchone()

            if active_trx:
                trx_id, created_at = active_trx
                minutes_passed = (datetime.now() - created_at).total_seconds() / 60 if created_at else 0

                if minutes_passed <= 15:
                    # < 15 мин — инфо-сообщение
                    error_msg = f"Платеж по заказу {data['personal_account']} уже обрабатывается. Повторите позже."
                else:
                    # > 15 мин — помечаем старую как timeout и даем ошибку
                    db.execute(text("UPDATE transactions SET status = 'timeout' WHERE id = :id"), {"id": trx_id})
                    db.commit()
                    error_msg = "Превышено время выполнения оплаты. Повторите платеж"

                logger.warning("account_locked", account=data["personal_account"], minutes=minutes_passed)
                return Response(
                    content=build_error_response(error_msg),
                    media_type="text/xml; charset=windows-1251",
                    status_code=200
                )

            svc_trx_id = str(secrets.randbelow(90000000) + 10000000)
            resp_xml = build_transactionstart_response(svc_trx_id)

            save_transaction(
                db=db,
                req_id=req_id, req_type=req_type, account=data["personal_account"],
                currency=data["currency"], amount_byn=amount_byn,
                erip_trx_id=data.get("erip_trx_id", ""),
                response_xml=resp_xml.decode("windows-1251", errors="replace"),
                terminal_id=data.get("terminal_id", ""),
                terminal_type=data.get("terminal_type", "0"),
                agent_code=int(data.get("agent", 0) or 0),
                auth_type=data.get("auth_type", ""),
                svc_trx_id=svc_trx_id,
                order_year=order_year,
                idorder=idorder
            )

            return Response(content=resp_xml,
                           media_type="text/xml; charset=windows-1251", status_code=200)

        # ============================================================
        # TransactionResult
        # ============================================================
        elif req_type == "TransactionResult":
            audit_logger.info(
                "AUDIT_TRANSACTION_RESULT_RECEIVED",
                request_id=req_id,
                datetime=data.get("datetime"),
                service_no=service_no,
                service_id=data.get("service_id"),
                personal_account=data.get("personal_account"),
                order_year=data.get("order_year"),
                currency=data.get("currency"),
                terminal_id=data.get("terminal_id"),
                terminal_type=data.get("terminal_type"),
                erip_trx_id=data.get("erip_trx_id"),
                service_trx_id=data.get("service_trx_id"),
                error_text=data.get("error_text")
            )

            erip_trx_id = data.get("erip_trx_id") or ""
            service_trx_id = data.get("service_trx_id") or ""
            error_text = data.get("error_text")

            if error_text:
                status = "failed"
                resp_xml = build_transactionresult_response(success=False)
            else:
                status = "success"
                payment_date = datetime.now().strftime("%d.%m.%Y")
                resp_xml = build_transactionresult_response(
                    success=True,
                    order_number=data["personal_account"],
                    payment_date=payment_date
                )

                logger.info("transaction_result_success", request_id=req_id)

                # 🔹 Ищем транзакцию и записываем платёж в ALEX
                trx = db.execute(
                    text("SELECT personal_account, amount, order_year, idorder "
                         "FROM transactions WHERE service_trx_id = :svc_id"),
                    {"svc_id": service_trx_id}
                ).fetchone()

                if trx and trx[1] >= 0:
                    personal_account, amount, order_year, existing_idorder = trx
                    idorder = existing_idorder

                    # Если idorder не сохранен — ищем заново
                    if not idorder:
                        if order_year:
                            q = text("""
                                SELECT IDORDER FROM ALEX.ORDERS
                                WHERE ORDERNUMBER = :num
                                  AND EXTRACT(YEAR FROM INDATE) = :year
                                  AND ROWNUM = 1
                            """)
                            res = db.execute(q, {"num": int(personal_account), "year": int(order_year)}).fetchone()
                        else:
                            q = text("""
                                SELECT IDORDER FROM (
                                    SELECT IDORDER FROM ALEX.ORDERS
                                    WHERE ORDERNUMBER = :num
                                    ORDER BY INDATE DESC
                                ) WHERE ROWNUM = 1
                            """)
                            res = db.execute(q, {"num": int(personal_account)}).fetchone()

                        if res:
                            idorder = res[0]

                    if idorder:
                        success = record_payment_in_alex(
                            db=db,
                            idorder=idorder,
                            amount=amount,
                            num_erip=erip_trx_id,
                            service_trx_id=service_trx_id
                        )
                        if success:
                            logger.info("debt_written_off", idorder=idorder, amount=amount, order_year=order_year)
                        else:
                            logger.error("debt_writeoff_failed", idorder=idorder)
                    else:
                        logger.warning("idorder_not_found",
                                      personal_account=personal_account,
                                      order_year=order_year)
                else:
                    logger.warning("no_amount_in_transaction", service_trx_id=service_trx_id)

            update_transaction_status(db, erip_trx_id, service_trx_id, status, error_text)
            return Response(content=resp_xml, media_type="text/xml; charset=windows-1251", status_code=200)

        # ============================================================
        # StornStart
        # ============================================================
        elif req_type == "StornStart":
            erip_trx_id = data.get("erip_trx_id") or ""
            service_trx_id = data.get("service_trx_id") or ""
            amount_raw = data.get("amount_raw", "0")

            logger.info("storn_start_received",
                       request_id=req_id,
                       erip_trx_id=erip_trx_id,
                       service_trx_id=service_trx_id,
                       amount=amount_raw)

            trx = db.execute(
                text("""
                    SELECT id, status, amount, idorder, order_year
                    FROM transactions
                    WHERE service_trx_id = :svc_id
                """),
                {"svc_id": service_trx_id}
            ).fetchone()

            if not trx:
                logger.warning("storn_transaction_not_found", service_trx_id=service_trx_id)
                return Response(
                    content=build_error_response(f"Транзакция {service_trx_id} не найдена"),
                    media_type="text/xml; charset=windows-1251",
                    status_code=200
                )

            trx_id, status, amount, idorder, order_year = trx

            if status != "success":
                logger.warning("storn_transaction_not_success",
                              service_trx_id=service_trx_id,
                              status=status)
                return Response(
                    content=build_error_response("Сторнирование запрещено на стороне производителя услуг"),
                    media_type="text/xml; charset=windows-1251",
                    status_code=200
                )

            if not idorder:
                logger.warning("storn_no_idorder", service_trx_id=service_trx_id)
                return Response(
                    content=build_error_response(f"Транзакция {service_trx_id} не имеет IDORDER"),
                    media_type="text/xml; charset=windows-1251",
                    status_code=200
                )

            logger.info("storn_approved",
                       service_trx_id=service_trx_id,
                       idorder=idorder,
                       amount=amount)

            resp_xml = '<?xml version="1.0" encoding="windows-1251"?><ServiceProvider_Response></ServiceProvider_Response>'
            return Response(
                content=resp_xml.encode("windows-1251"),
                media_type="text/xml; charset=windows-1251",
                status_code=200
            )

        # ============================================================
        # StornResult
        # ============================================================
        elif req_type == "StornResult":
            erip_trx_id = data.get("erip_trx_id") or ""
            service_trx_id = data.get("service_trx_id") or ""
            storned = data.get("storned")

            logger.info("storn_result_received",
                       request_id=req_id,
                       erip_trx_id=erip_trx_id,
                       service_trx_id=service_trx_id,
                       storned=storned)

            if storned == "Y":
                status = "storned"
                logger.info("storn_confirmed", request_id=req_id, service_trx_id=service_trx_id)

                trx = db.execute(
                    text("""
                        SELECT personal_account, amount, idorder
                        FROM transactions
                        WHERE service_trx_id = :svc_id
                    """),
                    {"svc_id": service_trx_id}
                ).fetchone()

                if trx and trx[2]:
                    personal_account, amount, idorder = trx
                    success = storn_payment_in_alex(
                        db=db,
                        idorder=idorder,
                        amount=amount,
                        service_trx_id=service_trx_id
                    )
                    if success:
                        logger.info("debt_restored",
                                   idorder=idorder,
                                   amount=amount,
                                   personal_account=personal_account)
                    else:
                        logger.error("debt_restore_failed",
                                    idorder=idorder,
                                    amount=amount)
                else:
                    logger.warning("storn_transaction_not_found_for_restore",
                                  service_trx_id=service_trx_id)

            elif storned == "N":
                status = "storn_failed"
                logger.warning("storn_failed", request_id=req_id, service_trx_id=service_trx_id)
            else:
                status = "storn_unknown"
                logger.warning("storned_value_unknown", request_id=req_id, storned=storned)

            update_transaction_status(db, erip_trx_id, service_trx_id, status)

            resp_xml = '<?xml version="1.0" encoding="windows-1251"?><ServiceProvider_Response></ServiceProvider_Response>'
            return Response(
                content=resp_xml.encode("windows-1251"),
                media_type="text/xml; charset=windows-1251",
                status_code=200
            )

        else:
            return Response(
                content=build_error_response("Unsupported RequestType"),
                media_type="text/xml; charset=windows-1251",
                status_code=200
            )

    except Exception as e:
        db.rollback()
        logger.error("processing_error", error=str(e), req_type=req_type, exc_info=True)
        return Response(
            content=build_error_response("Internal error"),
            media_type="text/xml; charset=windows-1251",
            status_code=200
        )
    finally:
        # 🔹 Гарантированное закрытие сессии БД
        db.close()


@app.get("/healthcheck")
async def healthcheck():
    return {"status": "ok"}