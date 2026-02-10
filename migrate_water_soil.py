import sqlite3
import psycopg2

# เชื่อมต่อฐานข้อมูล
sqlite_conn = sqlite3.connect('kok_data.db')
pg_conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='postgres',
    user='postgres',
    password='password123'
)

sqlite_cursor = sqlite_conn.cursor()
pg_cursor = pg_conn.cursor()

print("🔍 ตรวจสอบข้อมูลใน SQLite...")
sqlite_cursor.execute('SELECT COUNT(*) FROM water_data')
water_count = sqlite_cursor.fetchone()[0]
print(f"water_data ใน SQLite: {water_count} แถว")

sqlite_cursor.execute('SELECT COUNT(*) FROM soil_data')
soil_count = sqlite_cursor.fetchone()[0]
print(f"soil_data ใน SQLite: {soil_count} แถว")

if water_count > 0:
    print("🚀 กำลังย้ายข้อมูล water_data...")
    sqlite_cursor.execute('SELECT "\ufeffสิ่งที่ตรวจ", "ที่ตั้ง", "ครั้งที่ตรวจ", "ค่าที่ได้", "ค่าที่วัดได้", "หน่วย", "สถานี" FROM water_data')
    
    for i, row in enumerate(sqlite_cursor.fetchall()):
        try:
            pg_cursor.execute(
                'INSERT INTO water_data (parameter, location, check_number, value, numeric_value, unit, station) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                row
            )
            if (i + 1) % 500 == 0:
                print(f"✓ ย้าย water_data แล้ว {i + 1} แถว")
        except Exception as e:
            print(f"❌ ERROR water_data แถว {i + 1}: {e}")
            break
    
    pg_conn.commit()
    print("✅ ย้าย water_data เสร็จ!")

if soil_count > 0:
    print("🚀 กำลังย้ายข้อมูล soil_data...")
    sqlite_cursor.execute('SELECT "สารที่ตรวจ", "บริเวณจุดเก็บ", "ครั้งที่ตรวจ", "ค่าที่ได้", "ค่าที่วัดได้", "สถานี" FROM soil_data')
    
    for i, row in enumerate(sqlite_cursor.fetchall()):
        try:
            pg_cursor.execute(
                'INSERT INTO soil_data (parameter, location, check_number, value, numeric_value, station) VALUES (%s, %s, %s, %s, %s, %s)',
                row
            )
            if (i + 1) % 200 == 0:
                print(f"✓ ย้าย soil_data แล้ว {i + 1} แถว")
        except Exception as e:
            print(f"❌ ERROR soil_data แถว {i + 1}: {e}")
            break
    
    pg_conn.commit()
    print("✅ ย้าย soil_data เสร็จ!")

sqlite_conn.close()
pg_conn.close()
print("🎉 ย้ายข้อมูลทั้งหมดเสร็จสมบูรณ์!")