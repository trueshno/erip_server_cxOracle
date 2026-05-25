#!/usr/bin/env python3
import os, sys
os.environ.setdefault("LD_LIBRARY_PATH", "/usr/lib/oracle/12.2/client64/lib")
os.environ.setdefault("NLS_LANG", "RUSSIAN_RUSSIA.UTF8")

try:
    import cx_Oracle
    from dotenv import load_dotenv
    load_dotenv()
    
    dsn = cx_Oracle.makedsn(
        os.getenv("ORACLE_HOST"),
        int(os.getenv("ORACLE_PORT", 1521)),
        service_name=os.getenv("ORACLE_SERVICE_NAME")
    )
    
    conn = cx_Oracle.connect(
        user=os.getenv("ORACLE_USER"),
        password=os.getenv("ORACLE_PASS"),
        dsn=dsn
    )
    print("✓ CONNECT SUCCESS\n")
    
    cur = conn.cursor()
    
    # 1. Получаем список всех таблиц пользователя
    cur.execute("""
        SELECT table_name 
        FROM user_tables 
        ORDER BY table_name
    """)
    tables = [row[0] for row in cur.fetchall()]
    
    print(f"📂 НАЙДЕНО ТАБЛИЦ: {len(tables)}")
    print("=" * 60)
    
    for table_name in tables:
        print(f"\n📊 ТАБЛИЦА: {table_name}")
        print("-" * 40)
        
        # 2. Получаем структуру таблицы (колонки)
        cur.execute("""
            SELECT column_name, data_type, data_length, data_precision, data_scale, nullable
            FROM user_tab_columns 
            WHERE table_name = :tbl
            ORDER BY column_id
        """, tbl=table_name)
        
        columns = cur.fetchall()
        print("Структура:")
        header = f"{'Колонка':<25} {'Тип':<15} {'Длина':<6} {'Null'}"
        print(header)
        print("-" * len(header))
        
        col_names = [c[0] for c in columns]
        for col in columns:
            nullable = 'YES' if col[5] == 'Y' else 'NO'
            precision = col[3] if col[3] is not None else ''
            scale = col[4] if col[4] is not None else ''
            
            if col[1] == 'NUMBER' and precision:
                type_str = f"NUMBER({precision},{scale})" if scale else f"NUMBER({precision})"
            elif col[1] in ['VARCHAR2', 'CHAR']:
                type_str = f"{col[1]}({col[2]})"
            elif col[1] in ['CLOB', 'BLOB']:
                type_str = col[1]
            else:
                type_str = col[1]
                
            print(f"{col[0]:<25} {type_str:<15} {col[2]:<6} {nullable}")
        
        # 3. Получаем количество строк
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cur.fetchone()[0]
        print(f"\nВсего строк: {count}")
        
        # 4. Выводим данные (максимум 10 строк для краткости)
        if count > 0:
            print("\nСодержимое (первые 10 строк):")
            
            # Формируем запрос с ROWNUM для ограничения выборки
            cols_str = ", ".join([f'"{c}"' for c in col_names])
            sql = f"""
                SELECT {cols_str} 
                FROM (
                    SELECT {cols_str} FROM {table_name}
                )
                WHERE ROWNUM <= 10
            """
            cur.execute(sql)
            rows = cur.fetchall()
            
            # Красивый вывод таблицы
            for i, row in enumerate(rows):
                print(f"  [{i+1}] ", end="")
                vals = []
                for val in row:
                    if val is None:
                        vals.append("NULL")
                    elif isinstance(val, cx_Oracle.LOB):
                        # Чтение CLOB/BLOB
                        content = val.read()
                        if isinstance(content, bytes):
                            content = content.decode('utf-8', errors='replace')
                        
                        # Получаем полную длину до обрезки
                        full_len = len(content)
                        
                        # Обрезаем длинные тексты для вывода
                        if full_len > 50:
                            display_content = content[:50] + "..."
                        else:
                            display_content = content
                            
                        vals.append(f"[LOB:{full_len}] {display_content}")
                print(", ".join(vals))
                
            if count > 10:
                print(f"  ... и еще {count - 10} строк (не показаны)")
        else:
            print("  (Таблица пуста)")
            
        print("-" * 60)

    conn.close()
    print("\n✓ ВСЕ ДАННЫЕ ВЫВЕДЕНЫ")
    
except Exception as e:
    print(f"✗ ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)