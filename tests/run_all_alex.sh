#!/bin/bash
#   tests/run_all_alex.sh          # только статусы
#   tests/run_all_alex.sh -v       # показывает ответы

BASE_URL="http://127.0.0.1:8000"
TESTS_DIR="$(dirname "$0")"
PASS=0
FAIL=0
VERBOSE=0

# Проверка флага -v
if [[ "$1" == "-v" || "$1" == "--verbose" ]]; then
    VERBOSE=1
    echo "Режим: ПОДРОБНЫЙ"
fi

run_test() {
    local name="$1"
    local file="$2"
    local expected_tag="$3"
    
    echo -e "\n🔹 $name"
    echo "   Файл: $(basename "$file")"
    
    if [[ ! -f "$file" ]]; then
        echo "  Файл не найден"
        ((FAIL++))
        return 1
    fi
    
    local response
    response=$(curl -s --max-time 15 -X POST "$BASE_URL/" -F "XML=@$file" 2>/dev/null | iconv -f windows-1251 -t utf-8)
    local http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 -X POST "$BASE_URL/" -F "XML=@$file" 2>/dev/null)
    
    if [[ $VERBOSE -eq 1 ]]; then
        echo "   ┌─ HTTP: $http_code"
        echo "   └─ Ответ:"
        echo "$response" | sed 's/^/      /'
        echo ""
    fi
    
    if echo "$response" | grep -q "<$expected_tag>"; then
        echo "  OK (тег <$expected_tag> найден)"
        ((PASS++))
        return 0
    else
        echo "  FAIL (ожидался <$expected_tag>)"
        if [[ $VERBOSE -eq 0 ]]; then
            echo "  Ответ: ${response:0:150}..."
        fi
        ((FAIL++))
        return 1
    fi
}

echo "Запуск тестов"

run_test "Пример 1: ServiceInfo (долг)" "$TESTS_DIR/test_alex_serviceinfo.xml" "ServiceInfo"

run_test "Пример 2: ServiceInfo (Device)" "$TESTS_DIR/test_alex_serviceinfo_ex2.xml" "ServiceInfo"

run_test "Пример 3: TransactionStart" "$TESTS_DIR/test_alex_transactionstart.xml" "TransactionStart"

run_test "Пример 4: TransactionResult" "$TESTS_DIR/test_alex_transactionresult.xml" "TransactionResult"

run_test "Пример 5: StornStart" "$TESTS_DIR/test_alex_stornstart.xml" "ServiceProvider_Response"

run_test "Пример 6: StornResult" "$TESTS_DIR/test_alex_stornresult.xml" "ServiceProvider_Response"

run_test "Пример 7: Ошибка (Account not found)" "$TESTS_DIR/test_alex_error.xml" "Error"

echo "Пройдено: $PASS"
echo "Провалено: $FAIL"

if [[ $FAIL -eq 0 ]]; then
    echo "Все тесты пройдены!"
    exit 0
else
    echo "Есть ошибки — проверьте логи: tail -f logs/app.log"
    echo "Подсказка: запустите с -v для просмотра ответов: ./run_all_alex.sh -v"
    exit 1
fi