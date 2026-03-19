#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask web application with PostgreSQL (Neon)
"""
# Flask เป็น framework หลักสำหรับสร้างเว็บ
from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
import psycopg2 # ใช้เชื่อมต่อ Database ของ PostgreSQL
from psycopg2.extras import RealDictCursor
import os #ใช้จัดการ Environment Variables เช่น รหัสผ่าน ,URL Database
import secrets #ใช้สร้าง Secret Key ของ Flask
from dotenv import load_dotenv #ใช้จัดการ Environment Variables เช่น รหัสผ่าน ,URL Database
import requests # ใช้ดึงข้อมูลข่าวจากเว็บภายนอก
from bs4 import BeautifulSoup # ใช้ดึงข้อมูลข่าวจากเว็บภายนอก
from datetime import datetime
from functools import lru_cache
import time

load_dotenv()  # โหลดทันทีหลัง import
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(16) #ใช้สำหรับจัดการ Session (การเข้าสู่ระบบ)
app.config['JSON_AS_ASCII'] = False

# === Register API Blueprint ===
from api.index import api_bp
app.register_blueprint(api_bp) #ลงทะเบียน API Blueprint

#  ฟังก์ชันสำหรับสร้างการเชื่อมต่อไปยังฐานข้อมูล โดยใช้ URL จาก SUPABASE_DATABASE_URL
def get_db():
    db_url = os.environ.get('SUPABASE_DATABASE_URL')
    if not db_url:
        raise ValueError("SUPABASE_DATABASE_URL not set in environment")
    conn = psycopg2.connect(db_url)
    conn.cursor_factory = RealDictCursor
    return conn

#ฟังก์ชันสำหรับสร้างตารางฐานข้อมูลอัตโนมัติหากยังไม่มีข้อมูลใน Database
def init_db():
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        # ตารางสถานี
        cur.execute("""
        CREATE TABLE IF NOT EXISTS station_data (
            id SERIAL PRIMARY KEY,
            station TEXT UNIQUE NOT NULL,
            river TEXT, tambon TEXT, amphoe TEXT, province TEXT, location TEXT,
            lat DECIMAL(10, 7),   
            lon DECIMAL(10, 7) 
        )
        """)
        # ตารางข้อมูลน้ำ — ใช้ station TEXT (ไม่ใช่ station_id)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS water_data (
            id SERIAL PRIMARY KEY,
            station TEXT REFERENCES station_data(station) ON DELETE CASCADE,
            parameter TEXT, unit TEXT, location TEXT,
            check_number TEXT, value TEXT, numeric_value REAL
        )
        """)
        # ตารางข้อมูลดิน — ใช้ station TEXT เช่นกัน
        cur.execute("""
        CREATE TABLE IF NOT EXISTS soil_data (
            id SERIAL PRIMARY KEY,
            station TEXT REFERENCES station_data(station) ON DELETE CASCADE,
            parameter TEXT, location TEXT,
            check_number TEXT, value TEXT, numeric_value REAL
        )
        """)
        # ตาราง users
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
        """)
        # Indexes — ใช้ชื่อคอลัมน์ที่ถูกต้อง (station)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_water_station ON water_data(station)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_soil_station ON soil_data(station)")
        # สร้าง admin user
        cur.execute('SELECT COUNT(*) FROM users WHERE username = %s', ('admin',))
        if cur.fetchone()[0] == 0:
            cur.execute('INSERT INTO users (username, password) VALUES (%s, %s)', ('admin', 'admin123'))
            print("✅ สร้าง user admin: username='admin', password='admin123'")
        conn.commit()
        print("✅ ตารางฐานข้อมูลพร้อมใช้งาน")
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# === Debug Route ===
@app.route('/debug/db')
def debug_db():
    """แสดงข้อมูลฐานข้อมูลสำหรับ debug"""
    info = {
        'POSTGRES_HOST': os.environ.get('POSTGRES_HOST', 'Not set'),
        'POSTGRES_DATABASE': os.environ.get('POSTGRES_DATABASE', 'Not set'),
    }
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        info['Tables'] = [row['table_name'] for row in cur.fetchall()]
        conn.close()
    except Exception as e:
        info['Error'] = str(e)
    return info

# ฟังก์ชันที่ใช้เช็คก่อนเข้าถึงส่วนที่แอดมินมีสิทธิ์ ถ้ายังไม่ได้ Login จะถูกเด้งไปหน้า Login
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# === Login Route ===
@app.route('/login', methods=['GET', 'POST'])
def login(): # รับค่า username กับ password จาก form
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        print(f"🔍 DEBUG: login attempt - username='{username}'")
        # ตรวจสอบว่าเป็น AJAX request หรือไม่
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT password FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        conn.close()
        print(f"🔍 DEBUG: DB result - {row}")
        if row and row['password'] == password:
            # เข้าสู่ระบบสำเร็จ
            session['logged_in'] = True
            session['username'] = username
            if is_ajax:
                # คืนค่า JSON สำหรับ AJAX
                return jsonify({
                    'success': True,
                    'message': 'เข้าสู่ระบบสำเร็จ',
                    'redirect_url': url_for('index')
                })
            else:
                # Redirect สำหรับ form submit ปกติ (รองรับกรณีไม่มี JS)
                return redirect(url_for('index'))
        else:
            # กรณี เข้าสู่ระบบไม่สำเร็จ
            if is_ajax:
                return jsonify({
                    'success': False,
                    'message': 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'
                }), 401  # HTTP 401 Unauthorized
            else:
                flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง กรุณากรอกใหม่', 'error')
                return redirect(url_for('login'))
    # GET request: แสดงหน้า login
    return render_template('login.html')

# === Logout Route ===
@app.route('/logout')
def logout(): # ออกแล้วจะเด้งกลับไปหน้าหลัก
    session.clear()
    return redirect(url_for('index'))

# === CORS Headers ===
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# === Get All Stations ===
def get_stations():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT id, station, river, tambon, amphoe, province, location
    FROM station_data
    ORDER BY river, station
    """)
    stations = cur.fetchall()
    conn.close()
    return stations

# === Index Route ===
@app.route('/stations')
def stations_manage():
    try:
        stations = get_stations() # ดึงรายการสถานีทั้งหมด
        # แยกข้อมูล จังหวัด, อำเภอ, ตำบล เพื่อใช้ทำ Filter ในหน้าเว็บ
        unique_rivers = sorted(list(set([s['river'] for s in stations if s['river']])))
        unique_provinces = sorted(list(set([s['province'] for s in stations if s['province']])))
        unique_tambons = sorted(list(set([s['tambon'] for s in stations if s['tambon']])))
        unique_amphoes = sorted(list(set([s['amphoe'] for s in stations if s['amphoe']])))
        location_hierarchy = {}
        for station in stations:
            prov = station.get('province', '')
            amph = station.get('amphoe', '')
            tamb = station.get('tambon', '')
            if prov and amph and tamb:
                if prov not in location_hierarchy:
                    location_hierarchy[prov] = {}
                if amph not in location_hierarchy[prov]:
                    location_hierarchy[prov][amph] = set()
                location_hierarchy[prov][amph].add(tamb)
        for prov in location_hierarchy:
            for amph in location_hierarchy[prov]:
                location_hierarchy[prov][amph] = sorted(list(location_hierarchy[prov][amph]))
        return render_template('index.html',
            stations=stations,
            unique_rivers=unique_rivers,
            unique_provinces=unique_provinces,
            unique_tambons=unique_tambons,
            unique_amphoes=unique_amphoes,
            location_hierarchy=location_hierarchy)
    except Exception as e:
        return f"Error loading page: {str(e)}", 500

# === Test Route ===
@app.route('/test')
def test():
    return "Flask app is working with PostgreSQL!"

def get_station_by_code(station_code):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT id, station, river, tambon, amphoe, province, location, lat, lon
    FROM station_data
    WHERE TRIM(station) = %s
    """, (station_code.strip(),))
    row = cur.fetchone()
    conn.close()
    return row

# === Get Water Data ===
def get_water_data(station_code):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(r"""
    SELECT parameter, unit, location, check_number, value, numeric_value
    FROM water_data
    WHERE TRIM(station) = %s
    ORDER BY
        NULLIF(REGEXP_REPLACE(check_number, '\D', '', 'g'), '')::INTEGER NULLS LAST,
        check_number,
        parameter
    """, (station_code.strip(),))
    pivot_data = {}
    numeric_data = {}
    check_numbers = []
    unit_info = {}
    for row in cur.fetchall():
        param = row['parameter']
        check_num = row['check_number']
        value = row['value']
        numeric_value = row['numeric_value'] if row['numeric_value'] is not None else 0
        unit = row['unit']
        if param not in pivot_data:
            pivot_data[param] = {}
            numeric_data[param] = {}
            unit_info[param] = unit
        try:
            check_num_int = int(check_num.split('ครั้งที่')[-1].strip())
            if check_num_int not in check_numbers:
                check_numbers.append(check_num_int)
            pivot_data[param][check_num_int] = value
            numeric_data[param][check_num_int] = numeric_value
        except (ValueError, IndexError):
            if check_num not in check_numbers:
                check_numbers.append(check_num)
            pivot_data[param][check_num] = value
            numeric_data[param][check_num] = numeric_value
    conn.close()
    numeric_checks = sorted([c for c in check_numbers if isinstance(c, int)])
    text_checks = sorted([c for c in check_numbers if not isinstance(c, int)])
    sorted_checks = numeric_checks + text_checks
    parameters = sorted(pivot_data.keys())
    pivot_list = []
    for param in parameters:
        row_data = {'parameter': param, 'check_values': {}, 'unit': unit_info.get(param, '')}
        for check_num in sorted_checks:
            value = pivot_data[param].get(check_num, None)
            row_data['check_values'][str(check_num)] = value if value else None
        pivot_list.append(row_data)
    pivot_list_filtered = []
    for param in parameters:
        row_data_filtered = {'parameter': param, 'check_values': {}, 'numeric_values': {}, 'unit': unit_info.get(param, '')}
        for check_num in sorted_checks:
            value = pivot_data[param].get(check_num, None)
            numeric_value = numeric_data[param].get(check_num, 0)
            row_data_filtered['check_values'][str(check_num)] = value if value else None
            row_data_filtered['numeric_values'][str(check_num)] = numeric_value
        pivot_list_filtered.append(row_data_filtered)
    return {
        'pivot': pivot_data,
        'pivot_list': pivot_list,
        'pivot_list_filtered': pivot_list_filtered,
        'check_numbers': sorted_checks,
        'units': unit_info,
        'parameters': parameters
    }

# === Get Soil Data ===
def get_soil_data(station_code):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(r"""
    SELECT parameter, location, check_number, value, numeric_value
    FROM soil_data
    WHERE TRIM(station) = %s
    ORDER BY
        NULLIF(REGEXP_REPLACE(check_number, '\D', '', 'g'), '')::INTEGER NULLS LAST,
        check_number,
        parameter
    """, (station_code.strip(),))
    pivot_data = {}
    numeric_data = {}
    check_numbers = []
    for row in cur.fetchall():
        param = row['parameter']
        check_num = row['check_number']
        value = row['value']
        numeric_value = row['numeric_value'] if row['numeric_value'] is not None else 0
        if param not in pivot_data:
            pivot_data[param] = {}
            numeric_data[param] = {}
        try:
            check_num_int = int(check_num.split('ครั้งที่')[-1].strip())
            if check_num_int not in check_numbers:
                check_numbers.append(check_num_int)
            pivot_data[param][check_num_int] = value
            numeric_data[param][check_num_int] = numeric_value
        except (ValueError, IndexError):
            if check_num not in check_numbers:
                check_numbers.append(check_num)
            pivot_data[param][check_num] = value
            numeric_data[param][check_num] = numeric_value
    conn.close()
    numeric_checks = sorted([c for c in check_numbers if isinstance(c, int)])
    text_checks = sorted([c for c in check_numbers if not isinstance(c, int)])
    sorted_checks = numeric_checks + text_checks
    parameters = sorted(pivot_data.keys())
    pivot_list = []
    for param in parameters:
        row_data = {'parameter': param, 'check_values': {}}
        for check_num in sorted_checks:
            value = pivot_data[param].get(check_num, None)
            row_data['check_values'][str(check_num)] = value if value else None
        pivot_list.append(row_data)
    pivot_list_filtered = []
    for param in parameters:
        row_data_filtered = {'parameter': param, 'check_values': {}, 'numeric_values': {}}
        for check_num in sorted_checks:
            value = pivot_data[param].get(check_num, None)
            numeric_value = numeric_data[param].get(check_num, 0)
            row_data_filtered['check_values'][str(check_num)] = value if value else None
            row_data_filtered['numeric_values'][str(check_num)] = numeric_value
        pivot_list_filtered.append(row_data_filtered)
    return {
        'pivot': pivot_data,
        'pivot_list': pivot_list,
        'pivot_list_filtered': pivot_list_filtered,
        'check_numbers': sorted_checks,
        'parameters': parameters
    }

# === Add Station Route ===
@app.route('/add-station', methods=['GET', 'POST'])
@login_required
def add_station():
    if request.method == 'POST':
        try:
            # === ดึงข้อมูลพื้นฐาน ===
            station = request.form.get('station', '').strip()
            river = request.form.get('river', '').strip()
            tambon = request.form.get('tambon', '').strip()
            amphoe = request.form.get('amphoe', '').strip()
            province = request.form.get('province', '').strip()
            location = request.form.get('location', '').strip()
            lat = request.form.get('lat', '').strip()
            lon = request.form.get('lon', '').strip()

            lat_value = float(lat) if lat else None
            lon_value = float(lon) if lon else None

            # === Debug: พิมพ์ข้อมูลที่ได้รับ ===
            print(f"\n🔍 === DEBUG: Add Station ===")
            print(f"📍 station={station}")
            print(f"📍 location={location}")
            # ดึงพารามิเตอร์น้ำ
            parameters = request.form.getlist('parameter[]')
            units = request.form.getlist('unit[]')
            print(f"💧 parameters={parameters}")
            print(f"💧 units={units}")
            # ดึงพารามิเตอร์ดิน
            soil_params = request.form.getlist('soil_parameter[]')
            print(f"🌱 soil_params={soil_params}")
            conn = get_db()
            cur = conn.cursor()
            # === 1. บันทึกสถานี ===
            cur.execute("""
            INSERT INTO station_data (station, river, tambon, amphoe, province, location, lat, lon)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (station) DO UPDATE SET
                river = EXCLUDED.river,
                tambon = EXCLUDED.tambon,
                amphoe = EXCLUDED.amphoe,
                province = EXCLUDED.province,
                location = EXCLUDED.location,
                lat = EXCLUDED.lat,
                lon = EXCLUDED.lon
            """, (station, river, tambon, amphoe, province, location, lat_value, lon_value))
            print(f"✅ Saved station: {station}")
            # === 2. บันทึกข้อมูลน้ำ ===
            water_count = 0
            water_check_count = int(request.form.get('water_check_count', 14))
            for i in range(1, water_check_count + 1):
                check_values = request.form.getlist(f'check{i}[]')
                if not check_values or all(v == '' for v in check_values):
                    continue
                for idx, param in enumerate(parameters):
                    if idx >= len(check_values):
                        break
                    value = check_values[idx].strip() if check_values[idx] else ''
                    if not value:
                        continue
                    unit = units[idx].strip() if idx < len(units) else ''
                    numeric_value = None
                    if value and value not in ['-', 'ND', '']:
                        try:
                            numeric_value = 0.0 if value.startswith('<') else float(value)
                        except ValueError:
                            pass
                    cur.execute("""
                    INSERT INTO water_data (station, parameter, unit, location, check_number, value, numeric_value)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (station, param, unit, location, f'ครั้งที่ {i}', value, numeric_value))
                    water_count += 1
            print(f"✅ Saved {water_count} water data records")
            # === 3. บันทึกข้อมูลดิน ===
            soil_count = 0
            soil_check_count = int(request.form.get('soil_check_count', 8))
            for i in range(1, soil_check_count + 1):
                soil_check_values = request.form.getlist(f'soil_check{i}[]')
                if not soil_check_values or all(v == '' for v in soil_check_values):
                    continue
                for idx, param in enumerate(soil_params):
                    if idx >= len(soil_check_values):
                        break
                    value = soil_check_values[idx].strip() if soil_check_values[idx] else ''
                    if not value:
                        continue
                    numeric_value = None
                    if value and value not in ['-', 'ND', '']:
                        try:
                            numeric_value = 0.0 if value.startswith('<') else float(value)
                        except ValueError:
                            pass
                    cur.execute("""
                    INSERT INTO soil_data (station, parameter, location, check_number, value, numeric_value)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """, (station, param, location, f'ครั้งที่ {i}', value, numeric_value))
                    soil_count += 1
            print(f"✅ Saved {soil_count} soil data records")
            conn.commit()
            conn.close()
            return jsonify({
                'success': True,
                'message': 'Saved successfully',
                'water': water_count,
                'soil': soil_count
            })
        except Exception as e:
            print(f"❌ Error saving station: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'message': str(e)}), 500
    return render_template('add_station.html')

# === Delete Station Route ===
@app.route('/delete-station/<station_code>', methods=['DELETE'])
@login_required
def delete_station(station_code):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('DELETE FROM station_data WHERE station = %s', (station_code.strip(),))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        print("Error deleting station:", str(e))
        return jsonify({'success': False, 'message': str(e)}), 500

# === Station Detail Route ===
@app.route('/station/<station_code>')
def station_detail(station_code):
    try:
        station = get_station_by_code(station_code)  # ✅ มี lat/lon แล้ว
        if not station:
            return f"ไม่พบสถานี: {station_code}", 404
        water_data = get_water_data(station_code)
        soil_data = get_soil_data(station_code)
        return render_template('station_detail.html',
            station=station,          # ✅ station มี lat/lon
            water_data=water_data,
            soil_data=soil_data)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return f"Error loading station: {str(e)}", 500

# === Edit Station Route ===
@app.route('/edit-station/<station_code>', methods=['GET', 'POST'])
@login_required
def edit_station(station_code):
    if request.method == 'POST':
        try:
            station = request.form['station'].strip()
            river = request.form['river'].strip()
            tambon = request.form['tambon'].strip()
            amphoe = request.form['amphoe'].strip()
            province = request.form['province'].strip()
            location = request.form['location'].strip()
            lat_str = request.form.get('lat', '').strip()
            lon_str = request.form.get('lon', '').strip()

            try:
                lat = float(lat_str) if lat_str else None
            except ValueError:
                lat = None
            try:
                lon = float(lon_str) if lon_str else None
            except ValueError:
                lon = None
            
            conn = get_db()
            cur = conn.cursor()
            # อัปเดตข้อมูลสถานี
            cur.execute("""
            UPDATE station_data
            SET station = %s, river = %s, tambon = %s, amphoe = %s, province = %s, location = %s,  lat = %s, lon = %s
            WHERE station = %s
            """, (station, river, tambon, amphoe, province, location, lat, lon, station_code))
            # ลบเฉพาะข้อมูลน้ำและดินเดิม
            cur.execute('DELETE FROM water_data WHERE station = %s', (station_code.strip(),))
            cur.execute('DELETE FROM soil_data WHERE station = %s', (station_code.strip(),))
            parameters = request.form.getlist('parameter[]')
            units = request.form.getlist('unit[]')
            soil_params = request.form.getlist('soil_parameter[]')
            # บันทึกข้อมูลน้ำใหม่
            water_check_count = int(request.form.get('water_check_count', 14))
            for i in range(1, water_check_count + 1):
                check_values = request.form.getlist(f'check{i}[]')
                for idx, param in enumerate(parameters):
                    if idx < len(check_values):
                        value = check_values[idx].strip()
                        unit = units[idx].strip() if idx < len(units) else ''
                        numeric_value = None
                        if value and value not in ['-', 'ND']:
                            try:
                                numeric_value = 0.0 if value.startswith('<') else float(value)
                            except ValueError:
                                pass
                        cur.execute("""
                        INSERT INTO water_data (station, parameter, unit, location, check_number, value, numeric_value)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (station, param, unit, location, f'ครั้งที่ {i}', value, numeric_value))
            # บันทึกข้อมูลดินใหม่
            soil_check_count = int(request.form.get('soil_check_count', 8))
            for i in range(1, soil_check_count + 1):
                soil_check_values = request.form.getlist(f'soil_check{i}[]')
                for idx, param in enumerate(soil_params):
                    if idx < len(soil_check_values):
                        value = soil_check_values[idx].strip()
                        numeric_value = None
                        if value and value not in ['-', 'ND']:
                            try:
                                numeric_value = 0.0 if value.startswith('<') else float(value)
                            except ValueError:
                                pass
                        cur.execute("""
                        INSERT INTO soil_data (station, parameter, location, check_number, value, numeric_value)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """, (station, param, location, f'ครั้งที่ {i}', value, numeric_value))
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        except Exception as e:
            print(f"ERROR in edit_station POST: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 500
    # === GET: ดึงข้อมูลเดิมมา pre-fill ===
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
        SELECT river, station, location, tambon, amphoe, province, lat, lon
        FROM station_data WHERE station = %s
        """, (station_code.strip(),))
        station_row = cur.fetchone()
        if not station_row:
            conn.close()
            return "ไม่พบสถานี", 404
        cur.execute(r"""
        SELECT parameter, unit, check_number, value
        FROM water_data WHERE station = %s
        ORDER BY
            NULLIF(REGEXP_REPLACE(check_number, '\D', '', 'g'), '')::INTEGER NULLS LAST,
            check_number
        """, (station_code.strip(),))
        water_rows = cur.fetchall()
        cur.execute(r"""
        SELECT parameter, check_number, value
        FROM soil_data WHERE station = %s
        ORDER BY
            NULLIF(REGEXP_REPLACE(check_number, '\D', '', 'g'), '')::INTEGER NULLS LAST,
            check_number
        """, (station_code.strip(),))
        soil_rows = cur.fetchall()
        conn.close()
        water_data = {}
        for row in water_rows:
            param = row['parameter']
            if param not in water_data:
                water_data[param] = {'unit': row['unit'], 'checks': {}}
            check_num = row['check_number']
            water_data[param]['checks'][check_num] = row['value']
        soil_data = {}
        for row in soil_rows:
            param = row['parameter']
            if param not in soil_data:
                soil_data[param] = {'checks': {}}
            check_num = row['check_number']
            soil_data[param]['checks'][check_num] = row['value']
        water_check_count = len(next(iter(water_data.values()))['checks']) if water_data else 14
        soil_check_count = len(next(iter(soil_data.values()))['checks']) if soil_data else 8
        return render_template('edit_station.html',
            station=station_row,
            station_lat = station_row.get('lat'),
            station_lon = station_row.get('lon'),
            water_data=water_data,
            soil_data=soil_data,
            water_check_count=water_check_count,
            soil_check_count=soil_check_count)
    except Exception as e:
        print(f"ERROR in edit_station GET: {e}")
        import traceback
        traceback.print_exc()
        return f"Error loading edit form: {str(e)}", 500

# ค่าคงที่ — เพิ่มบนสุดของไฟล์ถัดจาก import
WATER_CHECK_COUNT = 15
SOIL_CHECK_COUNT  = 9

@app.route('/api/stations', methods=['POST'])
def api_add_station():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'ไม่พบข้อมูล JSON'}), 400

        station  = str(data.get('station',  '') or '').strip()
        river    = str(data.get('river',    '') or '').strip()
        tambon   = str(data.get('tambon',   '') or '').strip()
        amphoe   = str(data.get('amphoe',   '') or '').strip()
        province = str(data.get('province', '') or '').strip()
        location = str(data.get('location', '') or '').strip()

        lat_raw = data.get('lat')
        lon_raw = data.get('lon')
        try:
            lat = float(str(lat_raw).strip()) if lat_raw not in [None, '', 'null'] else None
        except (TypeError, ValueError):
            lat = None

        try:
            lon = float(str(lon_raw).strip()) if lon_raw not in [None, '', 'null'] else None
        except (TypeError, ValueError):
            lon = None

        print(f"📥 lat_raw={repr(lat_raw)} → lat={lat}")
        print(f"📥 lon_raw={repr(lon_raw)} → lon={lon}")

        if not station:
            return jsonify({'success': False, 'message': 'กรุณาระบุรหัสสถานี'}), 400

        conn = get_db()
        cur  = conn.cursor()

        # ✅ INSERT พร้อม lat, lon
        cur.execute("""
            INSERT INTO station_data
                (station, river, tambon, amphoe, province, location, lat, lon)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (station) DO UPDATE SET
                river    = EXCLUDED.river,
                tambon   = EXCLUDED.tambon,
                amphoe   = EXCLUDED.amphoe,
                province = EXCLUDED.province,
                location = EXCLUDED.location,
                lat      = EXCLUDED.lat,
                lon      = EXCLUDED.lon
        """, (station, river, tambon, amphoe, province, location, lat, lon))

        # บันทึกข้อมูลน้ำ
        water_count = 0
        for row in data.get('waterData', []):
            param = str(row.get('parameter', '') or '').strip()
            unit  = str(row.get('unit', '')      or '').strip()
            if not param:
                continue
            for i in range(1, WATER_CHECK_COUNT + 1):
                value = str(row.get(f'check{i}', '') or '').strip()
                if not value:
                    continue
                numeric_value = None
                if value not in ['-', 'ND']:
                    try:
                        numeric_value = 0.0 if value.startswith('<') else float(value)
                    except ValueError:
                        pass
                cur.execute("""
                    INSERT INTO water_data
                        (station, parameter, unit, location, check_number, value, numeric_value)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (station, param, unit, location, f'ครั้งที่ {i}', value, numeric_value))
                water_count += 1

        # บันทึกข้อมูลดิน
        soil_count = 0
        for row in data.get('soilData', []):
            param = str(row.get('parameter', '') or '').strip()
            if not param:
                continue
            for i in range(1, SOIL_CHECK_COUNT + 1):
                value = str(row.get(f'check{i}', '') or '').strip()
                if not value:
                    continue
                numeric_value = None
                if value not in ['-', 'ND']:
                    try:
                        numeric_value = 0.0 if value.startswith('<') else float(value)
                    except ValueError:
                        pass
                cur.execute("""
                    INSERT INTO soil_data
                        (station, parameter, location, check_number, value, numeric_value)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (station, param, location, f'ครั้งที่ {i}', value, numeric_value))
                soil_count += 1

        conn.commit()
        conn.close()

        print(f"✅ บันทึกสำเร็จ: {station} lat={lat} lon={lon} น้ำ={water_count} ดิน={soil_count}")
        return jsonify({'success': True, 'message': 'บันทึกสำเร็จ',
                        'station': station, 'lat': lat, 'lon': lon,
                        'water': water_count, 'soil': soil_count})

    except Exception as e:
        print(f"❌ api_add_station error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/env-test')
def env_test():
    return {
        'POSTGRES_HOST': os.environ.get('POSTGRES_HOST'),
        'DATABASE_URL': os.environ.get('DATABASE_URL')[:50] + '...' if os.environ.get('DATABASE_URL') else None
    }

@app.route('/check-env')
def check_env():
    return {
        "SUPABASE_DATABASE_URL": "SET" if os.environ.get('SUPABASE_DATABASE_URL') else "NOT SET",
        "SECRET_KEY": "SET" if os.environ.get('SECRET_KEY') else "NOT SET"
    }

# ===== ROUTE หน้าหลัก =====
@app.route('/')
def index():
    """หน้าหลัก: แสดงแผนที่และรายงานสถานีตรวจสอบ"""
    try:
        stations = get_stations()
        unique_rivers = sorted(list(set([s['river'] for s in stations if s['river']])))
        unique_provinces = sorted(list(set([s['province'] for s in stations if s['province']])))
        unique_tambons = sorted(list(set([s['tambon'] for s in stations if s['tambon']])))
        unique_amphoes = sorted(list(set([s['amphoe'] for s in stations if s['amphoe']])))
        location_hierarchy = {}
        for station in stations:
            prov = station.get('province', '')
            amph = station.get('amphoe', '')
            tamb = station.get('tambon', '')
            if prov and amph and tamb:
                if prov not in location_hierarchy:
                    location_hierarchy[prov] = {}
                if amph not in location_hierarchy[prov]:
                    location_hierarchy[prov][amph] = set()
                location_hierarchy[prov][amph].add(tamb)
        for prov in location_hierarchy:
            for amph in location_hierarchy[prov]:
                location_hierarchy[prov][amph] = sorted(list(location_hierarchy[prov][amph]))
        return render_template('mapandnews.html',
            stations=stations,
            unique_rivers=unique_rivers,
            unique_provinces=unique_provinces,
            unique_tambons=unique_tambons,
            unique_amphoes=unique_amphoes,
            location_hierarchy=location_hierarchy)
    except Exception as e:
        return f"Error loading page: {str(e)}", 500

# หน้าแสดงแผนที่และข่าว
@app.route('/map/<station_code>')
def map_page(station_code):
    station = get_station_by_code(station_code)
    if not station:
        return "ไม่พบสถานี", 404
    water_data = get_water_data(station_code)
    soil_data = get_soil_data(station_code)
    return render_template(
        'mapandnews.html',
        station=station,
        water_data=water_data,
        soil_data=soil_data
    )

# === API: Get All Monitoring Data for Map ===
@app.route('/api/map-data')
def api_map_data():
    """ส่งข้อมูลน้ำและดินทั้งหมดในรูปแบบ JSON สำหรับแผนที่"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
        SELECT DISTINCT check_number
        FROM water_data
        ORDER BY NULLIF(REGEXP_REPLACE(check_number, '\D', '', 'g'), '')::INTEGER NULLS LAST, check_number
        """)
        water_checks = [row['check_number'] for row in cur.fetchall()]
        cur.execute("""
        SELECT DISTINCT check_number
        FROM soil_data
        ORDER BY NULLIF(REGEXP_REPLACE(check_number, '\D', '', 'g'), '')::INTEGER NULLS LAST, check_number
        """)
        soil_checks = [row['check_number'] for row in cur.fetchall()]
        cur.execute("SELECT DISTINCT parameter, unit FROM water_data ORDER BY parameter")
        water_params = {row['parameter']: row['unit'] for row in cur.fetchall()}
        cur.execute("SELECT DISTINCT parameter FROM soil_data ORDER BY parameter")
        soil_params = [row['parameter'] for row in cur.fetchall()]
        water_data = {}
        for param in water_params:
            water_data[param] = {}
            cur.execute("""
            SELECT station, check_number, numeric_value
            FROM water_data
            WHERE parameter = %s AND numeric_value IS NOT NULL
            ORDER BY station, NULLIF(REGEXP_REPLACE(check_number, '\D', '', 'g'), '')::INTEGER NULLS LAST, check_number
            """, (param,))
            rows = cur.fetchall()
            for row in rows:
                st = row['station']
                val = row['numeric_value']
                if st not in water_data[param]:
                    water_data[param][st] = [None] * len(water_checks)
                try:
                    idx = water_checks.index(row['check_number'])
                    water_data[param][st][idx] = val
                except ValueError:
                    pass
        soil_data = {}
        for param in soil_params:
            soil_data[param] = {}
            cur.execute("""
            SELECT station, check_number, numeric_value
            FROM soil_data
            WHERE parameter = %s AND numeric_value IS NOT NULL
            ORDER BY station, NULLIF(REGEXP_REPLACE(check_number, '\D', '', 'g'), '')::INTEGER NULLS LAST, check_number
            """, (param,))
            rows = cur.fetchall()
            for row in rows:
                st = row['station']
                val = row['numeric_value']
                if st not in soil_data[param]:
                    soil_data[param][st] = [None] * len(soil_checks)
                try:
                    idx = soil_checks.index(row['check_number'])
                    soil_data[param][st][idx] = val
                except ValueError:
                    pass
        conn.close()
        return jsonify({
            'success': True,
            'water': {
                'check_numbers': water_checks,
                'parameters': water_params,
                'data': water_data
            },
            'soil': {
                'check_numbers': soil_checks,
                'parameters': soil_params,
                'data': soil_data
            }
        })
    except Exception as e:
        print(f"❌ API Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# === API: Get Latest Data for Map Chart ===
@app.route('/api/map-latest-data')
def api_map_latest_data():
    """ส่งข้อมูลค่าล่าสุดของแต่ละสถานี สำหรับแสดงกราฟ"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT parameter, unit FROM water_data ORDER BY parameter")
        water_params = {row['parameter']: row['unit'] for row in cur.fetchall()}
        cur.execute("SELECT DISTINCT parameter FROM soil_data ORDER BY parameter")
        soil_params = [row['parameter'] for row in cur.fetchall()]
        water_latest = {}
        for param in water_params:
            cur.execute("""
            SELECT DISTINCT ON (station)
                station, check_number, numeric_value, value
            FROM water_data
            WHERE parameter = %s AND numeric_value IS NOT NULL
            ORDER BY station,
                NULLIF(REGEXP_REPLACE(check_number, '[^0-9]', '', 'g'), '')::INTEGER DESC NULLS LAST,
                check_number DESC
            """, (param,))
            rows = cur.fetchall()
            water_latest[param] = {}
            for row in rows:
                if row['numeric_value'] is not None:
                    water_latest[param][row['station']] = {
                        'value': row['numeric_value'],
                        'raw_value': row['value'],
                        'check_number': row['check_number']
                    }
        soil_latest = {}
        for param in soil_params:
            cur.execute("""
            SELECT DISTINCT ON (station)
                station, check_number, numeric_value, value
            FROM soil_data
            WHERE parameter = %s AND numeric_value IS NOT NULL
            ORDER BY station,
                NULLIF(REGEXP_REPLACE(check_number, '[^0-9]', '', 'g'), '')::INTEGER DESC NULLS LAST,
                check_number DESC
            """, (param,))
            rows = cur.fetchall()
            soil_latest[param] = {}
            for row in rows:
                if row['numeric_value'] is not None:
                    soil_latest[param][row['station']] = {
                        'value': row['numeric_value'],
                        'raw_value': row['value'],
                        'check_number': row['check_number']
                    }
        conn.close()
        response = {
            'success': True,
            'water': {
                'parameters': water_params,
                'latest': water_latest
            },
            'soil': {
                'parameters': soil_params,
                'latest': soil_latest
            },
            'timestamp': datetime.now().isoformat()
        }
        return jsonify(response)
    except Exception as e:
        print(f"❌ API Latest Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/station-history')
def api_station_history():
    """ดึงข้อมูลย้อนหลังของแต่ละสถานี"""
    try:
        station_id = request.args.get('station')
        param_key = request.args.get('param')
        data_type = request.args.get('type', 'water')
        
        print(f"🔍 API Request: station={station_id}, param={param_key}, type={data_type}")
        
        if not station_id or not param_key:
            return jsonify({'success': False, 'error': 'กรุณาระบุสถานีและพารามิเตอร์'}), 400
        
        conn = get_db()
        cur = conn.cursor()
        
        # ✅ ใช้ตารางที่ถูกต้องตาม type
        if data_type == 'water':
            cur.execute("""
                SELECT check_number, numeric_value
                FROM water_data
                WHERE station = %s AND parameter = %s AND numeric_value IS NOT NULL
                ORDER BY NULLIF(REGEXP_REPLACE(check_number, '[^0-9]', '', 'g'), '')::INTEGER ASC
            """, (station_id, param_key))
        else:  # soil
            cur.execute("""
                SELECT check_number, numeric_value
                FROM soil_data
                WHERE station = %s AND parameter = %s AND numeric_value IS NOT NULL
                ORDER BY NULLIF(REGEXP_REPLACE(check_number, '[^0-9]', '', 'g'), '')::INTEGER ASC
            """, (station_id, param_key))
        
        rows = cur.fetchall()
        conn.close()
        
        # ✅ แปลงข้อมูลให้เป็นรูปแบบเดียวกัน (ทั้งน้ำและดิน)
        check_numbers = [row['check_number'] for row in rows]
        values = [float(row['numeric_value']) if row['numeric_value'] is not None else None for row in rows]
        
        print(f"📊 Found {len(rows)} records")
        print(f"📊 Check numbers: {check_numbers}")
        print(f"📊 Values: {values}")
        
        return jsonify({
            'success': True,
            'station': station_id,
            'parameter': param_key,
            'type': data_type,  # ✅ เพิ่ม type เพื่อ frontend รู้ว่าเป็นน้ำหรือดิน
            'check_numbers': check_numbers,
            'values': values
        })
        
    except Exception as e:
        print(f"❌ API Station History Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# === API: Get Latest Data by Tambon ===
@app.route('/api/latest-by-tambon')
def api_latest_by_tambon():
    """ดึงข้อมูลล่าสุดจัดกลุ่มตามตำบล + รายการรอบตรวจวัดทั้งหมด"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
        SELECT station, tambon, amphoe, province, river, location
        FROM station_data
        ORDER BY tambon, station
        """)
        stations = cur.fetchall()
        cur.execute("SELECT DISTINCT parameter, unit FROM water_data ORDER BY parameter")
        water_params = {row['parameter']: row['unit'] for row in cur.fetchall()}
        cur.execute("SELECT DISTINCT parameter FROM soil_data ORDER BY parameter")
        soil_params = [row['parameter'] for row in cur.fetchall()]
        cur.execute("""
        SELECT check_number
        FROM (
            SELECT DISTINCT check_number,
                NULLIF(REGEXP_REPLACE(check_number, '[^0-9]', '', 'g'), '')::INTEGER as sort_key
            FROM water_data
        ) AS temp
        ORDER BY sort_key DESC NULLS LAST, check_number DESC
        """)
        water_checks = [row['check_number'] for row in cur.fetchall()]
        cur.execute("""
        SELECT check_number
        FROM (
            SELECT DISTINCT check_number,
                NULLIF(REGEXP_REPLACE(check_number, '[^0-9]', '', 'g'), '')::INTEGER as sort_key
            FROM soil_data
        ) AS temp
        ORDER BY sort_key DESC NULLS LAST, check_number DESC
        """)
        soil_checks = [row['check_number'] for row in cur.fetchall()]
        water_latest_check = water_checks[0] if water_checks else None
        soil_latest_check = soil_checks[0] if soil_checks else None
        if not water_latest_check and not soil_latest_check:
            tambons = sorted(list(set(s['tambon'] for s in stations if s['tambon'])))
            conn.close()
            return jsonify({
                'success': True,
                'water_latest_check': None,
                'soil_latest_check': None,
                'tambons': tambons,
                'stations': stations,
                'water': {
                    'parameters': water_params,
                    'latest': {},
                    'check_numbers': []
                },
                'soil': {
                    'parameters': soil_params,
                    'latest': {},
                    'check_numbers': []
                }
            })
        water_latest = {}
        if water_latest_check:
            for param in water_params:
                water_latest[param] = {}
                cur.execute("""
                SELECT wd.station, sd.tambon, wd.numeric_value, wd.value, wd.check_number
                FROM water_data wd
                JOIN station_data sd ON wd.station = sd.station
                WHERE wd.parameter = %s AND wd.check_number = %s AND wd.numeric_value IS NOT NULL
                """, (param, water_latest_check))
                for row in cur.fetchall():
                    tambon = row['tambon'] or 'ไม่ระบุ'
                    if tambon not in water_latest[param]:
                        water_latest[param][tambon] = []
                    raw_val = row['value'] or ''
                    numeric_val = row['numeric_value']
                    prefix = ''
                    if raw_val.startswith('<'):
                        prefix = '<'
                        if numeric_val is None:
                            try: numeric_val = float(raw_val.replace('<', '').strip())
                            except: numeric_val = 0.0
                    elif raw_val.startswith('>'):
                        prefix = '>'
                        if numeric_val is None:
                            try: numeric_val = float(raw_val.replace('>', '').strip())
                            except: numeric_val = 0.0
                    water_latest[param][tambon].append({
                        'station': row['station'],
                        'value': float(numeric_val) if numeric_val is not None else None,
                        'raw_value': raw_val,
                        'prefix': prefix,
                        'check_number': row['check_number']
                    })
        soil_latest = {}
        if soil_latest_check:
            for param in soil_params:
                soil_latest[param] = {}
                cur.execute("""
                SELECT sd.station, st.tambon, sd.numeric_value, sd.value, sd.check_number
                FROM soil_data sd
                JOIN station_data st ON sd.station = st.station
                WHERE sd.parameter = %s AND sd.check_number = %s AND sd.numeric_value IS NOT NULL
                """, (param, soil_latest_check))
                for row in cur.fetchall():
                    tambon = row['tambon'] or 'ไม่ระบุ'
                    if tambon not in soil_latest[param]:
                        soil_latest[param][tambon] = []
                    raw_val = row['value'] or ''
                    numeric_val = row['numeric_value']
                    prefix = ''
                    if raw_val.startswith('<'):
                        prefix = '<'
                        if numeric_val is None:
                            try: numeric_val = float(raw_val.replace('<', '').strip())
                            except: numeric_val = 0.0
                    elif raw_val.startswith('>'):
                        prefix = '>'
                        if numeric_val is None:
                            try: numeric_val = float(raw_val.replace('>', '').strip())
                            except: numeric_val = 0.0
                    soil_latest[param][tambon].append({
                        'station': row['station'],
                        'value': float(numeric_val) if numeric_val is not None else None,
                        'raw_value': raw_val,
                        'prefix': prefix,
                        'check_number': row['check_number']
                    })
        tambons = sorted(list(set(s['tambon'] for s in stations if s['tambon'])))
        conn.close()
        return jsonify({
            'success': True,
            'water_latest_check': water_latest_check,
            'soil_latest_check': soil_latest_check,
            'tambons': tambons,
            'stations': stations,
            'water': {
                'parameters': water_params,
                'latest': water_latest,
                'check_numbers': water_checks
            },
            'soil': {
                'parameters': soil_params,
                'latest': soil_latest,
                'check_numbers': soil_checks
            }
        })
    except Exception as e:
        print(f"❌ API Tambon Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# === API: Get Data by Check Number ===
@app.route('/api/data-by-check')
def api_data_by_check():
    """ดึงข้อมูลตามรอบตรวจวัดที่ระบุ"""
    try:
        check_number = request.args.get('check_number')
        data_type = request.args.get('type', 'water')
        if not check_number:
            return jsonify({'success': False, 'error': 'กรุณาระบุรอบตรวจวัด'}), 400
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
        SELECT station, tambon, amphoe, province, river, location
        FROM station_data
        ORDER BY tambon, station
        """)
        stations = cur.fetchall()
        if data_type == 'water':
            cur.execute("SELECT DISTINCT parameter, unit FROM water_data ORDER BY parameter")
            params = {row['parameter']: row['unit'] for row in cur.fetchall()}
            data_by_param = {}
            for param in params:
                data_by_param[param] = {}
                cur.execute("""
                SELECT wd.station, sd.tambon, wd.numeric_value, wd.value, wd.check_number
                FROM water_data wd
                JOIN station_data sd ON wd.station = sd.station
                WHERE wd.parameter = %s
                AND wd.check_number = %s
                AND wd.numeric_value IS NOT NULL
                """, (param, check_number))
                for row in cur.fetchall():
                    tambon = row['tambon'] or 'ไม่ระบุ'
                    if tambon not in data_by_param[param]:
                        data_by_param[param][tambon] = []
                    raw_val = row['value'] or ''
                    numeric_val = row['numeric_value']
                    prefix = ''
                    if raw_val.startswith('<'):
                        prefix = '<'
                        if numeric_val is None:
                            try: numeric_val = float(raw_val.replace('<', '').strip())
                            except: numeric_val = 0.0
                    elif raw_val.startswith('>'):
                        prefix = '>'
                        if numeric_val is None:
                            try: numeric_val = float(raw_val.replace('>', '').strip())
                            except: numeric_val = 0.0
                    data_by_param[param][tambon].append({
                        'station': row['station'],
                        'value': float(numeric_val) if numeric_val is not None else None,
                        'raw_value': raw_val,
                        'prefix': prefix,
                        'check_number': row['check_number']
                    })
        else:
            cur.execute("SELECT DISTINCT parameter FROM soil_data ORDER BY parameter")
            params = [row['parameter'] for row in cur.fetchall()]
            data_by_param = {}
            for param in params:
                data_by_param[param] = {}
                cur.execute("""
                SELECT sd.station, st.tambon, sd.numeric_value, sd.value, sd.check_number
                FROM soil_data sd
                JOIN station_data st ON sd.station = st.station
                WHERE sd.parameter = %s
                AND sd.check_number = %s
                AND sd.numeric_value IS NOT NULL
                """, (param, check_number))
                for row in cur.fetchall():
                    tambon = row['tambon'] or 'ไม่ระบุ'
                    if tambon not in data_by_param[param]:
                        data_by_param[param][tambon] = []
                    raw_val = row['value'] or ''
                    numeric_val = row['numeric_value']
                    prefix = ''
                    if raw_val.startswith('<'):
                        prefix = '<'
                        if numeric_val is None:
                            try: numeric_val = float(raw_val.replace('<', '').strip())
                            except: numeric_val = 0.0
                    elif raw_val.startswith('>'):
                        prefix = '>'
                        if numeric_val is None:
                            try: numeric_val = float(raw_val.replace('>', '').strip())
                            except: numeric_val = 0.0
                    data_by_param[param][tambon].append({
                        'station': row['station'],
                        'value': float(numeric_val) if numeric_val is not None else None,
                        'raw_value': raw_val,
                        'prefix': prefix,
                        'check_number': row['check_number']
                    })
        tambons = sorted(list(set(s['tambon'] for s in stations if s['tambon'])))
        conn.close()
        return jsonify({
            'success': True,
            'check_number': check_number,
            'type': data_type,
            'tambons': tambons,
            'stations': stations,
            'data': data_by_param,
            'parameters': params
        })
    except Exception as e:
        print(f"❌ API Data By Check Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stations-list')
def get_stations_list():
    try:
        conn = get_db()
        cur  = conn.cursor()
        # ✅ เพิ่ม lat, lon ใน SELECT
        cur.execute("""
            SELECT station, river, tambon, amphoe, province, location, lat, lon
            FROM station_data
            ORDER BY river, station
        """)
        rows = cur.fetchall()
        conn.close()

        stations = []
        for row in rows:
            river  = row['river']  or ''
            tambon = row['tambon'] or ''
            stations.append({
                'id':       row['station'],
                'name':     f"แม่น้ำ{river} ({tambon})" if river else row['station'],
                'river':    river,
                'tambon':   tambon,
                'amphoe':   row['amphoe']   or '',
                'province': row['province'] or '',
                'lat': float(row['lat']) if row['lat'] is not None else None,  # ✅
                'lon': float(row['lon']) if row['lon'] is not None else None,  # ✅
            })

        return jsonify({'success': True, 'stations': stations, 'count': len(stations)})

    except Exception as e:
        print(f"❌ stations-list error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    
# ✅ เพิ่มตัวแปร Hardcode ข่าว (แทน Database)
HARDCODED_NEWS = [
    {
        'id': 1,
        'type': 'normal',
        'badge': '🔵 ทั่วไป',
        'badgeClass': 'badge-normal',
        'title': 'กรมอนามัยเผยคุณภาพน้ำแม่น้ำกกอยู่ในเกณฑ์มาตรฐาน',
        'excerpt': 'สำนักงานสิ่งแวดล้อมภาคที่ 1 เชียงใหม่ รายงานผลการตรวจวัดคุณภาพน้ำในแม่น้ำกกและลำน้ำสาขา...',
        'content': '<p>สำนักงานสิ่งแวดล้อมและควบคุมมลพิษที่ 1 (เชียงใหม่) รายงานผลการตรวจวัดคุณภาพน้ำในแม่น้ำกกและลำน้ำสาขา พบว่าค่าสารปนเปื้อนต่างๆ อยู่ในเกณฑ์มาตรฐานที่กำหนด...</p>',
        'date': '15 มี.ค. 68',
        'source': 'RYT9',
        'externalLink': 'https://www.ryt9.com/s/prg/3596933',
        'image': 'https://www.ryt9.com/img/files/20250416/00c1d856-0.jpg.webp',
        'sourceKey': 'ryt9_1'
    },
    {
        'id': 2,
        'type': 'normal',
        'badge': '⚠️ สิ่งแวดล้อม',
        'badgeClass': 'badge-warning',
        'title': 'ชาวบ้านเชียงรายร่วมเฝ้าระวังคุณภาพน้ำแม่น้ำโขง',
        'excerpt': 'ชุมชนริมแม่น้ำโขงจังหวัดเชียงราย จัดกิจกรรมติดตามตรวจสอบคุณภาพน้ำร่วมกับหน่วยงานภาครัฐ...',
        'content': '<p>ชาวบ้านในจังหวัดเชียงรายร่วมกับสำนักงานสิ่งแวดล้อม จัดกิจกรรมติดตามตรวจสอบคุณภาพน้ำแม่น้ำโขง เพื่อสร้างความมั่นใจในการใช้น้ำอุปโภคบริโภค...</p>',
        'date': '12 มี.ค. 68',
        'source': 'RYT9',
        'externalLink': 'https://www.ryt9.com/s/iq01/12768056',
        'image': 'https://www.ryt9.com/img/files/20251122/00c2d338-0.jpg.webp',
        'sourceKey': 'ryt9_2'
    },
    {
        'id': 3,
        'type': 'normal',
        'badge': '🏛️ รัฐบาล',
        'badgeClass': 'badge-info',
        'title': 'เตือนภัย! ตรวจสอบสารปนเปื้อนในแหล่งน้ำภาคเหนือ',
        'excerpt': 'กรมทรัพยากรน้ำแจ้งเตือนประชาชนในพื้นที่ภาคเหนือเฝ้าระวังคุณภาพน้ำช่วงฤดูร้อน...',
        'content': '<p>กรมทรัพยากรน้ำ กระทรวงทรัพยากรธรรมชาติและสิ่งแวดล้อม ออกประกาศเตือนประชาชนในพื้นที่ภาคเหนือให้เฝ้าระวังคุณภาพน้ำในช่วงฤดูร้อน...</p>',
        'date': '10 มี.ค. 68',
        'source': 'RYT9',
        'externalLink': 'https://www.ryt9.com/s/prg/12721189',
        'image': 'https://www.ryt9.com/img/files/20250617/00c21c25-0.jpg.webp',
        'sourceKey': 'ryt9_3'
    },
    {
        'id': 4,
        'type': 'normal',
        'badge': '💰 งบประมาณ',
        'badgeClass': 'badge-primary',
        'title': 'ผลตรวจตะกอนดินแม่น้ำสายพบค่าปกติ',
        'excerpt': 'ผลการตรวจวัดตะกอนดินในแม่น้ำสายจังหวัดเชียงราย พบว่าค่าสารโลหะหนักอยู่ในเกณฑ์ปลอดภัย...',
        'content': '<p>สำนักงานสิ่งแวดล้อมภาคที่ 1 เชียงใหม่ เผยผลการตรวจวัดตะกอนดินในแม่น้ำสาย พบว่าค่าสารโลหะหนักต่างๆ อยู่ในเกณฑ์มาตรฐาน...</p>',
        'date': '08 มี.ค. 68',
        'source': 'RYT9',
        'externalLink': 'https://www.ryt9.com/s/prg/12731088',
        'image': 'https://www.ryt9.com/img/files/20250722/00c242d0-0.jpg.webp',
        'sourceKey': 'ryt9_4'
    },
    {
        'id': 5,
        'type': 'normal',
        'badge': '🔵 ทั่วไป',
        'badgeClass': 'badge-normal',
        'title': 'เปิดศูนย์เฝ้าระวังคุณภาพน้ำจังหวัดเชียงใหม่',
        'excerpt': 'จังหวัดเชียงใหม่เปิดศูนย์ติดตามตรวจสอบคุณภาพน้ำแบบเรียลไทม์ เพื่อแจ้งเตือนประชาชน...',
        'content': '<p>จังหวัดเชียงใหม่ร่วมกับหน่วยงานที่เกี่ยวข้อง เปิดศูนย์ติดตามตรวจสอบคุณภาพน้ำแบบเรียลไทม์ เพื่อแจ้งเตือนประชาชนกรณีพบค่าผิดปกติ...</p>',
        'date': '05 มี.ค. 68',
        'source': 'RYT9',
        'externalLink': 'https://www.ryt9.com/s/iq01/12729203',
        'image': 'https://www.ryt9.com/img/files/20250715/00c23b73-0.jpg.webp',
        'sourceKey': 'ryt9_5'
    },
    {
        'id': 6,
        'type': 'normal',
        'badge': '🔵 ทั่วไป',
        'badgeClass': 'badge-normal',
        'title': 'แนะนำวิธีตรวจสอบคุณภาพน้ำเบื้องต้นสำหรับประชาชน',
        'excerpt': 'กรมอนามัยเผยวิธีสังเกตคุณภาพน้ำด้วยตนเองเบื้องต้น เพื่อความปลอดภัยในการอุปโภคบริโภค...',
        'content': '<p>กรมอนามัย กระทรวงสาธารณสุข แนะนำวิธีสังเกตคุณภาพน้ำด้วยตนเองเบื้องต้น เช่น การดูสี กลิ่น รสชาติ...</p>',
        'date': '01 มี.ค. 68',
        'source': 'RYT9',
        'externalLink': 'https://www.ryt9.com/s/prg/12748477',
        'image': 'https://www.ryt9.com/img/files/20250917/00c286bd-0.jpg.webp',
        'sourceKey': 'ryt9_6'
    },
    {
        'id': 7,
        'type': 'normal',
        'badge': '🔵 ทั่วไป',
        'badgeClass': 'badge-normal',
        'title': 'สวทช. พัฒนาเทคโนโลยีตรวจสอบคุณภาพน้ำ',
        'excerpt': 'สวทช. เผยพัฒนาเทคโนโลยีใหม่สำหรับตรวจสอบคุณภาพน้ำแบบเรียลไทม์...',
        'content': '<p>สำนักงานพัฒนาวิทยาศาสตร์และเทคโนโลยีแห่งชาติ (สวทช.) เผยพัฒนาเทคโนโลยีใหม่สำหรับตรวจสอบคุณภาพน้ำแบบเรียลไทม์...</p>',
        'date': '28 ก.พ. 68',
        'source': 'RYT9',
        'externalLink': 'https://www.ryt9.com/s/prg/12716763',
        'image': 'https://www.ryt9.com/img/files/20250529/00c20adb-0.jpg.webp',
        'sourceKey': 'ryt9_7'
    },
    {
        'id': 8,
        'type': 'normal',
        'badge': '🔵 ทั่วไป',
        'badgeClass': 'badge-normal',
        'title': 'มาตรการป้องกันมลพิษทางน้ำในพื้นที่ภาคเหนือ',
        'excerpt': 'รัฐบาลประกาศมาตรการใหม่ในการป้องกันและแก้ไขปัญหามลพิษทางน้ำ...',
        'content': '<p>รัฐบาลประกาศมาตรการใหม่ในการป้องกันและแก้ไขปัญหามลพิษทางน้ำในพื้นที่ภาคเหนือ โดยเน้นการมีส่วนร่วมของชุมชน...</p>',
        'source': 'RYT9',
        'externalLink': 'https://www.ryt9.com/s/prg/3595367',
        'image': 'https://www.ryt9.com/img/files/20250408/00c1d134-0.jpg.webp',
        'sourceKey': 'ryt9_8'
    }
]

# ✅ แก้ไขฟังก์ชัน get_ryt9_news() ให้ใช้ Hardcode
@app.route('/api/ryt9-news', methods=['GET'])
def get_ryt9_news():
    """ดึงข่าวจาก HARDCODED_NEWS (ไม่ต้องใช้ Database)"""
    try:
        print("✅ Using hardcoded news data")
        
        return jsonify({
            'success': True,
            'data': HARDCODED_NEWS,
            'count': len(HARDCODED_NEWS),
            'cached': False
        })
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# === Main Entry Point ===
if __name__ == '__main__':
    # สร้างตารางถ้ายังไม่มี
    init_db()
    port = int(os.environ.get('PORT', 8080))
    print("=" * 50)
    print("🚀 กำลังเริ่มเว็บแอปพลิเคชัน...")
    print("=" * 50)
    print(f"📊 ฐานข้อมูล: PostgreSQL (Neon)")
    print(f"🌐 เปิดเบราว์เซอร์ที่: http://localhost:{port}")
    print("=" * 50)
    app.run(debug=False, host='0.0.0.0', port=port, threaded=True)