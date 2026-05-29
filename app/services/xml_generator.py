# -*- coding: utf-8 -*-
"""Генераторы ответов ЕРИП. Возвращают БАЙТЫ в windows-1251."""

def _mask_name(full_name: str) -> str:
    if not full_name or len(full_name) < 2:
        return full_name or ""
    return full_name[0] + "***" + full_name[-1]

def _mask_city(city: str) -> str:
    if not city or len(city) < 2:
        return city or ""
    return city[0] + "***" + city[-1]

def _mask_street(street: str) -> str:
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

def build_serviceinfo_response(acc: dict) -> bytes:
    """Генерация ответа ServiceInfo в windows-1251. Гарантирует возврат bytes."""
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
            '</ServiceProvider_Response>'
        )
        return xml.encode("windows-1251", errors="replace")
    
    debt = acc.get("debt") or "0,00"
    editable = acc.get("editable") or "Y"
    min_amount = acc.get("min_amount") or "0,01"
    max_amount = acc.get("max_amount") or "100000,00"
    
    surname = acc.get("surname") or ""
    firstname = acc.get("firstname") or ""
    patronymic = acc.get("patronymic") or ""
    city = acc.get("city") or ""
    street = acc.get("street") or ""
    house = acc.get("house") or ""
    apartment = acc.get("apartment") or ""
    
    def mask(val: str) -> str:
        if not val or len(val) < 2:
            return val or ""
        return val[0] + "***" + val[-1]
    
    xml = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        '  <ServiceInfo>\n'
        f'    <Amount Editable="{editable}" MinAmount="{min_amount}" MaxAmount="{max_amount}">\n'
        f'      <Debt>{debt}</Debt>\n'
        '    </Amount>\n'
        '    <Name>\n'
        f'      <Surname>{mask(surname)}</Surname>\n'
        f'      <FirstName>{firstname}</FirstName>\n'
        f'      <Patronymic>{patronymic}</Patronymic>\n'
        '    </Name>\n'
        '    <Address>\n'
        f'      <City>{mask(city)}</City>\n'
        f'      <Street>{mask(street)}</Street>\n'
        f'      <House>{house}</House>\n'
        f'      <Apartment>{apartment}</Apartment>\n'
        '    </Address>\n'
        '    <Info>\n'
        '      <InfoLine>Задолженность по оплате: </InfoLine>\n'
        f'      <InfoLine>Составляет: {debt}</InfoLine>\n'
        '    </Info>\n'
        '  </ServiceInfo>\n'
        '</ServiceProvider_Response>'
    )
    
    try:
        return xml.encode("windows-1251", errors="replace")
    except Exception as e:
        fallback = '<?xml version="1.0" encoding="windows-1251"?><ServiceProvider_Response><ServiceInfo><Amount><Debt>0,00</Debt></Amount><Info><InfoLine>Error</InfoLine></Info></ServiceInfo></ServiceProvider_Response>'
        return fallback.encode("windows-1251", errors="replace")
    
def build_transactionstart_response(svc_trx_id: str) -> bytes:
    """
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

def build_transactionresult_response(success: bool, custom_lines: list = None) -> bytes:
    """Генерация ответа TransactionResult в windows-1251"""
    if custom_lines:
        info_lines = custom_lines
    elif success:
        info_lines = [
            "Задолженность оплачена"
        ]
    else:
        # ← ОШИБКА: короткий ответ
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
        '</ServiceProvider_Response>'
    )
    return xml.encode("windows-1251", errors="replace")

def build_error_response(error_message: str) -> bytes:
    """
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