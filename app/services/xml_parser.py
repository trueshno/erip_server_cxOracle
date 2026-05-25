def parse_xml(xml_str: str) -> dict:
    """Парсит XML из строки (уже декодированной)"""
    import xml.etree.ElementTree as ET
    import re
    
    # Удаляем BOM если есть
    if xml_str.startswith('\ufeff'):
        xml_str = xml_str[1:]
    
    root = ET.fromstring(xml_str.strip())
    
    terminal_elem = root.find(".//Terminal")
    data = {
        "request_type": root.findtext("RequestType"),
        "request_id": root.findtext("RequestId"),
        "personal_account": root.findtext("PersonalAccount"),
        "currency": root.findtext("Currency"),
        "terminal_id": root.findtext("Terminal"),
        "terminal_type": terminal_elem.get("Type", "0") if terminal_elem is not None else "0"
    }
    
    if data["request_type"] == "ServiceInfo":
        agent_el = root.find(".//ServiceInfo/Agent")
        data["agent"] = agent_el.text.strip() if agent_el is not None and agent_el.text else None
    elif data["request_type"] == "TransactionStart":
        amount_el = root.find(".//TransactionStart/Amount")
        amount_raw = amount_el.text.strip() if amount_el is not None and amount_el.text else "0"
        try:
            data["amount_byn"] = int(amount_raw) / 100.0
        except ValueError:
            data["amount_byn"] = 0.0
        data["erip_trx_id"] = root.findtext(".//TransactionStart/TransactionId")
        data["auth_type"] = root.findtext(".//TransactionStart/AuthorizationType")
    
    return data