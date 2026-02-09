import sqlite3
import psycopg2
import pandas as pd
from psycopg2 import sql

# === การตั้งค่า ===
SQLITE_DB_PATH = "kok_data.db"  # เปลี่ยนเป็นชื่อไฟล์ SQLite ของคุณ
PG_HOST = "localhost"
PG_PORT = 5432
PG_DB = "postgres"             # ชื่อฐานข้อมูล PostgreSQL (ต้องสร้างไว้ก่อน)
PG_USER = "postgres"
PG_PASSWORD = "password123"       # รหัสผ่านที่คุณตั้งไว้

# === 1. เชื่อมต่อฐานข้อมูล ===
sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
pg_conn = psycopg2.connect(
    host=PG_HOST,
    port=PG_PORT,
    database=PG_DB,
    user=PG_USER,
    password=PG_PASSWORD
)
pg_conn.autocommit = True
pg_cursor = pg_conn.cursor()

# === 2. ดึงรายชื่อตารางจาก SQLite ===
sqlite_cursor = sqlite_conn.cursor()
sqlite_cursor.execute("""
    SELECT name FROM sqlite_master 
    WHERE type='table' AND name NOT LIKE 'sqlite_%'
""")
tables = [row[0] for row in sqlite_cursor.fetchall()]

print(f"พบตารางทั้งหมด {len(tables)} ตาราง: {tables}")

# === 3. ย้ายข้อมูลทีละตาราง ===
for table_name in tables:
    print(f"\nกำลังย้ายข้อมูลตาราง: {table_name}")
    
    # ดึงข้อมูลจาก SQLite
    df = pd.read_sql_query(f"SELECT * FROM {table_name}", sqlite_conn)
    print(f"  - จำนวนแถว: {len(df)}")
    
    if df.empty:
        print(f"  ⚠️  ตารางว่าง ข้าม...")
        continue
    
    # สร้างตารางใน PostgreSQL (ถ้ายังไม่มี)
    columns = []
    for col, dtype in zip(df.columns, df.dtypes):
        if dtype == 'int64':
            pg_type = 'BIGINT'
        elif dtype == 'float64':
            pg_type = 'DOUBLE PRECISION'
        elif dtype == 'bool':
            pg_type = 'BOOLEAN'
        else:
            pg_type = 'TEXT'  # ใช้ TEXT สำหรับ string, datetime ฯลฯ
        
        # จัดการชื่อคอลัมน์ที่เป็นคำสงวนใน PostgreSQL
        safe_col = f'"{col}"' if col.lower() in ['user', 'order', 'group'] else col
        columns.append(f"{safe_col} {pg_type}")
    
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        {', '.join(columns)}
    )
    """
    pg_cursor.execute(create_table_sql)
    print(f"  - สร้างตารางแล้ว")
    
    # ลบข้อมูลเก่า (ถ้ามี) เพื่อป้องกันการซ้ำ
    pg_cursor.execute(f"DELETE FROM {table_name}")
    
    # นำเข้าข้อมูล
    if not df.empty:
        # แปลงค่า NaN/None เป็นค่าว่าง
        df = df.where(pd.notnull(df), None)
        
        # สร้างคำสั่ง INSERT
        cols = ', '.join([f'"{col}"' if col.lower() in ['user', 'order', 'group'] else col for col in df.columns])
        values_placeholder = ', '.join(['%s'] * len(df.columns))
        insert_sql = f"INSERT INTO {table_name} ({cols}) VALUES ({values_placeholder})"
        
        # ส่งข้อมูลทีละแถว
        for _, row in df.iterrows():
            pg_cursor.execute(insert_sql, tuple(row))
        
        print(f"  ✅ นำเข้าข้อมูล {len(df)} แถว เสร็จสิ้น")

# === 4. ปิดการเชื่อมต่อ ===
sqlite_conn.close()
pg_conn.close()

print("\n🎉 การย้ายข้อมูลเสร็จสมบูรณ์!")