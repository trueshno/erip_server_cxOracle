#!/usr/bin/env python3
import os, sys
os.environ.setdefault("LD_LIBRARY_PATH", "/usr/lib/oracle/12.2/client64/lib")
sys.path.insert(0, '/opt/erip_server_cxOracle')

from app.db import SessionLocal, engine
from app.models import Account

print(f"Engine URL: {engine.url}")

db = SessionLocal()
try:
    # Прямой запрос
    acc = db.query(Account).filter(Account.account_number == '123').first()
    
    if acc:
        print(f"✓ Account found: {acc.holder_surname}, debt={acc.debt_amount}")
    else:
        print("✗ Account NOT found via SQLAlchemy")
        
        # Проверим, какие аккаунты вообще есть
        all_acc = db.query(Account.account_number).all()
        print(f"  All accounts: {[a[0] for a in all_acc]}")
        
        # Проверим точное значение с отладкой
        from sqlalchemy import text
        result = db.execute(text("SELECT account_number, DUMP(account_number) FROM accounts WHERE ROWNUM <= 5"))
        for row in result:
            print(f"  Debug: '{row[0]}' → {row[1]}")
finally:
    db.close()