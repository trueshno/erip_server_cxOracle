import xml.etree.ElementTree as ET
from typing import Dict, Optional
import structlog

logger = structlog.get_logger()

def parse_erip_xml(xml_bytes: bytes) -> Optional[ET.Element]:
    """Парсит входящий XML в кодировке cp1251"""
    try:
        xml_str = xml_bytes.decode("windows-1251")
        root = ET.fromstring(xml_str)
        logger.info("xml_parsed", request_type=root.findtext("RequestType"))
        return root
    except Exception as e:
        logger.error("xml_parse_error", error=str(e))
        return None

def get_request_type(root: ET.Element) -> Optional[str]:
    req_type_el = root.find("RequestType")
    return req_type_el.text.strip() if req_type_el is not None else None