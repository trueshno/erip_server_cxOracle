import os
os.environ.setdefault("LD_LIBRARY_PATH", "/usr/lib/oracle/12.2/client64/lib")
import cx_Oracle
from dotenv import load_dotenv
load_dotenv()

dsn = cx_Oracle.makedsn("192.168.100.64", 1521, service_name="orcl200")
try:
    conn = cx_Oracle.connect(user=os.getenv("ORACLE_USER"), 
                             password=os.getenv("ORACLE_PASS"), 
                             dsn=dsn)
    print("✓ Connection OK")
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM user_tables WHERE table_name IN ('TRANSACTIONS', 'ACCOUNTS')")
    print("Tables found:", [r[0] for r in cur.fetchall()])
    cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'TRANSACTIONS' ORDER BY column_id")
    print("Transaction columns:", [r[0] for r in cur.fetchall()])
    conn.close()
except Exception as e:
    print(f"✗ Connection failed: {e}")