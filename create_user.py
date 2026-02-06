#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
สร้างตาราง users และเพิ่มผู้ใช้ 'admin' ใน PostgreSQL
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

# ดึง DATABASE_URL จาก environment variable
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("❌ ต้องตั้งค่า environment variable 'DATABASE_URL' ก่อนรันสคริปต์นี้")

print("Using DB:", DATABASE_URL)

try:
    # สร้าง connection กับ PostgreSQL
    with psycopg2.connect(DATABASE_URL) as conn:
        cur = conn.cursor()

        # สร้างตาราง users (ใช้ SERIAL แทน AUTOINCREMENT)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')

        # เพิ่มผู้ใช้ 'admin' (ใช้ %s แทน ?)
        try:
            cur.execute(
                "INSERT INTO users (username, password) VALUES (%s, %s)",
                ("admin", "password123")
            )
            print("✅ สร้างผู้ใช้ 'admin' สำเร็จ!")
        except psycopg2.errors.UniqueViolation:
            print("ℹ️ ผู้ใช้ 'admin' มีอยู่แล้ว")
            conn.rollback()  # สำคัญ: ต้อง rollback เมื่อเกิด error

except Exception as e:
    print(f"❌ เกิดข้อผิดพลาด: {e}")