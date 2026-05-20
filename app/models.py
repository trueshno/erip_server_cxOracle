from sqlalchemy import Column, Integer, String, Float, Date, CLOB
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    erip_request_id = Column("erip_request_id", String(64), unique=True, nullable=False)
    personal_account = Column("personal_account", String(32), nullable=False)
    amount = Column("amount", Float, nullable=True)
    currency = Column("currency", String(3), default="933")
    service_trx_id = Column("service_trx_id", String(8), unique=True, nullable=False)
    erip_transaction_id = Column("transaction_id", String(32), nullable=True)
    status = Column("status", String(20), default="pending")
    error_code = Column("error_code", Integer, nullable=True)
    error_text = Column("error_text", CLOB, nullable=True)
    created_at = Column("created_at", Date, nullable=True)
    processed_at = Column("processed_at", Date, nullable=True)
    metadata_json = Column("metadata_json", CLOB, nullable=True)
    response_xml = Column("response_xml", CLOB, nullable=True)

class MockClient(Base):
    __tablename__ = "mock_clients"
    personal_account = Column("personal_account", String(32), primary_key=True)
    debt = Column("debt", String(20))
    surname = Column("surname", String(50))
    firstname = Column("firstname", String(50))
    patronymic = Column("patronymic", String(50))
    city = Column("city", String(50))
    street = Column("street", String(50))
    house = Column("house", String(10))
    apartment = Column("apartment", String(10))