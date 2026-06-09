def parse_xml(xml_str: str) -> dict:
    # Парсит XML из строки (уже декодированной)
    import xml.etree.ElementTree as ET
    
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
    
    req_type = data["request_type"] 
    
    if req_type == "ServiceInfo":
        agent_el = root.find(".//ServiceInfo/Agent")
        data["agent"] = agent_el.text.strip() if agent_el is not None and agent_el.text else None
        
    elif req_type == "TransactionStart":
        amount_el = root.find(".//TransactionStart/Amount")
        amount_raw = amount_el.text.strip() if amount_el is not None and amount_el.text else "0"
        try:
            data["amount_byn"] = int(amount_raw) / 100.0
        except ValueError:
            data["amount_byn"] = 0.0
        data["erip_trx_id"] = root.findtext(".//TransactionStart/TransactionId")
        data["auth_type"] = root.findtext(".//TransactionStart/AuthorizationType")
        
    elif req_type == "TransactionResult": 
        data["erip_trx_id"] = root.findtext(".//TransactionResult/TransactionId")
        data["service_trx_id"] = root.findtext(".//TransactionResult/ServiceProvider_TrxId")
        error_text_el = root.find(".//TransactionResult/ErrorText")
        data["error_text"] = error_text_el.text.strip() if error_text_el is not None and error_text_el.text else None
    
    elif req_type == "StornStart":
        data["erip_trx_id"] = root.findtext(".//StornStart/TransactionId")
        data["service_trx_id"] = root.findtext(".//StornStart/ServiceProvider_TrxId")
        amount_el = root.find(".//StornStart/Amount")
        amount_raw = amount_el.text.strip() if amount_el is not None and amount_el.text else "0"
        data["amount_raw"] = amount_raw 
        
    elif req_type == "StornResult":
        data["erip_trx_id"] = root.findtext(".//StornResult/TransactionId")
        data["service_trx_id"] = root.findtext(".//StornResult/ServiceProvider_TrxId")
        amount_el = root.find(".//StornResult/Amount")
        amount_raw = amount_el.text.strip() if amount_el is not None and amount_el.text else "0"
        data["amount_raw"] = amount_raw
        storned_el = root.find(".//StornResult/Storned")
        data["storned"] = storned_el.text.strip() if storned_el is not None and storned_el.text else None
    
    return data