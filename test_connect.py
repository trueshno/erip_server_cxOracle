import os, sys
os.environ.setdefault("LD_LIBRARY_PATH", "/usr/lib/oracle/12.2/client64/lib")
os.environ.setdefault("NLS_LANG", "RUSSIAN_RUSSIA.UTF8")

try:
    import cx_Oracle
    from dotenv import load_dotenv
    load_dotenv()
    
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
    print("✓ CONNECT SUCCESS")
    
    cur = conn.cursor()
    
    # 1. Проверка количества строк в таблицах
    tables_to_check = ['TRANSACTIONS', 'ACCOUNTS', 'TRANSACTION_INFO_LINES']
    print("\nROW COUNTS:")
    for table in tables_to_check:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        status = "ПУСТАЯ" if count == 0 else f"{count} строк"
        print(f"  {table}: {status}")

 # 2. Попытка выбрать реальные данные (последние 5 записей)
    print("\nSAMPLE DATA (TRANSACTIONS):")
    cur.execute("""
        SELECT id, erip_request_id, amount, status, created_at 
        FROM (
            SELECT id, erip_request_id, amount, status, created_at 
            FROM transactions 
            ORDER BY created_at DESC
        )
        WHERE ROWNUM <= 5
    """)
    rows = cur.fetchall()
    if not rows:
        print("  (Нет данных для отображения)")
    else:
        for row in rows:
            # Декодирование байтов в строку, если нужно (для NLS_LANG)
            print(f"  ID: {row[0]}, Req: {row[1]}, Amt: {row[2]}, Status: {row[3]}, Date: {row[4]}")

    # 3. Проверка чтения CLOB (частая проблема)
    print("\nCLOB READ TEST:")
    cur.execute("""
        SELECT id, dbms_lob.getlength(error_text) as err_len, dbms_lob.getlength(metadata_json) as meta_len
        FROM (
            SELECT id, error_text, metadata_json
            FROM transactions
            WHERE error_text IS NOT NULL OR metadata_json IS NOT NULL
            ORDER BY id
        )
        WHERE ROWNUM <= 1
    """)
    lob_row = cur.fetchone()
    if lob_row:
        print(f"  CLOB доступен. ID: {lob_row[0]}, ErrorTextLen: {lob_row[1]}, MetaLen: {lob_row[2]}")
    else:
        print("  В таблице нет записей с заполненными CLOB полями для проверки")

    conn.close()
    print("\n✓ ALL EXTENDED TESTS PASSED")
    
except Exception as e:
    print(f"✗ ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)