import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = (
    f"oracle+cx_oracle://{os.getenv('ORACLE_USER')}:{os.getenv('ORACLE_PASS')}"
    f"@{os.getenv('ORACLE_DSN')}"
)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")