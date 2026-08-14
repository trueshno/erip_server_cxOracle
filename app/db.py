from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

os.environ.setdefault("NLS_LANG", "RUSSIAN_RUSSIA.CL8MSWIN1251")

# Витебск
VITEBSK_DATABASE_URL = "oracle+cx_oracle://erip_user:rjrf-rjkf@192.168.100.64:1521/?service_name=orcl200"
# Орша
ORSHA_DATABASE_URL = "oracle+cx_oracle://erip_user:rjrf-rjkf@192.168.140.100:1521/?service_name=orcl240"

engine_vitebsk = create_engine(VITEBSK_DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
engine_orsha = create_engine(ORSHA_DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)

Base = declarative_base()

def get_engine(service_no: str):
    """Возвращает нужный engine в зависимости от номера услуги"""
    if str(service_no) == "240":
        return engine_orsha
    return engine_vitebsk  # По умолчанию Витебск (200)

def get_db_session(service_no: str):
    """Создает и возвращает сессию для нужной БД"""
    engine = get_engine(service_no)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()