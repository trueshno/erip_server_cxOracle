# app/config.py
import os
import cx_Oracle
from dotenv import load_dotenv

load_dotenv()

dsn = cx_Oracle.makedsn(
    host=os.getenv("ORACLE_HOST", "192.168.100.64"),
    port=int(os.getenv("ORACLE_PORT", 1521)),
    service_name=os.getenv("ORACLE_SERVICE_NAME", "orcl200")
)

DATABASE_URL = f"oracle+cx_oracle://{os.getenv('ORACLE_USER')}:{os.getenv('ORACLE_PASS')}@{dsn}"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")