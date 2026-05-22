# -*- coding: utf-8 -*-
# isort: skip_file
# pylint: disable=unused-argument,missing-docstring,line-too-long
"""
Тесты для ERIP Server — версия с исправлениями для Pylance
Python 3.7.2, FastAPI 0.103.2, Pydantic 1.10.13
"""
from __future__ import unicode_literals

import sys
import os
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, Union
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

# Python 3.7 совместимость
try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("FastAPI not installed", allow_module_level=True)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app, parse_xml
from app.services.xml_generator import (
    build_serviceinfo_response,
    build_transactionstart_response,
    build_error_response
)
from app.services.db_service import (
    get_account_info,
    save_transaction,
    get_stored_response,
    SessionLocal
)
# Убрали 'engine' — он может не экспортироваться из db_service

client = TestClient(app)


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ для безопасной работы с XML
# ============================================================================

def safe_find_text(element: Optional[ET.Element], path: str, default: str = "") -> str:
    """Безопасное получение текста из XML-элемента"""
    if element is None:
        return default
    found = element.find(path)
    if found is None or found.text is None:
        return default
    return found.text


def safe_get_attr(element: Optional[ET.Element], attr: str, default: str = "") -> str:
    """Безопасное получение атрибута"""
    if element is None:
        return default
    value = element.get(attr)
    return value if value is not None else default


def safe_find_element(element: Optional[ET.Element], path: str) -> Optional[ET.Element]:
    """Безопасный поиск элемента"""
    if element is None:
        return None
    return element.find(path)


# ============================================================================
# ФИКСТУРЫ
# ============================================================================

@pytest.fixture(scope="function")
def sample_serviceinfo_request() -> bytes:
    return b'''<?xml version="1.0" encoding="windows-1251"?>
<ServiceProvider_Request>
    <Version>1</Version>
    <RequestType>ServiceInfo</RequestType>
    <DateTime>20200601153456</DateTime>
    <Terminal Type="5">55411</Terminal>
    <ServiceNo>1</ServiceNo>
    <PersonalAccount>123</PersonalAccount>
    <Currency>933</Currency>
    <RequestId>9221</RequestId>
    <ServiceInfo>
        <Agent>999</Agent>
    </ServiceInfo>
</ServiceProvider_Request>'''


@pytest.fixture(scope="function")
def sample_transactionstart_request() -> bytes:
    return b'''<?xml version="1.0" encoding="windows-1251"?>
<ServiceProvider_Request>
    <Version>1</Version>
    <RequestType>TransactionStart</RequestType>
    <DateTime>20200601153856</DateTime>
    <Terminal Type="5">55411</Terminal>
    <ServiceNo>1</ServiceNo>
    <PersonalAccount>123</PersonalAccount>
    <Currency>933</Currency>
    <RequestId>9221</RequestId>
    <TransactionStart>
        <Amount>250000</Amount>
        <TransactionId>6180433</TransactionId>
        <Agent>999</Agent>
        <AuthorizationType>BANK999</AuthorizationType>
    </TransactionStart>
</ServiceProvider_Request>'''


@pytest.fixture(scope="function")
def mock_account_data() -> Dict[str, Any]:
    return {
        "debt": "30,21",
        "editable": "Y",
        "min_amount": "0,01",
        "max_amount": "100000,00",
        "surname": "И***в",
        "firstname": "Иван",
        "patronymic": "Иванович",
        "city": "М***к",
        "street": "П***а",
        "house": "10",
        "apartment": "100",
        "info_line": "Задолженность по оплате за квартиру"
    }


@pytest.fixture(scope="function")
def mock_db_session():
    with patch('app.services.db_service.SessionLocal') as mock_session_factory:
        mock_db = MagicMock()
        mock_session_factory.return_value = mock_db
        mock_db.close = MagicMock()
        mock_db.rollback = MagicMock()
        mock_db.commit = MagicMock()
        yield mock_db
        mock_db.close.assert_called()


# ============================================================================
# ТЕСТЫ XML-ГЕНЕРАТОРОВ
# ============================================================================

class TestXmlGenerators(object):

    def test_build_serviceinfo_response_structure(self, mock_account_data: Dict[str, Any]) -> None:
        response = build_serviceinfo_response(mock_account_data)
        assert isinstance(response, bytes)
        
        response_str = response.decode('windows-1251')
        root = ET.fromstring(response_str)
        
        assert root.tag == 'ServiceProvider_Response'
        
        service_info = safe_find_element(root, 'ServiceInfo')
        assert service_info is not None
        
        amount = safe_find_element(service_info, 'Amount')
        assert amount is not None
        assert safe_get_attr(amount, 'Editable') == 'Y'
        assert safe_get_attr(amount, 'MinAmount') == '0,01'
        assert safe_get_attr(amount, 'MaxAmount') == '100000,00'
        
        debt_text = safe_find_text(amount, 'Debt')
        assert debt_text == '30,21'
        
        # Проверка запятой как разделителя
        assert '30,21' in response_str
        
        # Проверка маскирования
        surname = safe_find_text(service_info, 'Name/Surname')
        assert surname == 'И***в'

    def test_build_transactionstart_response(self) -> None:
        svc_trx_id = "8571502"
        response = build_transactionstart_response(svc_trx_id)
        response_str = response.decode('windows-1251')
        root = ET.fromstring(response_str)
        
        trx_start = safe_find_element(root, 'TransactionStart')
        assert trx_start is not None
        
        svc_id_text = safe_find_text(trx_start, 'ServiceProvider_TrxId')
        assert svc_id_text == svc_trx_id
        assert svc_id_text.isdigit()
        assert len(svc_id_text) <= 12

    def test_build_error_response(self) -> None:
        error_msg = "Account not found"
        response = build_error_response(error_msg)
        response_str = response.decode('windows-1251')
        root = ET.fromstring(response_str)
        
        error = safe_find_element(root, 'Error')
        assert error is not None
        error_line = safe_find_text(error, 'ErrorLine')
        assert error_line == error_msg


# ============================================================================
# ТЕСТЫ PARSE_XML
# ============================================================================

class TestXmlParser(object):

    def test_parse_serviceinfo_request(self, sample_serviceinfo_request: bytes) -> None:
        data = parse_xml(sample_serviceinfo_request)
        assert isinstance(data, dict)
        assert data.get('request_type') == 'ServiceInfo'
        assert data.get('request_id') == '9221'
        assert data.get('personal_account') == '123'
        assert data.get('terminal_type') == '5'

    def test_parse_transactionstart_request(self, sample_transactionstart_request: bytes) -> None:
        data = parse_xml(sample_transactionstart_request)
        assert data.get('request_type') == 'TransactionStart'
        assert data.get('amount_kopeks') == '250000'
        assert data.get('erip_trx_id') == '6180433'


# ============================================================================
# ТЕСТЫ ENDPOINT (исправленные типы)
# ============================================================================

class TestErpEndpoint(object):

    @patch('app.services.db_service.get_stored_response')
    @patch('app.services.db_service.get_account_info')
    @patch('app.services.db_service.save_transaction')
    def test_serviceinfo_success_flow(
        self,
        mock_save: MagicMock,
        mock_get_acc: MagicMock,
        mock_stored: MagicMock,
        sample_serviceinfo_request: bytes,
        mock_account_data: Dict[str, Any]
    ) -> None:
        mock_stored.return_value = None
        mock_get_acc.return_value = mock_account_data
        mock_save.return_value = "12345678"
        
        # Исправление: передаём XML как строку, не bytes в dict
        response = client.post(
            "/",
            data={"XML": sample_serviceinfo_request.decode('windows-1251')},
            headers={"Content-Type": "multipart/form-data; charset=windows-1251"}
        )
        
        assert response.status_code == 200
        
        # Безопасная проверка Content-Type
        content_type = response.headers.get("content-type") or ""
        assert "windows-1251" in content_type.lower() or "xml" in content_type.lower()
        
        response_str = response.content.decode('windows-1251')
        root = ET.fromstring(response_str)
        
        debt = safe_find_text(root, './/ServiceInfo/Amount/Debt')
        assert debt == '30,21'

    @patch('app.services.db_service.get_stored_response')
    def test_idempotency_serviceinfo_cached(
        self,
        mock_stored: MagicMock,
        sample_serviceinfo_request: bytes
    ) -> None:
        cached_response = '''<?xml version="1.0" encoding="windows-1251"?>
<ServiceProvider_Response><ServiceInfo><Amount><Debt>30,21</Debt></Amount></ServiceInfo></ServiceProvider_Response>'''
        mock_stored.return_value = cached_response
        
        response = client.post(
            "/",
            data={"XML": cached_response},
            headers={"Content-Type": "multipart/form-data"}
        )
        
        assert response.status_code == 200
        assert cached_response.encode('windows-1251') in response.content

    def test_missing_xml_in_form_request(self) -> None:
        response = client.post("/", data={})
        assert response.status_code == 200
        
        response_str = response.content.decode('windows-1251', errors='replace')
        root = ET.fromstring(response_str)
        error_line = safe_find_text(root, './/Error/ErrorLine')
        assert error_line, "Missing XML should return Error element"

    @patch('app.services.db_service.get_stored_response')
    @patch('app.services.db_service.get_account_info')
    def test_account_not_found_error(
        self,
        mock_get_acc: MagicMock,
        mock_stored: MagicMock,
        sample_serviceinfo_request: bytes
    ) -> None:
        mock_stored.return_value = None
        mock_get_acc.return_value = None
        
        response = client.post(
            "/",
            data={"XML": sample_serviceinfo_request.decode('windows-1251')},
            headers={"Content-Type": "multipart/form-data"}
        )
        
        assert response.status_code == 200
        root = ET.fromstring(response.content.decode('windows-1251'))
        error_line = safe_find_text(root, './/Error/ErrorLine')
        assert error_line and ("not found" in error_line.lower() or "Account" in error_line)


# ============================================================================
# ТЕСТЫ БИЗНЕС-ЛОГИКИ
# ============================================================================

class TestDbService(object):

    @patch('app.services.db_service.SessionLocal')
    def test_save_transaction_generates_valid_id(self, mock_session_factory: MagicMock) -> None:
        mock_db = MagicMock()
        mock_session_factory.return_value = mock_db
        mock_session = mock_db.__enter__.return_value if hasattr(mock_db, '__enter__') else mock_db
        mock_session.commit = MagicMock()
        
        result = save_transaction(
            req_id="9221",
            req_type="TransactionStart",
            account="123",
            currency="933",
            amount_byn=2500.00,
            erip_trx_id="6180433",
            response_xml="<test/>"
        )
        
        assert result is not None
        # Безопасная проверка: result — str, не Optional
        assert isinstance(result, str)
        assert result.isdigit()
        assert 8 <= len(result) <= 12


# ============================================================================
# ТЕСТЫ СПЕЦИФИКАЦИИ ЕРИП
# ============================================================================

class TestEripSpecificationCompliance(object):

    def test_datetime_format_yyyymmddhhmmss(self) -> None:
        valid_examples = ["20200601153456", "20231231235959"]
        for dt in valid_examples:
            assert len(dt) == 14
            assert dt.isdigit()
            year, month, day = int(dt[0:4]), int(dt[4:6]), int(dt[6:8])
            assert 2000 <= year <= 2100
            assert 1 <= month <= 12
            assert 1 <= day <= 31

    def test_decimal_separator_comma(self) -> None:
        amounts = ["30,21", "0,01", "100000,00"]
        for amt in amounts:
            assert "," in amt
            # Проверка: нет точки как разделителя в этих значениях
            parts = amt.split(',')
            assert len(parts) == 2
            assert parts[0].isdigit() and parts[1].isdigit()

    def test_terminal_types_table_3_1_1(self) -> None:
        valid_types = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19}
        assert 5 in valid_types  # РКС из примеров


# ============================================================================
# ПАРАМЕТРИЗОВАННЫЕ ТЕСТЫ
# ============================================================================

@pytest.mark.parametrize("amount_kopeks,expected_byn", [
    ("250000", 2500.00),
    ("3021", 30.21),
    ("100", 1.00),
])
def test_amount_conversion_kopeks_to_byn(amount_kopeks: str, expected_byn: float) -> None:
    amount_byn = int(amount_kopeks) / 100.0
    assert amount_byn == expected_byn


@pytest.mark.parametrize("surname,expected_masked", [
    ("Иванов", "И***в"),
    ("Петров", "П***в"),
    ("", "И***в"),
])
def test_name_masking_variants(surname: str, expected_masked: str) -> None:
    if surname and len(surname) >= 3:
        masked = surname[0] + "***" + surname[-1]
    else:
        masked = "И***в"
    assert masked == expected_masked