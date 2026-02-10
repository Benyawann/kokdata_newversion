import sqlite3
import psycopg2

import os
print("SQLite file path:", os.path.abspath('kok_data.db'))
print("File exists:", os.path.exists('kok_data.db'))
print("File size:", os.path.getsize('kok_data.db'), "bytes")
sqlite_conn = sqlite3.connect('kok_data.db')
pg_conn = psycopg2.connect(
    host='127.0.0.1',
    port=5432,
    database='postgres',
    user='postgres',
    password='password123'
)

sqlite_cursor = sqlite_conn.cursor()
pg_cursor = pg_conn.cursor()

print("🔍 ตรวจสอบข้อมูลใน SQLite...")
sqlite_cursor.execute('SELECT COUNT(*) FROM station_data')
count = sqlite_cursor.fetchone()[0]
print(f"มี {count} แถวใน SQLite")

if count > 0:
    print("🚀 ย้ายข้อมูล station_data...")
    sqlite_cursor.execute('SELECT "\ufeffแม่น้ำ", "สถานี", "บริเวณที่เก็บ", "ตำบล", "อำเภอ", "จังหวัด" FROM station_data')
    
    rows = sqlite_cursor.fetchall()
    print(f"จะย้าย {len(rows)} แถว")
    
    for i, row in enumerate(rows):
        try:
            # ปรับชื่อคอลัมน์ให้ตรงกับโครงสร้าง PostgreSQL ของคุณ
            pg_cursor.execute(
                'INSERT INTO station_data (river, station, location, tambon, amphoe, province) VALUES (%s, %s, %s, %s, %s, %s)',
                row
            )
            print(f"✓ แถว {i+1}: {row[1]}")  # แสดงชื่อสถานี
        except Exception as e:
            print(f"❌ ERROR แถว {i+1}: {e}")
            print(f"   ข้อมูล: {row}")
            break
    
    pg_conn.commit()
    print("✅ Commit เรียบร้อย!")
else:
    print("⚠️ ไม่มีข้อมูลใน SQLite")

sqlite_conn.close()
pg_conn.close()