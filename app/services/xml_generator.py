import xml.etree.ElementTree as ET

def _escape_xml(text: str) -> str:
    """Простой экранизатор для легаси-окружения"""
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&apos;"))

def build_serviceinfo_response(client: dict) -> bytes:
    """Пример 1 и 2: Ответ на ServiceInfo"""
    debt = client.get("debt", "0,00")
    xml_str = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        '  <ServiceInfo>\n'
        f'    <Amount Editable="Y" MinAmount="0,01" MaxAmount="100000">\n'
        f'      <Debt>{_escape_xml(debt)}</Debt>\n'
        '    </Amount>\n'
        '    <Name>\n'
        f'      <Surname>{_escape_xml(client.get("surname", ""))}</Surname>\n'
        f'      <FirstName>{_escape_xml(client.get("firstname", ""))}</FirstName>\n'
        f'      <Patronymic>{_escape_xml(client.get("patronymic", ""))}</Patronymic>\n'
        '    </Name>\n'
        '    <Address>\n'
        f'      <City>{_escape_xml(client.get("city", ""))}</City>\n'
        f'      <Street>{_escape_xml(client.get("street", ""))}</Street>\n'
        f'      <House>{_escape_xml(client.get("house", ""))}</House>\n'
        f'      <Apartment>{_escape_xml(client.get("apartment", ""))}</Apartment>\n'
        '    </Address>\n'
        '    <Info>\n'
        f'      <InfoLine>Задолженность по оплате за квартиру</InfoLine>\n'
        f'      <InfoLine>Составляет: {_escape_xml(debt)}</InfoLine>\n'
        '    </Info>\n'
        '  </ServiceInfo>\n'
        '</ServiceProvider_Response>'
    )
    return xml_str.encode("windows-1251")

def build_transactionstart_response(service_trx_id: str) -> bytes:
    """Пример 3: Ответ на TransactionStart"""
    xml_str = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        '  <TransactionStart>\n'
        f'    <ServiceProvider_TrxId>{service_trx_id}</ServiceProvider_TrxId>\n'
        '    <Info>\n'
        f'      <InfoLine>Номер операции: {service_trx_id}</InfoLine>\n'
        '    </Info>\n'
        '  </TransactionStart>\n'
        '</ServiceProvider_Response>'
    )
    return xml_str.encode("windows-1251")

def build_error_response(error_msg: str) -> bytes:
    """Стандартный ответ с ошибкой (Таблица 3.2)"""
    xml_str = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        '  <Error>\n'
        f'    <ErrorLine>{_escape_xml(error_msg)}</ErrorLine>\n'
        '  </Error>\n'
        '</ServiceProvider_Response>'
    )
    return xml_str.encode("windows-1251")