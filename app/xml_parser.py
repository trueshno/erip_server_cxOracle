import xml.etree.ElementTree as ET
import structlog
from typing import Optional, Dict, Any

logger = structlog.get_logger()

def parse_erip_xml(xml_bytes: bytes) -> Optional[Dict[str, Any]]:
    try:
        root = ET.fromstring(xml_bytes.decode("windows-1251"))
        req_type = root.findtext("RequestType")
        if not req_type:
            return None

        data: Dict[str, Any] = {
            "request_type": req_type,
            "request_id": root.findtext("RequestId") or "",
            "personal_account": root.findtext("PersonalAccount") or "",
            "currency": root.findtext("Currency") or "933",
        }

        if req_type == "ServiceInfo":
            debt_el = root.find(".//Amount/Debt")
            # Безопасно получаем текст, чтобы избежать вызова .strip() на None
            debt_text = debt_el.text if debt_el is not None else None
            data["debt"] = debt_text.strip() if debt_text else None
            
        elif req_type == "TransactionStart":
            amount_el = root.find(".//TransactionStart/Amount")
            # Аналогичная защита от None для amount_el.text
            amount_text = amount_el.text if amount_el is not None else None
            amount_raw = amount_text.strip() if amount_text else "0"
            
            data["amount_raw"] = amount_raw
            data["erip_trx_id"] = root.findtext(".//TransactionStart/TransactionId") or "0"
            
            # Конвертация копеек в BYN для БД
            try:
                data["amount_byn"] = int(amount_raw) / 100.0
            except ValueError:
                data["amount_byn"] = 0.0
                
        return data
    except Exception as e:
        logger.error("xml_parse_failed", error=str(e))
        return None