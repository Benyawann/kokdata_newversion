#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migrate soil_data with CORRECT column mapping and robust error handling
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

# === 2. เชื่อมต่อ Neon PostgreSQL (Standard endpoint เท่านั้น!) ===
NEON_URL = "postgresql://neondb_owner:npg_Rep9gY1jNnSJ@ep-patient-lake-aikp3l97-pooler.c-4.us-east-1.aws.neon.tech/kokdata-db?sslmode=require&channel_binding=require"

print(f"\n🔗 เชื่อมต่อ Neon...")
try:
    pg_conn = psycopg2.connect(NEON_URL)
    pg_cursor = pg_conn.cursor()
    print("✅ เชื่อมต่อสำเร็จ!")
except Exception as e:
    print(f"❌ ไม่สามารถเชื่อมต่อได้: {e}")
    sys.exit(1)

# === 3. สร้างตาราง soil_data ===
print("\n🌱 สร้างตาราง soil_data...")
pg_cursor.execute("""
CREATE TABLE IF NOT EXISTS soil_data (
    id SERIAL PRIMARY KEY,
    station TEXT NOT NULL,
    parameter TEXT NOT NULL,
    location TEXT,
    check_number TEXT NOT NULL,
    value TEXT,
    numeric_value NUMERIC
)
""")
pg_conn.commit()
print("✅ สร้างตารางเรียบร้อย")

# === 4. ตรวจสอบโครงสร้างจริงของ soil_data ใน SQLite ===
print("\n📋 ตรวจสอบโครงสร้างตาราง soil_data ใน SQLite...")
sqlite_cursor.execute("PRAGMA table_info(soil_data)")
columns = [col[1].lstrip('\ufeff').strip() for col in sqlite_cursor.fetchall()]
print(f"   คอลัมน์จริง: {columns}")

# แมปคอลัมน์ให้ตรงกับโครงสร้างจริง (ปรับตามโครงสร้างจริงของคุณ)
column_mapping = {
    'สารที่ตรวจ': 'parameter',      # หรือ 'รายการ' ขึ้นกับโครงสร้างจริง
    'สถานี': 'station',
    'บริเวณจุดเก็บ': 'location',    # หรือ 'ที่ตั้ง'
    'ครั้งที่ตรวจ': 'check_number', # หรือ 'ครั้งที่วัด'
    'ค่าที่ได้': 'value',           # ข้อความที่แสดงผล
    'ค่าที่วัดได้': 'numeric_value' # ค่าตัวเลขสำหรับการคำนวณ
}

# สร้างรายการคอลัมน์สำหรับ SELECT และ INSERT
sqlite_cols = []
pg_cols = []
for sqlite_col, pg_col in column_mapping.items():
    # ค้นหาคอลัมน์ที่ตรงหรือใกล้เคียงที่สุด
    found = False
    for col in columns:
        if sqlite_col == col or sqlite_col in col or col in sqlite_col:
            sqlite_cols.append(f'"{col}"')
            pg_cols.append(pg_col)
            found = True
            print(f"   ✅ แมป: '{col}' → '{pg_col}'")
            break
    if not found:
        print(f"   ⚠️ ไม่พบคอลัมน์ '{sqlite_col}' - ข้ามคอลัมน์นี้")

if not sqlite_cols:
    print("❌ ไม่พบคอลัมน์ที่ตรงกัน ตรวจสอบโครงสร้างตารางอีกครั้ง")
    sys.exit(1)

# === 5. ย้ายข้อมูลด้วยการจัดการข้อผิดพลาดทีละแถว ===
sqlite_cursor.execute(f'SELECT {", ".join(sqlite_cols)} FROM soil_data')
rows = sqlite_cursor.fetchall()
total = len(rows)
print(f"\n📊 พบ {total:,} แถว กำลังย้ายข้อมูล...")

start_time = time()
success_count = 0
error_count = 0
batch_size = 50

for i, row in enumerate(rows):
    try:
        # ทำความสะอาดข้อมูลและแปลงค่าตัวเลข
        cleaned_row = []
        for idx, val in enumerate(row):
            pg_col = pg_cols[idx] if idx < len(pg_cols) else None
            
            if val is None:
                cleaned_row.append(None)
            elif isinstance(val, str):
                cleaned_val = val.strip()
                # แปลงค่าตัวเลขสำหรับคอลัมน์ numeric_value
                if pg_col == 'numeric_value' and cleaned_val not in ['', 'ND', '-', 'ไม่มีข้อมูล', 'ไม่พบ']:
                    try:
                        # จัดการค่าที่มีเครื่องหมาย < เช่น "<0.01"
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
        query = f'INSERT INTO soil_data ({columns_str}) VALUES ({placeholders})'
        
        # ใช้ savepoint เพื่อจัดการข้อผิดพลาดทีละแถว
        pg_cursor.execute("SAVEPOINT migrate_row")
        pg_cursor.execute(query, cleaned_row)
        pg_cursor.execute("RELEASE SAVEPOINT migrate_row")
        success_count += 1
        
    except Exception as e:
        # Rollback สำหรับแถวที่ผิดพลาดเท่านั้น
        try:
            pg_cursor.execute("ROLLBACK TO SAVEPOINT migrate_row")
        except:
            pass
        error_count += 1
        if error_count <= 5:  # แสดงเฉพาะ 5 ข้อผิดพลาดแรก
            print(f"\n⚠️ แถว {i+1} ผิดพลาด: {str(e)[:80]}")
            print(f"   ข้อมูล: {cleaned_row}")
    
    # Commit ทุกๆ batch_size แถว
    if (i + 1) % batch_size == 0:
        pg_conn.commit()
        elapsed = time() - start_time
        eta = elapsed / (i + 1) * (total - i - 1) if i > 0 else 0
        print(f"   ย้ายแล้ว {i+1}/{total} แถว (สำเร็จ: {success_count}, ผิดพลาด: {error_count}) - ETA: {eta:.0f} วินาที", end='\r')

# Commit ส่วนที่เหลือ
pg_conn.commit()
elapsed = time() - start_time

print(f"\n\n✅ ย้ายข้อมูลสำเร็จ {success_count:,}/{total:,} แถว (ผิดพลาด: {error_count}) ใน {elapsed:.1f} วินาที")

# === 6. ตรวจสอบผลลัพธ์ ===
pg_cursor.execute("SELECT COUNT(*), MIN(id), MAX(id) FROM soil_data")
count, min_id, max_id = pg_cursor.fetchone()
print(f"\n📊 ตรวจสอบในฐานข้อมูล Neon:")
print(f"   จำนวนแถวทั้งหมด: {count:,}")
print(f"   ID ต่ำสุด: {min_id}")
print(f"   ID สูงสุด: {max_id}")

# แสดงตัวอย่างข้อมูล
pg_cursor.execute("""
    SELECT station, parameter, check_number, value, numeric_value 
    FROM soil_data 
    ORDER BY id 
    LIMIT 5
""")
print("\n📋 ตัวอย่างข้อมูล 5 แถวแรก:")
for row in pg_cursor.fetchall():
    print(f"   {row}")

# ปิดการเชื่อมต่อ
sqlite_conn.close()
pg_conn.close()
print("\n🎉 การย้ายข้อมูล soil_data เสร็จสมบูรณ์!")