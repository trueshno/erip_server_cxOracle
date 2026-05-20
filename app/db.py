from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import DATABASE_URL

# Для Oracle 10g и cx_Oracle 6.4.1 рекомендуется отключать ANSI-join, если возникают ошибки парсинга
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"mode": 0}  # Стандартный режим подключения
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()