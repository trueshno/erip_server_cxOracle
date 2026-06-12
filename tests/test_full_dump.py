#!/usr/bin/env python3
import os, sys
import datetime

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
    
    # Подключение через erip_user к схеме ALEX
    conn = cx_Oracle.connect(
        user=os.getenv("ORACLE_USER"),  # должен быть erip_user
        password=os.getenv("ORACLE_PASS"),
        dsn=dsn
    )
    print("✓ CONNECT SUCCESS\n")
    
    cur = conn.cursor()

    def output_type_handler(cursor, name, defaultType, size, precision, scale):
        if defaultType in (cx_Oracle.CLOB, cx_Oracle.NCLOB):
            return cursor.var(cx_Oracle.STRING, arraysize=cur.arraysize, size=4000)
        if defaultType == cx_Oracle.FIXED_CHAR:
            return cursor.var(cx_Oracle.STRING, arraysize=cur.arraysize, size=size)
    
    if hasattr(cur, 'outputtypehandler'):
        cur.outputtypehandler = output_type_handler
    # -------------------------------------------------

    # Конкретные таблицы из схемы ALEX
    TABLES = ['DOGOVOR', 'KASSA', 'ORDERCHECK', 'ORDERDOCUMENTS', 'ORDEREXTR', 'ORDEROBJ', 'ORDERS', 'ORDERSUBJ', 'OUTDOCS', 'PAYMENTS', 'PAYMENTSHISTOR', 'SMSOCH_TINV']
    SCHEMA = 'ALEX'
    
    print(f"📂 ТАБЛИЦЫ ДЛЯ ЭКСПОРТА: {len(TABLES)}")
    print(f"📋 СХЕМА: {SCHEMA}")
    print("=" * 60)
    
    for table_name in TABLES:
        print(f"\n📊 ТАБЛИЦА: {SCHEMA}.{table_name}")
        print("-" * 40)
        
        # 1. Получаем структуру таблицы из схемы ALEX
        cur.execute("""
            SELECT column_name, data_type, data_length, data_precision, data_scale, nullable
            FROM all_tab_columns 
            WHERE owner = :schema AND table_name = :tbl
            ORDER BY column_id
        """, schema=SCHEMA, tbl=table_name)
        
        columns = cur.fetchall()
        
        if not columns:
            print(f"⚠ Таблица {SCHEMA}.{table_name} не найдена или нет доступа")
            continue
        
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
        
        # 2. Получаем количество строк
        cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.{table_name}")
        count = cur.fetchone()[0]
        print(f"\nВсего строк: {count}")
        
        # 3. Выводим данные (только 5 записей)
        if count > 0:
            print("\nСодержимое (первые 5 строк):")
            
            cols_str = ", ".join([f'"{c}"' for c in col_names])
            sql = f"""
                SELECT {cols_str} 
                FROM (
                    SELECT {cols_str} FROM {SCHEMA}.{table_name}
                )
                WHERE ROWNUM <= 5
            """
            
            try:
                cur.execute(sql)
                rows = cur.fetchall()
                
                for i, row in enumerate(rows):
                    print(f"  [{i+1}] ", end="")
                    vals = []
                    for val in row:
                        if val is None:
                            vals.append("NULL")
                        elif isinstance(val, datetime.datetime):
                            vals.append(val.strftime('%Y-%m-%d %H:%M:%S'))
                        elif isinstance(val, datetime.date):
                            vals.append(val.strftime('%Y-%m-%d'))
                        elif isinstance(val, cx_Oracle.LOB):
                            content = val.read()
                            if isinstance(content, bytes):
                                content = content.decode('utf-8', errors='replace')
                            full_len = len(content)
                            display_content = content[:50] + "..." if full_len > 50 else content
                            vals.append(f"[LOB:{full_len}] {display_content}")
                        else:
                            vals.append(str(val))
                    print(", ".join(vals))
                    
                if count > 5:
                    print(f"  ... и еще {count - 5} строк (не показаны)")
            except Exception as e:
                print(f"  ⚠ Ошибка чтения данных: {e}")
        else:
            print("  (Таблица пуста)")
            
        print("-" * 60)

    conn.close()
    print("\n✓ ВСЕ ДАННЫЕ ВЫВЕДЕНЫ")
    
except Exception as e:
    print(f"✗ CRITICAL ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)