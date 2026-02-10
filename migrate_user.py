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

print("🚀 ย้ายข้อมูล users...")
sqlite_cursor.execute('SELECT username, password FROM users')
for row in sqlite_cursor.fetchall():
    try:
        pg_cursor.execute(
            'INSERT INTO users (username, password) VALUES (%s, %s)',
            row
        )
        print(f"✓ เพิ่มผู้ใช้: {row[0]}")
    except Exception as e:
        print(f"❌ ERROR: {e}")

pg_conn.commit()
print("✅ ย้ายข้อมูล users เสร็จ!")

sqlite_conn.close()
pg_conn.close()