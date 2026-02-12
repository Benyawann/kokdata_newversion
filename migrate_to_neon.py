#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migrate data from SQLite (local) to Neon PostgreSQL
"""
import sqlite3
import psycopg2
import os

# === 1. เชื่อมต่อ SQLite (ในเครื่องคุณ) ===
sqlite_path = 'kok_data.db'
print(f"🔍 อ่านข้อมูลจาก SQLite: {os.path.abspath(sqlite_path)}")
print(f"ไฟล์มีอยู่: {os.path.exists(sqlite_path)}")

sqlite_conn = sqlite3.connect(sqlite_path)
sqlite_cursor = sqlite_conn.cursor()

# ตรวจสอบโครงสร้างตาราง
sqlite_cursor.execute("PRAGMA table_info(station_data)")
columns = [col[1] for col in sqlite_cursor.fetchall()]
print(f"โครงสร้างคอลัมน์ SQLite: {columns}")

# === 2. เชื่อมต่อ Neon PostgreSQL ===
# แทนที่ด้วย Connection String ใหม่ที่คัดลอกจาก Neon Dashboard
NEON_URL = "postgresql://neondb_owner:npg_Rep9gY1jNnSJ@ep-patient-lake-aikp3l97-pooler.c-4.us-east-1.aws.neon.tech/kokdata-db?sslmode=require"

# หรือแยกเป็นตัวแปร (ถ้าไม่สะดวกใช้ URL):
# NEON_HOST = "ep-xxx-xxx.aws.neon.tech"
# NEON_PORT = 5432
# NEON_DATABASE = "kokdata-db"
# NEON_USER = "neondb_owner"
# NEON_PASSWORD = "YOUR_PASSWORD"

pg_conn = psycopg2.connect(NEON_URL)
pg_cursor = pg_conn.cursor()

# สร้างตารางถ้ายังไม่มี
pg_cursor.execute("""
CREATE TABLE IF NOT EXISTS station_data (
    id SERIAL PRIMARY KEY,
    river TEXT,
    station TEXT UNIQUE NOT NULL,
    location TEXT,
    tambon TEXT,
    amphoe TEXT,
    province TEXT
)
""")
pg_conn.commit()
print("✅ สร้างตาราง station_data ใน Neon เรียบร้อย")

# === 3. ย้ายข้อมูล ===
print("\n🚀 เริ่มย้ายข้อมูล...")
sqlite_cursor.execute('SELECT "แม่น้ำ", "สถานี", "บริเวณที่เก็บ", "ตำบล", "อำเภอ", "จังหวัด" FROM station_data')
rows = sqlite_cursor.fetchall()
print(f"พบ {len(rows)} แถวใน SQLite")

success_count = 0
for i, row in enumerate(rows):
    try:
        cleaned_row = [val.strip() if isinstance(val, str) else val for val in row]
        
        pg_cursor.execute(
            'INSERT INTO station_data (river, station, location, tambon, amphoe, province) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (station) DO NOTHING',
            cleaned_row
        )
        success_count += 1
        if (i + 1) % 10 == 0:
            print(f"✓ ย้ายแล้ว {i+1}/{len(rows)} แถว")
    except Exception as e:
        print(f"❌ ข้อผิดพลาดแถวที่ {i+1}: {e}")
        print(f"   ข้อมูล: {row}")
        pg_conn.rollback()
        break
else:
    pg_conn.commit()
    print(f"\n✅ ย้ายข้อมูลสำเร็จทั้งหมด {success_count} แถว!")

# ปิดการเชื่อมต่อ
sqlite_conn.close()
pg_conn.close()
print("\n🎉 การย้ายข้อมูลเสร็จสมบูรณ์!")