import requests
import xml.etree.ElementTree as ET

URL = "http://10.222.64.3:8000/healthcheck"

# 1. TransactionStart
xml_start = '''<?xml version="1.0" encoding="windows-1251"?>
<ServiceProvider_Request>
  <Version>1</Version>
  <RequestType>TransactionStart</RequestType>
  <DateTime>20260625120000</DateTime>
  <Terminal Type="5">55411</Terminal>
  <ServiceNo>1</ServiceNo>
  <PersonalAccount>31620</PersonalAccount>
  <Currency>933</Currency>
  <RequestId>CYCLE-START-004</RequestId>
  <TransactionStart>
    <Amount>900</Amount>
    <TransactionId>11122233344</TransactionId>
    <Agent>999</Agent>
    <AuthorizationType>MS</AuthorizationType>
    <ParameterList Count="1">
      <Parameter Idx="300">2026</Parameter>
    </ParameterList>
  </TransactionStart>
</ServiceProvider_Request>'''

print("1. Отправляем TransactionStart...")
resp1 = requests.post(URL, files={'XML': ('req.xml', xml_start.encode('windows-1251'))})
print(f"Статус: {resp1.status_code}")
print(resp1.content.decode('windows-1251'))

# Извлекаем ServiceProvider_TrxId
root = ET.fromstring(resp1.content)
svc_trx_id = root.findtext(".//ServiceProvider_TrxId")
print(f"\n✅ Получен ServiceProvider_TrxId: {svc_trx_id}\n")

if not svc_trx_id:
    print(" Ошибка: не удалось получить ServiceProvider_TrxId")
    exit(1)

# 2. TransactionResult
xml_result = f'''<?xml version="1.0" encoding="windows-1251"?>
<ServiceProvider_Request>
  <Version>1</Version>
  <RequestType>TransactionResult</RequestType>
  <DateTime>20260625120100</DateTime>
  <Terminal Type="5">55411</Terminal>
  <ServiceNo>1</ServiceNo>
  <PersonalAccount>31620</PersonalAccount>
  <Currency>933</Currency>
  <RequestId>CYCLE-RESULT-004</RequestId>
  <TransactionResult>
    <TransactionId>11122233344</TransactionId>
    <ServiceProvider_TrxId>{svc_trx_id}</ServiceProvider_TrxId>
  </TransactionResult>
</ServiceProvider_Request>'''

print("2. Отправляем TransactionResult...")
resp2 = requests.post(URL, files={'XML': ('req.xml', xml_result.encode('windows-1251'))})
print(f"Статус: {resp2.status_code}")
print(resp2.content.decode('windows-1251'))
