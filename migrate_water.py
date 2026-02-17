import sqlite3
import psycopg2
import sys

def safe_strip(val):
    if val is None:
        return ''
    if isinstance(val, str):
        return val.strip()
    return str(val).strip()

# === 1. เชื่อมต่อ SQLite ===
sqlite_conn = sqlite3.connect('kok_data.db')
sqlite_cursor = sqlite_conn.cursor()

# === 2. เชื่อมต่อ Neon (Standard endpoint) ===
NEON_URL = "postgresql://neondb_owner:npg_Rep9gY1jNnSJ@ep-patient-lake-aikp3l97-pooler.c-4.us-east-1.aws.neon.tech/kokdata-db?sslmode=require&channel_binding=require"
pg_conn = psycopg2.connect(NEON_URL)
pg_cursor = pg_conn.cursor()

# === 3. สร้างตาราง water_data ===
pg_cursor.execute("""
CREATE TABLE IF NOT EXISTS water_data (
    id SERIAL PRIMARY KEY,
    parameter TEXT NOT NULL,
    station TEXT NOT NULL,  
    location TEXT,
    check_number TEXT NOT NULL,
    value TEXT,
    numeric_value NUMERIC,
    unit TEXT
)
""")
pg_conn.commit()

# แมปคอลัมน์ให้ตรงกับโครงสร้างจริง (ปรับตามโครงสร้างจริงของคุณ)
column_mapping = {
    'สิ่งที่ตรวจ': 'parameter',      
    'สถานี': 'station',
    'ที่ตั้ง': 'location',    
    'ครั้งที่ตรวจ': 'check_number', 
    'ค่าที่ได้': 'value',          
    'ค่าที่วัดได้': 'numeric_value', 
    'หน่วย': 'unit'
}

# === 4. ดึงข้อมูลจาก water_data (ใช้คอลัมน์ "สิ่งที่ตรวจ") ===
sqlite_cursor.execute("""
    SELECT 
        "สิ่งที่ตรวจ", 
        "สถานี",  
        "ที่ตั้ง",
        "ครั้งที่ตรวจ",
        "ค่าที่ได้",
        "ค่าที่วัดได้",
        "หน่วย"
    FROM water_data
""")
rows = sqlite_cursor.fetchall()
print(f"📊 พบ {len(rows)} แถว จาก water_data")

# === 5. ย้ายข้อมูล ===
success_count = 0
for i, row in enumerate(rows):
    try:
        # แปลง numeric_value อย่างปลอดภัย
        numeric_val = None
        if row[5] is not None:
            val_str = str(row[5]).strip()
            if val_str and val_str not in ['ND', '-', '']:
                try:
                    if val_str.startswith('<'):
                        numeric_val = float(val_str[1:])
                    elif val_str.startswith('>'):
                        numeric_val = float(val_str[1:])
                    else:
                        numeric_val = float(val_str)
                except:
                    numeric_val = None
        
        pg_cursor.execute("""
            INSERT INTO water_data (station, parameter, location, check_number, value, numeric_value, unit)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            safe_strip(row[0]),   # station
            safe_strip(row[1]),   # parameter ← ค่าจริง: pH, DO, BOD
            safe_strip(row[2]),   # location (อาจเป็นค่าว่าง)
            safe_strip(row[3]),   # check_number
            safe_strip(row[4]),   # value
            numeric_val,          # numeric_value
            safe_strip(row[6])    # unit
        ))
        success_count += 1
        
        if (i + 1) % 100 == 0:
            pg_conn.commit()
            print(f"   ย้ายแล้ว {i+1}/{len(rows)} แถว")
            
    except Exception as e:
        print(f"⚠️ ข้ามแถว {i+1}: {e}")

pg_conn.commit()
print(f"✅ ย้ายข้อมูลสำเร็จ {success_count}/{len(rows)} แถว!")

# === 6. ตรวจสอบผลลัพธ์ ===
pg_cursor.execute("SELECT parameter, value FROM water_data LIMIT 5")
for row in pg_cursor.fetchall():
    print(f"parameter: '{row[0]}', value: '{row[1]}'")

sqlite_conn.close()
pg_conn.close()
print("🎉 การย้ายข้อมูล water_data เสร็จสมบูรณ์!")