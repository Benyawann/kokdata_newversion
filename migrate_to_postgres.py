#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration script from SQLite to PostgreSQL (Neon) - FIXED VERSION
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_batch, RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()

SQLITE_DB_PATH = 'kok_data.db'
POSTGRES_CONNECTION_STRING = os.environ.get('DATABASE_URL')
if not POSTGRES_CONNECTION_STRING:
    raise ValueError("DATABASE_URL not set. Please check your .env file")

def get_sqlite_connection():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_postgres_connection():
    conn = psycopg2.connect(POSTGRES_CONNECTION_STRING)
    return conn

def create_postgres_tables(conn):
    print("📊 Creating tables in PostgreSQL...")
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS station_data (
                id SERIAL PRIMARY KEY,
                station TEXT UNIQUE NOT NULL,
                river TEXT, tambon TEXT, amphoe TEXT, province TEXT, location TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS water_data (
                id SERIAL PRIMARY KEY,
                station_id INTEGER REFERENCES station_data(id) ON DELETE CASCADE,
                parameter TEXT, unit TEXT, location TEXT,
                check_number TEXT, value TEXT, numeric_value REAL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS soil_data (
                id SERIAL PRIMARY KEY,
                station_id INTEGER REFERENCES station_data(id) ON DELETE CASCADE,
                parameter TEXT, location TEXT,
                check_number TEXT, value TEXT, numeric_value REAL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_water_station ON water_data(station_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_soil_station ON soil_data(station_id)")
    conn.commit()
    print("✅ Tables created successfully")

def migrate_users(sqlite_conn, postgres_conn):
    print("👤 Migrating users...")
    sqlite_cur = sqlite_conn.cursor()
    postgres_cur = postgres_conn.cursor()
    sqlite_cur.execute("SELECT * FROM users")
    users = sqlite_cur.fetchall()
    if users:
        execute_batch(postgres_cur, """
            INSERT INTO users (username, password) VALUES (%s, %s)
            ON CONFLICT (username) DO NOTHING
        """, [(user['username'], user['password']) for user in users])
        postgres_conn.commit()
        print(f"   ✅ Migrated {len(users)} users")
    else:
        print("   ℹ️  No users to migrate")

def migrate_stations(sqlite_conn, postgres_conn):
    """Migrate stations และสร้าง mapping: {sqlite_id: postgres_id, station_code: postgres_id}"""
    print("🏭 Migrating stations...")
    sqlite_cur = sqlite_conn.cursor()
    postgres_cur = postgres_conn.cursor()
    
    sqlite_cur.execute("""
        SELECT id, "สถานี", "\ufeffแม่น้ำ", "ตำบล", "อำเภอ", "จังหวัด", "บริเวณที่เก็บ"
        FROM station_data
    """)
    stations = sqlite_cur.fetchall()
    
    if stations:
        # สร้าง mapping 2 แบบ: ใช้ id และใช้ station code
        id_mapping = {}      # {sqlite_id: postgres_id}
        code_mapping = {}    # {station_code: postgres_id}
        
        for station in stations:
            station_dict = dict(station)
            for key, val in station_dict.items():
                if isinstance(val, str):
                    station_dict[key] = val.strip()
            
            postgres_cur.execute("""
                INSERT INTO station_data (station, river, tambon, amphoe, province, location)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (station) DO UPDATE SET
                    river = EXCLUDED.river, tambon = EXCLUDED.tambon,
                    amphoe = EXCLUDED.amphoe, province = EXCLUDED.province,
                    location = EXCLUDED.location
                RETURNING id
            """, (
                station_dict['สถานี'], station_dict['\ufeffแม่น้ำ'],
                station_dict['ตำบล'], station_dict['อำเภอ'],
                station_dict['จังหวัด'], station_dict['บริเวณที่เก็บ']
            ))
            
            new_id = postgres_cur.fetchone()[0]
            id_mapping[station['id']] = new_id
            code_mapping[station_dict['สถานี']] = new_id  # เพิ่ม mapping ด้วยชื่อสถานี
        
        postgres_conn.commit()
        print(f"   ✅ Migrated {len(stations)} stations")
        return id_mapping, code_mapping
    else:
        print("   ℹ️  No stations to migrate")
        return {}, {}

def migrate_water_data(sqlite_conn, postgres_conn, code_mapping):
    """Migrate water_data โดยใช้ station code หา id_mapping"""
    print("💧 Migrating water data...")
    sqlite_cur = sqlite_conn.cursor()
    postgres_cur = postgres_conn.cursor()
    
    sqlite_cur.execute("""
        SELECT "สถานี", "\ufeffสิ่งที่ตรวจ", "หน่วย", "ที่ตั้ง", "ครั้งที่ตรวจ", "ค่าที่ได้", "ค่าที่วัดได้"
        FROM water_data
    """)
    water_data = sqlite_cur.fetchall()
    
    if water_data:
        batch_data = []
        for row in water_data:
            row_dict = dict(row)
            for key, val in row_dict.items():
                if isinstance(val, str):
                    row_dict[key] = val.strip()
            
            station_code = row_dict['สถานี']
            new_station_id = code_mapping.get(station_code)
            
            if new_station_id:
                batch_data.append((
                    new_station_id,
                    row_dict['\ufeffสิ่งที่ตรวจ'],
                    row_dict['หน่วย'],
                    row_dict['ที่ตั้ง'],
                    row_dict['ครั้งที่ตรวจ'],
                    row_dict['ค่าที่ได้'],
                    row_dict['ค่าที่วัดได้']
                ))
        
        execute_batch(postgres_cur, """
            INSERT INTO water_data 
            (station_id, parameter, unit, location, check_number, value, numeric_value)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, batch_data, page_size=1000)
        
        postgres_conn.commit()
        print(f"   ✅ Migrated {len(batch_data)} water data records")
    else:
        print("   ℹ️  No water data to migrate")

def migrate_soil_data(sqlite_conn, postgres_conn, code_mapping):
    """Migrate soil_data โดยใช้ station code หา id_mapping"""
    print("🌱 Migrating soil data...")
    sqlite_cur = sqlite_conn.cursor()
    postgres_cur = postgres_conn.cursor()
    
    sqlite_cur.execute("""
        SELECT "สถานี", "สารที่ตรวจ", "บริเวณจุดเก็บ", "ครั้งที่ตรวจ", "ค่าที่ได้", "ค่าที่วัดได้"
        FROM soil_data
    """)
    soil_data = sqlite_cur.fetchall()
    
    if soil_data:
        batch_data = []
        for row in soil_data:
            row_dict = dict(row)
            for key, val in row_dict.items():
                if isinstance(val, str):
                    row_dict[key] = val.strip()
            
            station_code = row_dict['สถานี']
            new_station_id = code_mapping.get(station_code)
            
            if new_station_id:
                batch_data.append((
                    new_station_id,
                    row_dict['สารที่ตรวจ'],
                    row_dict['บริเวณจุดเก็บ'],
                    row_dict['ครั้งที่ตรวจ'],
                    row_dict['ค่าที่ได้'],
                    row_dict['ค่าที่วัดได้']
                ))
        
        execute_batch(postgres_cur, """
            INSERT INTO soil_data 
            (station_id, parameter, location, check_number, value, numeric_value)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, batch_data, page_size=1000)
        
        postgres_conn.commit()
        print(f"   ✅ Migrated {len(batch_data)} soil data records")
    else:
        print("   ℹ️  No soil data to migrate")

def verify_migration(sqlite_conn, postgres_conn):
    print("\n🔍 Verifying migration...")
    sqlite_cur = sqlite_conn.cursor()
    postgres_cur = postgres_conn.cursor()
    
    tables = ['station_data', 'water_data', 'soil_data', 'users']
    for table in tables:
        sqlite_cur.execute(f"SELECT COUNT(*) FROM {table}")
        sqlite_count = sqlite_cur.fetchone()[0]
        postgres_cur.execute(f"SELECT COUNT(*) FROM {table}")
        postgres_count = postgres_cur.fetchone()[0]
        status = "✅" if sqlite_count == postgres_count else "❌"
        print(f"   {status} {table}: SQLite={sqlite_count}, PostgreSQL={postgres_count}")

def main():
    print("=" * 60)
    print("🚀 Starting SQLite to PostgreSQL Migration")
    print("=" * 60)
    
    try:
        print("\n📡 Connecting to databases...")
        sqlite_conn = get_sqlite_connection()
        postgres_conn = get_postgres_connection()
        print("   ✅ Connected successfully")
        
        create_postgres_tables(postgres_conn)
        migrate_users(sqlite_conn, postgres_conn)
        
        # รับ mapping 2 แบบ
        id_mapping, code_mapping = migrate_stations(sqlite_conn, postgres_conn)
        
        # ใช้ code_mapping สำหรับ migrate ข้อมูลน้ำและดิน
        migrate_water_data(sqlite_conn, postgres_conn, code_mapping)
        migrate_soil_data(sqlite_conn, postgres_conn, code_mapping)
        
        verify_migration(sqlite_conn, postgres_conn)
        
        sqlite_conn.close()
        postgres_conn.close()
        
        print("\n" + "=" * 60)
        print("✅ Migration completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")
        raise

if __name__ == '__main__':
    main()