# -*- coding: utf-8 -*-
import structlog
import secrets
import json
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import or_, text
from app.models import Transaction, Account, TransactionError
from app.db import SessionLocal

ERROR_ACCOUNT_NOT_FOUND = "Заказ {account}. Информация для оплаты не найдена. Проверьте номер заказа. vagr.by"
ERROR_ZERO_DEBT = "Заказ {account}. Оплата при нулевой задолженности запрещена. vagr.by"
ERROR_ACCOUNT_LOCKED = "Оплата по счету {account} временно заблокирована. vagr.by"

logger = structlog.get_logger()

def get_stored_response(request_id: str, request_type: str) -> Optional[str]:
    """
    Возвращает сохранённый XML-ответ по паре (request_id, request_type).
    """
    if not request_id or not request_type:
        return None
        
    db = SessionLocal()
    try:
        row = db.query(Transaction).filter(
            Transaction.erip_request_id == request_id,
            Transaction.request_type == request_type
        ).first()  # type: ignore[call-arg]
        
        if row and row.metadata_json:
            try:
                meta = json.loads(row.metadata_json)
                return meta.get("response_xml")
            except (json.JSONDecodeError, TypeError):
                logger.warning("cache_parse_error", request_id=request_id, request_type=request_type)
                return None
        return None
    except Exception as e:
        logger.error("cache_query_error", error=str(e), request_id=request_id, request_type=request_type)
        return None
    finally:
        db.close()

def update_transaction_status(
    erip_trx_id: Optional[str], 
    service_trx_id: Optional[str], 
    status: str, 
    error_text: Optional[str] = None
) -> bool:
    """Обновляет статус и логирует ошибку в TRANSACTION_ERRORS при статусе failed"""
    db = SessionLocal()
    try:
        filters = []
        if erip_trx_id:
            filters.append(Transaction.erip_transaction_id == erip_trx_id)
        if service_trx_id:
            filters.append(Transaction.service_trx_id == service_trx_id)
            
        if not filters:
            logger.warning("no_ids_for_status_update")
            return False
            
        trx = db.query(Transaction).filter(or_(*filters)).first()  # type: ignore[call-arg]
        if not trx:
            logger.warning("transaction_not_found_for_update", erip_trx_id=erip_trx_id, service_trx_id=service_trx_id)
            return False
        
        # 1. Обновляем основную транзакцию
        trx.status = status
        trx.processed_at = datetime.now()
        if error_text:
            trx.error_text = error_text[:4000] if len(error_text) > 4000 else error_text
            
        # 2. 🔹 ЛОГИРОВАНИЕ ОШИБКИ В TRANSACTION_ERRORS
        if error_text and status == "failed":
            # 🔹 Добавили # type: ignore[call-arg] для Pylance
            error_record = TransactionError(
                transaction_id=trx.id,  # type: ignore[call-arg]
                error_stage="TransactionResult",  # type: ignore[call-arg]
                error_code=400,  # type: ignore[call-arg]
                error_text=error_text[:4000] if len(error_text) > 4000 else error_text,  # type: ignore[call-arg]
                created_at=datetime.now()  # type: ignore[call-arg]
            )
            db.add(error_record)
            logger.info("error_logged_to_db", transaction_id=trx.id, error=error_text[:50])
            
        db.commit()
        logger.info("transaction_status_updated", trx_id=trx.id, status=status)
        return True
    except Exception as e:
        db.rollback()
        logger.error("db_update_error", error=str(e), exc_info=True)
        return False
    finally:
        db.close()

def get_account_info_alex(personal_account: str, order_year: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Получает данные счёта из ALEX.
    personal_account = ORDERNUMBER, order_year = год заказа (из ParameterList с кодом 300).
    """
    db = SessionLocal()
    try:
        # 1. Ищем IDORDER по ORDERNUMBER + году
        if order_year:
            idorder_query = text("""
                SELECT IDORDER 
                FROM ALEX.ORDERS 
                WHERE ORDERNUMBER = :order_number
                AND EXTRACT(YEAR FROM INDATE) = :year
                AND ROWNUM = 1
            """)
            idorder_result = db.execute(
                idorder_query, 
                {"order_number": int(personal_account), "year": int(order_year)}
            ).fetchone()
        else:
            idorder_query = text("""
                SELECT IDORDER 
                FROM ALEX.ORDERS 
                WHERE ORDERNUMBER = :order_number
                ORDER BY INDATE DESC
                FETCH FIRST 1 ROW ONLY
            """)
            idorder_result = db.execute(
                idorder_query, 
                {"order_number": int(personal_account)}
            ).fetchone()
        
        if not idorder_result or not idorder_result[0]:
            error_msg = ERROR_ACCOUNT_NOT_FOUND.format(account=personal_account)
            logger.info("alex_order_not_found", order_number=personal_account, year=order_year)
            return {"_error": error_msg}
        
        idorder = idorder_result[0]
        
        # 2. Считаем задолженность по IDORDER через функцию ALEX.sum_order_nds2
        debt_query = text("""
            SELECT ALEX.sum_order_nds2(:idorder) FROM DUAL
        """)
        debt_val = db.execute(debt_query, {"idorder": idorder}).scalar() or 0
        logger.info("debt_calculated", idorder=idorder, debt_val=debt_val)
        
        # 3. Получаем адрес из ALEX.ORDEROBJ по IDORDER
        addr_query = text("""
            SELECT PRIMADR
            FROM ALEX.ORDEROBJ
            WHERE IDORDER = :idorder AND ROWNUM = 1
        """)
        addr_result = db.execute(addr_query, {"idorder": idorder}).fetchone()
        street = addr_result[0].strip() if addr_result and addr_result[0] else ""
        
        # 4. 🔹 Получаем ФИО — ДВУМЯ ОТДЕЛЬНЫМИ ЗАПРОСАМИ для диагностики
        logger.info("starting_fio_query", idorder=idorder)
        
        # Шаг 4.1: Получаем IDSUBJ из ORDERSUBJ
        idsubj_query = text("""
            SELECT TRIM(IDSUBJ), SUBJTYPE
            FROM ALEX.ORDERSUBJ
            WHERE IDORDER = :idorder
            AND SUBJTYPE = 'F'
            AND ROWNUM = 1
        """)
        idsubj_result = db.execute(idsubj_query, {"idorder": idorder}).fetchone()
        
        surname = "Ф***в"
        firstname = "И."
        patronymic = "О."
        
        if idsubj_result and idsubj_result[0]:
            idfizlic = idsubj_result[0]
            subjtype = idsubj_result[1]
            logger.info("idsubj_found", idorder=idorder, idfizlic=idfizlic, subjtype=subjtype)
            
            # Шаг 4.2: Ищем ФИО в BTI.BFIZLICTMP
            try:
                fio_query = text("""
                    SELECT FAM, NAIM, SNAIM
                    FROM BTI.BFIZLIC
                    WHERE TRIM(IDFIZLIC) = :idfizlic
                """)
                fio_result = db.execute(fio_query, {"idfizlic": idfizlic}).fetchone()
                logger.info("fio_query_executed", idfizlic=idfizlic, found=fio_result is not None)
                
                if fio_result:
                    raw_surname = fio_result[0].strip() if fio_result[0] else ""
                    raw_firstname = fio_result[1].strip() if fio_result[1] else ""
                    raw_patronymic = fio_result[2].strip() if fio_result[2] else ""
                    
                    if raw_surname:
                        surname = raw_surname[0] + "***" + raw_surname[-1] if len(raw_surname) > 2 else "***"
                    if raw_firstname:
                        firstname = raw_firstname[0] + "."
                    if raw_patronymic:
                        patronymic = raw_patronymic[0] + "."
                    
                    logger.info("fio_extracted", 
                               idorder=idorder, 
                               surname=surname, 
                               firstname=firstname, 
                               patronymic=patronymic)
                else:
                    logger.warning("fio_not_found_in_bti", idfizlic=idfizlic)
            except Exception as fio_err:
                logger.error("fio_query_failed", 
                           error=str(fio_err), 
                           error_type=type(fio_err).__name__,
                           idfizlic=idfizlic)
        else:
            logger.warning("idsubj_not_found", idorder=idorder)
        
        def fmt(val: float) -> str:
            return f"{val:.2f}".replace(".", ",")
        
        return {
            "debt": fmt(float(debt_val)),
            "editable": "Y",
            "min_amount": "0,01",
            "max_amount": "100000,00",
            "surname": surname,
            "firstname": firstname,
            "patronymic": patronymic,
            "city": "",
            "street": street,
            "house": "",
            "apartment": ""
        }
        
    except Exception as e:
        logger.error("alex_db_error", error=str(e), personal_account=personal_account, exc_info=True)
        return None
    finally:
        db.close()

def record_payment_in_alex(
    idorder: int, 
    amount: float, 
    num_erip: str, 
    service_trx_id: str,
    num_kartchek: str = ""
) -> bool:
    """
    Записывает платёж в ALEX.PAYMENTS для реального списания задолженности.
    """
    db = SessionLocal()
    try:
        #  Однострочный SQL + кавычки для "NUM" + переименованный параметр :doc_num
        insert_query = text(
            "INSERT INTO ALEX.PAYMENTS (IDORDER, SUMMA, IDKASSA, NUM_ERIP, NUM_KARTCHEK, \"NUM\") "
            "VALUES (:idorder, :summa, 1, :num_erip, :num_kartchek, :doc_num)"
        )
        
        # Генерируем номер документа
        doc_num = f"ERIP-{service_trx_id}" if service_trx_id else f"ERIP-{int(datetime.now().timestamp())}"
        
        # Явное приведение типов для cx_Oracle
        params = {
            "idorder": int(idorder),
            "summa": float(amount),
            "num_erip": int(num_erip) if num_erip and str(num_erip).isdigit() else None,
            "num_kartchek": str(num_kartchek)[:50] if num_kartchek else None,
            "doc_num": doc_num[:50]
        }
        
        db.execute(insert_query, params)
        db.commit()
        
        logger.info("payment_recorded_in_alex", 
                   idorder=idorder, 
                   amount=amount, 
                   num_erip=num_erip)
        return True
        
    except Exception as e:
        db.rollback()
        logger.error("payment_record_error", error=str(e), idorder=idorder, exc_info=True)
        return False
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
    svc_trx_id: Optional[str] = None,
    order_year: Optional[str] = None 
) -> Optional[str]:

    db = SessionLocal()
    try:
        if svc_trx_id is None:
            svc_trx_id = "".join([str(secrets.randbelow(10)) for _ in range(8)])

        metadata = {
            "request_type": req_type,
            "erip_trx_id": erip_trx_id,
            "terminal_id": terminal_id,
            "terminal_type": terminal_type,
            "order_year": order_year,
            "agent_code": agent_code,
            "auth_type": auth_type,
            "response_xml": response_xml 
        }

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


def storn_payment_in_alex(
    idorder: int, 
    amount: float, 
    service_trx_id: str
) -> bool:
    """
    Сторнирует платёж в ALEX.PAYMENTS — помечает запись как возвращённую.
    Использует поля USER_VOZVRAT и DATE_VOZVRAT.
    """
    db = SessionLocal()
    try:
        # 🔹 Ищем запись о платеже по IDORDER и NUM (который содержит service_trx_id)
        num = f"ERIP-{service_trx_id}"
        
        update_query = text(
            "UPDATE ALEX.PAYMENTS "
            "SET USER_VOZVRAT = 1, DATE_VOZVRAT = SYSDATE "
            "WHERE IDORDER = :idorder "
            "AND \"NUM\" = :num "
            "AND USER_VOZVRAT IS NULL"
        )
        
        result = db.execute(update_query, {
            "idorder": int(idorder),
            "num": num[:50]
        })
        db.commit()
        
        rows_updated = result.rowcount
        logger.info("payment_storned_in_alex", 
                   idorder=idorder, 
                   num=num,
                   rows_updated=rows_updated)
        
        return rows_updated > 0
        
    except Exception as e:
        db.rollback()
        logger.error("payment_storn_error", error=str(e), idorder=idorder, exc_info=True)
        return False
    finally:
        db.close()