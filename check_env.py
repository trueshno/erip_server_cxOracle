import os
import sys
sys.path.insert(0, '/opt/erip_server_cxOracle')

# Пытаемся импортировать dotenv, если используется
try:
    from dotenv import load_dotenv
    load_dotenv('/opt/erip_server_cxOracle/.env')
    print("[INFO] .env loaded via dotenv")
except:
    print("[INFO] dotenv not used or failed")

print("--- ENVIRONMENT VARIABLES ---")
print(f"ORACLE_DSN: '{os.environ.get('ORACLE_DSN')}'")
print(f"ORACLE_USER: '{os.environ.get('ORACLE_USER')}'")
print(f"ORACLE_PASS: '{os.environ.get('ORACLE_PASS')}'")
print(f"LD_LIBRARY_PATH: '{os.environ.get('LD_LIBRARY_PATH')}'")

# Проверка подключения с теми данными, которые видит скрипт
dsn = os.environ.get('ORACLE_DSN')
user = os.environ.get('ORACLE_USER')
pwd = os.environ.get('ORACLE_PASS')

if dsn and user and pwd:
    try:
        import cx_Oracle
        print(f"\n[TEST] Trying connect to: {dsn} as {user}...")
        conn = cx_Oracle.connect(user, pwd, dsn)
        print("[SUCCESS] Connection established!")
        conn.close()
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")
else:
    print("\n[ERROR] Missing environment variables for DB connection")
