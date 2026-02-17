#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migrate water_data and soil_data from SQLite to Neon PostgreSQL
With proper column mapping and error handling
"""
import sqlite3
import psycopg2
import os
import sys
from time import time

# === 1. เชื่อมต่อ SQLite ===
sqlite_path = 'kok_data.db'
print(f"🔍 อ่านข้อมูลจาก SQLite: {os.path.abspath(sqlite_path)}")

if not os.path.exists(sqlite_path):
    print(f"❌ ไม่พบไฟล์ฐานข้อมูล: {sqlite_path}")
    sys.exit(1)

sqlite_conn = sqlite3.connect(sqlite_path)
sqlite_cursor = sqlite_conn.cursor()

# === 2. เชื่อมต่อ Neon PostgreSQL (ใช้ Standard endpoint เท่านั้น!) ===
NEON_URL = "postgresql://neondb_owner:npg_Rep9gY1jNnSJ@ep-patient-lake-aikp3l97-pooler.c-4.us-east-1.aws.neon.tech/kokdata-db?sslmode=require&channel_binding=require"

print(f"\n🔗 เชื่อมต่อ Neon (Standard endpoint)...")
try:
    pg_conn = psycopg2.connect(NEON_URL)
    pg_cursor = pg_conn.cursor()
    print("✅ เชื่อมต่อสำเร็จ!")
except Exception as e:
    print(f"❌ ไม่สามารถเชื่อมต่อได้: {e}")
    print("\n💡 วิธีแก้ไข:")
    print("   1. ไปที่ Neon Console → Connection Details")
    print("   2. เลือก 'Standard' endpoint (ไม่มี -pooler)")
    print("   3. คัดลอกและแทนที่ NEON_URL ในสคริปต์นี้")
    sys.exit(1)

# === Helper Function: ตรวจสอบและแมปคอลัมน์ ===
def get_column_mapping(table_name, expected_mapping):
    """ตรวจสอบโครงสร้างตารางและสร้างการแมปคอลัมน์"""
    sqlite_cursor.execute(f"PRAGMA table_info({table_name})")
    raw_columns = [col[1] for col in sqlite_cursor.fetchall()]
    clean_columns = [col.lstrip('\ufeff').strip() for col in raw_columns]
    
    print(f"\n📋 โครงสร้างตาราง {table_name}:")
    print(f"   คอลัมน์จริง: {clean_columns}")
    
    sqlite_cols = []
    pg_cols = []
    for sqlite_name, pg_name in expected_mapping.items():
        found = False
        for col in clean_columns:
            if sqlite_name in col or col in sqlite_name:
                idx = clean_columns.index(col)
                sqlite_cols.append(f'"{raw_columns[idx]}"')
                pg_cols.append(pg_name)
                print(f"   ✅ แมป: '{raw_columns[idx]}' → '{pg_name}'")
                found = True
                break
        if not found:
            print(f"   ⚠️ ไม่พบคอลัมน์ '{sqlite_name}'")
    
    return sqlite_cols, pg_cols

# === Helper Function: ย้ายข้อมูลด้วย error handling ===
def migrate_data(table_name, sqlite_table, pg_table, sqlite_cols, pg_cols):
    """ย้ายข้อมูลจากตารางหนึ่งไปยังอีกตารางหนึ่ง"""
    select_query = f'SELECT {", ".join(sqlite_cols)} FROM {sqlite_table}'
    print(f"\n📤 คำสั่ง SELECT: {select_query}")
    
    sqlite_cursor.execute(select_query)
    rows = sqlite_cursor.fetchall()
    total = len(rows)
    
    if total == 0:
        print(f"⚠️ ไม่พบข้อมูลในตาราง {table_name}")
        return 0, 0
    
    print(f"📊 พบ {total:,} แถว กำลังย้ายข้อมูล...")
    
    start_time = time()
    success_count = 0
    error_count = 0
    batch_size = 50
    
    for i, row in enumerate(rows):
        try:
            # ทำความสะอาดและแปลงข้อมูล
            cleaned_row = []
            for idx, val in enumerate(row):
                pg_col = pg_cols[idx] if idx < len(pg_cols) else None
                
                if val is None:
                    cleaned_row.append(None)
                elif isinstance(val, str):
                    cleaned_val = val.strip()
                    # แปลงค่าตัวเลขสำหรับคอลัมน์ที่ต้องการ
                    if pg_col in ['numeric_value'] and cleaned_val not in ['', 'ND', '-', 'ไม่มีข้อมูล', 'ไม่พบ']:
                        try:
                            if cleaned_val.startswith('<'):
                                cleaned_row.append(float(cleaned_val[1:]))
                            elif cleaned_val.startswith('>'):
                                cleaned_row.append(float(cleaned_val[1:]))
                            else:
                                cleaned_row.append(float(cleaned_val))
                            continue
                        except:
                            cleaned_row.append(None)
                    else:
                        cleaned_row.append(cleaned_val if cleaned_val else None)
                else:
                    cleaned_row.append(val)
            
            # สร้างคำสั่ง INSERT
            placeholders = ', '.join(['%s'] * len(pg_cols))
            columns_str = ', '.join(pg_cols)
            insert_query = f'INSERT INTO {pg_table} ({columns_str}) VALUES ({placeholders})'
            
            # ใช้ SAVEPOINT สำหรับจัดการข้อผิดพลาดทีละแถว
            pg_cursor.execute("SAVEPOINT migrate_row")
            pg_cursor.execute(insert_query, cleaned_row)
            pg_cursor.execute("RELEASE SAVEPOINT migrate_row")
            success_count += 1
            
        except Exception as e:
            # Rollback เฉพาะแถวที่ผิดพลาด
            try:
                pg_cursor.execute("ROLLBACK TO SAVEPOINT migrate_row")
            except:
                pass
            error_count += 1
            if error_count <= 3:
                print(f"\n⚠️ แถว {i+1} ผิดพลาด: {str(e)[:70]}")
        
        # Commit ทุกๆ batch_size แถว
        if (i + 1) % batch_size == 0:
            pg_conn.commit()
            elapsed = time() - start_time
            eta = elapsed / (i + 1) * (total - i - 1) if i > 0 else 0
            print(f"   ย้ายแล้ว {i+1}/{total} แถว (สำเร็จ: {success_count}, ผิดพลาด: {error_count}) - ETA: {eta:.0f} วินาที", end='\r')
    
    pg_conn.commit()
    elapsed = time() - start_time
    
    print(f"\n✅ ย้ายข้อมูล {table_name} สำเร็จ {success_count:,}/{total:,} แถว (ผิดพลาด: {error_count}) ใน {elapsed:.1f} วินาที")
    return success_count, error_count

# === 3. สร้างตาราง water_data ===
print("\n" + "="*60)
print("💧 สร้างตาราง water_data...")
print("="*60)

pg_cursor.execute("""
CREATE TABLE IF NOT EXISTS water_data (
    id SERIAL PRIMARY KEY,
    parameter TEXT NOT NULL,
    location TEXT,
    check_number TEXT NOT NULL,
    value TEXT,
    numeric_value NUMERIC,
    unit TEXT,
    station TEXT NOT NULL
)
""")
pg_conn.commit()
print("✅ สร้างตารางเรียบร้อย")

# ตรวจสอบโครงสร้างและแมปคอลัมน์
water_mapping = {
    'สิ่งที่ตรวจ': 'parameter',  # ✅ ใช้ "สิ่งที่ตรวจ" (ไม่ใช้ "รายการ")
    'ที่ตั้ง': 'location',
    'ครั้งที่ตรวจ': 'check_number',
    'ค่าที่วัดได้': 'numeric_value',
    'หน่วย': 'unit' ,
    'สถานี': 'station'
}

sqlite_water_cols, pg_water_cols = get_column_mapping('water_data', water_mapping)

# ย้ายข้อมูล water_data
water_success, water_errors = migrate_data(
    'water_data',
    'water_data',
    'water_data',
    sqlite_water_cols,
    pg_water_cols
)

# === 4. สร้างตาราง soil_data ===
print("\n" + "="*60)
print("🌱 สร้างตาราง soil_data...")
print("="*60)

pg_cursor.execute("""
CREATE TABLE IF NOT EXISTS soil_data (
    id SERIAL PRIMARY KEY,
    parameter TEXT NOT NULL,
    location TEXT,
    check_number TEXT NOT NULL,
    value TEXT,
    numeric_value NUMERIC,
    station TEXT NOT NULL
)
""")
pg_conn.commit()
print("✅ สร้างตารางเรียบร้อย")

# ตรวจสอบโครงสร้างและแมปคอลัมน์
soil_mapping = {
    'สารที่ตรวจ': 'parameter',  # ✅ ใช้ "สารที่ตรวจ" (ไม่ใช้ "รายการ")
    'บริเวณจุดเก็บ': 'location',
    'ครั้งที่ตรวจ': 'check_number',
    'ค่าที่วัดได้': 'numeric_value',
    'สถานี': 'station'
}

sqlite_soil_cols, pg_soil_cols = get_column_mapping('soil_data', soil_mapping)

# ย้ายข้อมูล soil_data
soil_success, soil_errors = migrate_data(
    'soil_data',
    'soil_data',
    'soil_data',
    sqlite_soil_cols,
    pg_soil_cols
)

# === 5. ตรวจสอบผลลัพธ์ ===
print("\n" + "="*60)
print("📊 สรุปผลการย้ายข้อมูล:")
print("="*60)

print(f"   water_data: {water_success:,} แถว (ผิดพลาด: {water_errors})")
print(f"   soil_data:  {soil_success:,} แถว (ผิดพลาด: {soil_errors})")

# ตรวจสอบในฐานข้อมูล
print("\n🔍 ตรวจสอบในฐานข้อมูล Neon:")

pg_cursor.execute("SELECT COUNT(*) FROM water_data")
water_count = pg_cursor.fetchone()[0]
print(f"   water_data: {water_count:,} แถว")

pg_cursor.execute("SELECT COUNT(*) FROM soil_data")
soil_count = pg_cursor.fetchone()[0]
print(f"   soil_data:  {soil_count:,} แถว")

# แสดงตัวอย่างข้อมูล
print("\n📋 ตัวอย่างข้อมูล 3 แถวแรกจาก water_data:")
pg_cursor.execute("""
    SELECT station, parameter, check_number, value, numeric_value, unit 
    FROM water_data 
    ORDER BY id 
    LIMIT 3
""")
for row in pg_cursor.fetchall():
    print(f"   {row}")

print("\n📋 ตัวอย่างข้อมูล 3 แถวแรกจาก soil_data:")
pg_cursor.execute("""
    SELECT station, parameter, check_number, value, numeric_value 
    FROM soil_data 
    ORDER BY id 
    LIMIT 3
""")
for row in pg_cursor.fetchall():
    print(f"   {row}")

# ปิดการเชื่อมต่อ
sqlite_conn.close()
pg_conn.close()

print("\n" + "="*60)
print("🎉 การย้ายข้อมูลทั้งหมดเสร็จสมบูรณ์!")
print("="*60)
print("\n💡 คำแนะนำต่อไป:")
print("   1. Deploy แอปใหม่: fly deploy --app kokdata-newversion")
print("   2. ทดสอบเว็บ: https://kokdata-newversion.fly.dev")
print("   3. ตรวจสอบข้อมูลน้ำและดินในแต่ละสถานี")