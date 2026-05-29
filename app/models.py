from sqlalchemy import Column, Integer, String, Float, Date, CLOB
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    erip_request_id = Column("erip_request_id", String(64), unique=True, nullable=False)
    personal_account = Column("personal_account", String(32), nullable=False)
    amount = Column("amount", Float, default=0.0)
    currency = Column("currency", String(3), default="933")
    service_trx_id = Column("service_trx_id", String(8), unique=True, nullable=False)
    transaction_id = Column("transaction_id", String(32))
    request_type = Column("request_type", String(20))
    erip_transaction_id = Column("erip_transaction_id", String(32))
    status = Column("status", String(20), default="pending")
    error_code = Column("error_code", Integer)
    error_text = Column("error_text", CLOB)
    created_at = Column("created_at", Date)
    processed_at = Column("processed_at", Date)
    metadata_json = Column("metadata_json", CLOB)
    auth_type = Column("auth_type", String(50))
    terminal_type = Column("terminal_type", String(50))

class Account(Base):
    __tablename__ = "accounts"
    account_number = Column("account_number", String(32), primary_key=True)
    status = Column("status", String(20), default="active")
    debt_amount = Column("debt_amount", Float, default=0.0)
    editable_flag = Column("editable_flag", String(1), default="N")
    min_amount = Column("min_amount", Float, default=0.01)
    max_amount = Column("max_amount", Float, default=100000.0)
    holder_surname = Column("holder_surname", String(30))
    holder_firstname = Column("holder_firstname", String(30))
    holder_patronymic = Column("holder_patronymic", String(30))
    city = Column("city", String(30))
    street = Column("street", String(30))
    house = Column("house", String(10))
    building = Column("building", String(10))
    apartment = Column("apartment", String(10))
    currency = Column("currency", String(3), default="933")
    service_no = Column("service_no", Integer, default=1)

class TransactionError(Base):
    __tablename__ = "transaction_errors"
    
    id = Column(Integer, primary_key=True)
    transaction_id = Column("transaction_id", Integer)
    error_stage = Column("error_stage", String(20), nullable=False)
    error_code = Column("error_code", Integer)
    error_text = Column("error_text", CLOB)
    created_at = Column("created_at", DateTime(timezone=True))