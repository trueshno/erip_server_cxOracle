# -*- coding: utf-8 -*-
"""
Генераторы ответов ЕРИП.
Возвращают БАЙТЫ в кодировке windows-1251 с читаемым форматированием.
"""
from typing import Optional, List 

def _mask_name(full_name: str) -> str:
    # Маска ФИО
    if not full_name or len(full_name) < 2:
        return full_name or ""
    return full_name[0] + "***" + full_name[-1]


def _mask_city(city: str) -> str:
    # Маска город
    if not city or len(city) < 2:
        return city or ""
    return city[0] + "***" + city[-1]


def _mask_street(street: str) -> str:
    # Маска улица
    if not street or len(street) < 2:
        return street or ""
    return street[0] + "***" + street[-1]


def _escape_xml(text: str) -> str:
    # Экранирование
    if not text:
        return ""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


def build_serviceinfo_response(acc: dict) -> bytes:
    if not acc:
        xml = (
            '<?xml version="1.0" encoding="windows-1251"?>\n'
            '<ServiceProvider_Response>\n'
            '  <ServiceInfo>\n'
            '    <Amount Editable="N" MinAmount="0,01" MaxAmount="100000,00">\n'
            '      <Debt>0,00</Debt>\n'
            '    </Amount>\n'
            '    <Info>\n'
            '      <InfoLine>Информация недоступна</InfoLine>\n'
            '    </Info>\n'
            '  </ServiceInfo>\n'
            '</ServiceProvider_Response>\n'
        )
        return xml.encode("windows-1251", errors="replace")
    
    debt = acc.get("debt") or "0,00"
    editable = acc.get("editable") or "Y"
    min_amount = acc.get("min_amount") or "0,01"
    max_amount = acc.get("max_amount") or "100000,00"
    
    surname = _mask_name(acc.get("surname") or "")
    firstname = acc.get("firstname") or ""
    patronymic = acc.get("patronymic") or ""
    city = _mask_city(acc.get("city") or "")
    street = _mask_street(acc.get("street") or "")
    house = acc.get("house") or ""
    apartment = acc.get("apartment") or ""
    
    xml = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        '  <ServiceInfo>\n'
        f'    <Amount Editable="{editable}" MinAmount="{min_amount}" MaxAmount="{max_amount}">\n'
        f'      <Debt>{debt}</Debt>\n'
        '    </Amount>\n'
        '    <Name>\n'
        f'      <Surname>{_escape_xml(surname)}</Surname>\n'
        f'      <FirstName>{_escape_xml(firstname)}</FirstName>\n'
        f'      <Patronymic>{_escape_xml(patronymic)}</Patronymic>\n'
        '    </Name>\n'
        '    <Address>\n'
        f'      <City>{_escape_xml(city)}</City>\n'
        f'      <Street>{_escape_xml(street)}</Street>\n'
        f'      <House>{_escape_xml(house)}</House>\n'
        f'      <Apartment>{_escape_xml(apartment)}</Apartment>\n'
        '    </Address>\n'
        '    <Info>\n'
        '      <InfoLine>Задолженность по оплате за квартиру</InfoLine>\n'
        f'      <InfoLine>Составляет: {_escape_xml(debt)}</InfoLine>\n'
        '    </Info>\n'
        '  </ServiceInfo>\n'
        '</ServiceProvider_Response>\n'
    )
    
    return xml.encode("windows-1251", errors="replace")


def build_transactionstart_response(svc_trx_id: str) -> bytes:
    xml = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        '  <TransactionStart>\n'
        f'    <ServiceProvider_TrxId>{svc_trx_id}</ServiceProvider_TrxId>\n'
        '    <Info>\n'
        f'      <InfoLine>Номер операции: {svc_trx_id}</InfoLine>\n'
        '    </Info>\n'
        '  </TransactionStart>\n'
        '</ServiceProvider_Response>\n'
    )
    return xml.encode("windows-1251", errors="replace")

def build_transactionresult_response(success: bool, custom_lines: Optional[List[str]] = None) -> bytes:
    if custom_lines:
        info_lines = custom_lines
    elif success:
        info_lines = ["Задолженность оплачена"]
    else:
        info_lines = ["Оплата аннулирована!"]
    
    lines_xml = "\n".join(f"      <InfoLine>{_escape_xml(line)}</InfoLine>" for line in info_lines)
    
    xml = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        '  <TransactionResult>\n'
        '    <Info>\n'
        f'{lines_xml}\n'
        '    </Info>\n'
        '  </TransactionResult>\n'
        '</ServiceProvider_Response>\n'
    )
    return xml.encode("windows-1251", errors="replace")

def build_error_response(error_message: str) -> bytes:
    # Генерация ответа с ошибкой пример 7"""
    lines = error_message.split('\n') if '\n' in error_message else [error_message]
    lines_xml = "\n".join(f"    <ErrorLine>{_escape_xml(line)}</ErrorLine>" for line in lines)
    
    xml = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        '  <Error>\n'
        f'{lines_xml}\n'
        '  </Error>\n'
        '</ServiceProvider_Response>\n'
    )
    return xml.encode("windows-1251", errors="replace")