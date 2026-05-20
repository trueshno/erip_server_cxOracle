def build_serviceinfo_response(acc: dict) -> bytes:
    debt = acc.get("debt", "0,00")
    xml_str = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        '  <ServiceInfo>\n'
        f'    <Amount Editable="{acc.get("editable", "N")}" '
        f'MinAmount="{acc.get("min_amount", "0,01")}" '
        f'MaxAmount="{acc.get("max_amount", "100000,00")}">\n'
        f'      <Debt>{debt}</Debt>\n'
        '    </Amount>\n'
        '    <Name>\n'
        f'      <Surname>{acc.get("surname", "")}</Surname>\n'
        f'      <FirstName>{acc.get("firstname", "")}</FirstName>\n'
        f'      <Patronymic>{acc.get("patronymic", "")}</Patronymic>\n'
        '    </Name>\n'
        '    <Address>\n'
        f'      <City>{acc.get("city", "")}</City>\n'
        f'      <Street>{acc.get("street", "")}</Street>\n'
        f'      <House>{acc.get("house", "")}</House>\n'
        f'      <Apartment>{acc.get("apartment", "")}</Apartment>\n'
        '    </Address>\n'
        '    <Info>\n'
        f'      <InfoLine>Задолженность по оплате за квартиру</InfoLine>\n'
        f'      <InfoLine>Составляет: {debt}</InfoLine>\n'
        '    </Info>\n'
        '  </ServiceInfo>\n'
        '</ServiceProvider_Response>'
    )
    return xml_str.encode("windows-1251")

def build_transactionstart_response(svc_trx_id: str) -> bytes:
    xml_str = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        '  <TransactionStart>\n'
        f'    <ServiceProvider_TrxId>{svc_trx_id}</ServiceProvider_TrxId>\n'
        '    <Info>\n'
        f'      <InfoLine>Номер операции: {svc_trx_id}</InfoLine>\n'
        '    </Info>\n'
        '  </TransactionStart>\n'
        '</ServiceProvider_Response>'
    )
    return xml_str.encode("windows-1251")

def build_error_response(error_msg: str) -> bytes:
    xml_str = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '<ServiceProvider_Response>\n'
        '  <Error>\n'
        f'    <ErrorLine>{error_msg}</ErrorLine>\n'
        '  </Error>\n'
        '</ServiceProvider_Response>'
    )
    return xml_str.encode("windows-1251")