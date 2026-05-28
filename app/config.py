# import os
# from dotenv import load_dotenv
# import cx_Oracle

# load_dotenv()

# dsn = cx_Oracle.makedsn(
#     host=os.getenv("ORACLE_HOST", "192.168.100.64"),
#     port=int(os.getenv("ORACLE_PORT", 1521)),
#     service_name=os.getenv("ORACLE_SERVICE_NAME")
# )

# # Если service_name не работает, то sid
# if os.getenv("ORACLE_USE_SID", "false").lower() == "true":
#     dsn = cx_Oracle.makedsn(
#         host=os.getenv("ORACLE_HOST", "192.168.100.64"),
#         port=int(os.getenv("ORACLE_PORT", 1521)),
#         sid=os.getenv("ORACLE_SID")
#     )

# DATABASE_URL = (
#     f"oracle+cx_oracle://{os.getenv('ORACLE_USER')}:{os.getenv('ORACLE_PASS')}@{dsn}"
# )
# LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
# DB_DEMO_MODE = os.getenv("DB_DEMO_MODE", "false").lower() == "true"

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