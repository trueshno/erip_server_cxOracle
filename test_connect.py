#!/usr/bin/env python3
import os, sys
os.environ.setdefault("LD_LIBRARY_PATH", "/usr/lib/oracle/12.2/client64/lib")

try:
    import cx_Oracle
    from dotenv import load_dotenv
    load_dotenv()
    
    dsn = cx_Oracle.makedsn(
        os.getenv("ORACLE_HOST"),
        int(os.getenv("ORACLE_PORT", 1521)),
        service_name=os.getenv("ORACLE_SERVICE_NAME")
    )
    print(f"✓ DSN formed: {dsn}")
    
    conn = cx_Oracle.connect(
        user=os.getenv("ORACLE_USER"),
        password=os.getenv("ORACLE_PASS"),
        dsn=dsn
    )
    print("✓ CONNECT SUCCESS")
    
    cur = conn.cursor()
    cur.execute("SELECT SYSDATE, user FROM dual")
    row = cur.fetchone()
    print(f"✓ DB Time: {row[0]}, User: {row[1]}")
    
    cur.execute("""
        SELECT table_name FROM user_tables 
        WHERE table_name IN ('TRANSACTIONS', 'ACCOUNTS', 'TRANSACTION_INFO_LINES')
    """)
    tables = [r[0] for r in cur.fetchall()]
    print(f"✓ Tables found: {tables}")
    
    cur.execute("""
        SELECT column_name, data_type, data_length 
        FROM user_tab_columns 
        WHERE table_name = 'TRANSACTIONS' 
        ORDER BY column_id
    """)
    print("\n✓ TRANSACTIONS columns:")
    for col in cur.fetchall():
        print(f"  {col[0]}: {col[1]}({col[2]})")
    
    conn.close()
    print("\n✓ ALL TESTS PASSED")
    
except cx_Oracle.DatabaseError as e:
    error, = e.args
    print(f"✗ ORACLE ERROR: {error.code} - {error.message}")
    if error.code == 12545:
        print("  → Проверьте: service_name vs sid, правильность имени сервиса")
    elif error.code == 1017:
        print("  → Проверьте: логин/пароль (ORACLE_USER / ORACLE_PASS)")
    elif error.code == 12514:
        print("  → Проверьте: имя сервиса 'orcl200' зарегистрировано в listener.ora")
    sys.exit(1)
except Exception as e:
    print(f"✗ PYTHON ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)