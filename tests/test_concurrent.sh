#!/bin/bash
# tests/test_concurrent.sh — Тест одновременной оплаты

echo "🚀 Отправка двух TransactionStart одновременно..."

# Первый запрос (в фоне)
curl -s -X POST http://10.222.64.3:8000/healthcheck \
  -F "XML=@tests/test_alex_transactionstart.xml" \
  -o /tmp/response1.xml &
PID1=$!

# Второй запрос (в фоне)
curl -s -X POST http://10.222.64.3:8000/healthcheck \
  -F "XML=@tests/test_alex_transactionstart2.xml" \
  -o /tmp/response2.xml &
PID2=$!

# Ждём завершения обоих
wait $PID1
wait $PID2

echo ""
echo "📊 Результаты:"
echo ""
echo "✅ Запрос 1:"
iconv -f windows-1251 -t utf-8 < /tmp/response1.xml
echo ""
echo "✅ Запрос 2:"
iconv -f windows-1251 -t utf-8 < /tmp/response2.xml