#!/usr/bin/env python3
import os, sys
os.environ.setdefault("LD_LIBRARY_PATH", "/usr/lib/oracle/12.2/client64/lib")

import cx_Oracle
from dotenv import load_dotenv
load_dotenv("/opt/erip_server_cxOracle/.env")

try:
    dsn = cx_Oracle.makedsn(
        os.getenv("ORACLE_HOST"),
        int(os.getenv("ORACLE_PORT", 1521)),
        service_name=os.getenv("ORACLE_SERVICE_NAME")
    )
    conn = cx_Oracle.connect(
        user=os.getenv("ORACLE_USER"),
        password=os.getenv("ORACLE_PASS"),
        dsn=dsn
    )
    cursor = conn.cursor()
    
    # Добавляем колонки (если их ещё нет)
    cursor.execute("""
        DECLARE
            col_exists NUMBER;
        BEGIN
            SELECT COUNT(*) INTO col_exists 
            FROM user_tab_columns 
            WHERE table_name = 'TRANSACTIONS' AND column_name = 'REQUEST_TYPE';
            IF col_exists = 0 THEN
                EXECUTE IMMEDIATE 'ALTER TABLE transactions ADD (request_type VARCHAR2(20))';
            END IF;
        END;
    """)
    
    cursor.execute("""
        DECLARE
            col_exists NUMBER;
        BEGIN
            SELECT COUNT(*) INTO col_exists 
            FROM user_tab_columns 
            WHERE table_name = 'TRANSACTIONS' AND column_name = 'ERIP_TRANSACTION_ID';
            IF col_exists = 0 THEN
                EXECUTE IMMEDIATE 'ALTER TABLE transactions ADD (erip_transaction_id VARCHAR2(32))';
            END IF;
        END;
    """)
    
    # Индексы
    cursor.execute("CREATE INDEX idx_request_type ON transactions(request_type)")
    cursor.execute("CREATE INDEX idx_erip_trx_id ON transactions(erip_transaction_id)")
    
    conn.commit()
    print("✓ Колонки и индексы добавлены успешно")
    
    # Проверка
    cursor.execute("""
        SELECT column_name FROM user_tab_columns 
        WHERE table_name = 'TRANSACTIONS' ORDER BY column_id
    """)
    print("Колонки в TRANSACTIONS:")
    for row in cursor.fetchall():
        print(f"  - {row[0]}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"✗ Ошибка: {e}")
    sys.exit(1)