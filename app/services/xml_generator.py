# -*- coding: utf-8 -*-
"""Генераторы ответов ЕРИП. Возвращают БАЙТЫ в windows-1251."""

def _mask_name(full_name: str) -> str:
    """Маскирует ФИО по протоколу: Иванов → И***в"""
    if not full_name or len(full_name) < 2:
        return full_name or ""
    return full_name[0] + "***" + full_name[-1]

def _mask_city(city: str) -> str:
    """Маскирует город: Минск → М***к"""
    if not city or len(city) < 2:
        return city or ""
    return city[0] + "***" + city[-1]

def _mask_street(street: str) -> str:
    """Маскирует улицу: Пушкина → П***а"""
    if not street or len(street) < 2:
        return street or ""
    return street[0] + "***" + street[-1]

def _escape_xml(text: str) -> str:
    """Экранирование спецсимволов для XML"""
    if not text:
        return ""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))

def build_serviceinfo_response(acc: dict) -> bytes: # type: ignore[call-arg]
    """
    Генерация ответа ServiceInfo в windows-1251.
    acc: dict из get_account_info() с полями debt, editable, surname, city, etc.
    """
    debt = acc.get("debt", "0,00")
    
    # Маскировка данных (требование протокола)
    surname = _mask_name(acc.get("surname", ""))
    firstname = acc.get("firstname", "") 
    patronymic = acc.get("patronymic", "")
    city = _mask_city(acc.get("city", ""))
    street = _mask_street(acc.get("street", ""))
    
    xml = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        '  <ServiceInfo>\n'
        f'    <Amount Editable="{acc.get("editable", "Y")}" '
        f'MinAmount="{acc.get("min_amount", "0,01")}" '
        f'MaxAmount="{acc.get("max_amount", "100000,00")}">\n'
        f'      <Debt>{_escape_xml(debt)}</Debt>\n'
        '    </Amount>\n'
        '    <Name>\n'
        f'      <Surname>{_escape_xml(surname)}</Surname>\n'
        f'      <FirstName>{_escape_xml(firstname)}</FirstName>\n'
        f'      <Patronymic>{_escape_xml(patronymic)}</Patronymic>\n'
        '    </Name>\n'
        '    <Address>\n'
        f'      <City>{_escape_xml(city)}</City>\n'
        f'      <Street>{_escape_xml(street)}</Street>\n'
        f'      <House>{_escape_xml(acc.get("house", ""))}</House>\n'
        f'      <Apartment>{_escape_xml(acc.get("apartment", ""))}</Apartment>\n'
        '    </Address>\n'
        '    <Info>\n'
        '      <InfoLine>Задолженность по оплате за квартиру</InfoLine>\n'
        f'      <InfoLine>Составляет: {_escape_xml(debt)}</InfoLine>\n'
        '    </Info>\n'
        '  </ServiceInfo>\n'
        '</ServiceProvider_Response>'
    )
    
def build_transactionstart_response(svc_trx_id: str) -> bytes:
    """
    Генерация ответа TransactionStart в windows-1251.
    svc_trx_id: идентификатор транзакции сервиса
    """
    xml = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        '  <TransactionStart>\n'
        f'    <ServiceTransactionId>{svc_trx_id}</ServiceTransactionId>\n'
        '    <Status>OK</Status>\n'
        '  </TransactionStart>\n'
        '</ServiceProvider_Response>'
    )
    return xml.encode("windows-1251", errors="replace")


def build_error_response(error_message: str) -> bytes:
    """
    Генерация ответа с ошибкой в windows-1251.
    error_message: текст ошибки
    """
    xml = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        '  <Error>\n'
        f'    <Message>{_escape_xml(error_message)}</Message>\n'
        '  </Error>\n'
        '</ServiceProvider_Response>'
    )
    return xml.encode("windows-1251", errors="replace")