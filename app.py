#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask web application with PostgreSQL (Neon)
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import secrets
from dotenv import load_dotenv 
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from functools import lru_cache
import time

_last_ryt9 = {'data': None, 'timestamp': 0}
CACHE_DURATION = 1800  # 30 นาที

load_dotenv()  # ← โหลดทันทีหลัง import

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(16)
app.config['JSON_AS_ASCII'] = False

# === Register API Blueprint ===
from api.index import api_bp
app.register_blueprint(api_bp)

# === Database Connection ===
def get_db():
    db_url = os.environ.get('SUPABASE_DATABASE_URL')
    if not db_url:
        raise ValueError("SUPABASE_DATABASE_URL not set in environment")
    conn = psycopg2.connect(db_url)
    conn.cursor_factory = RealDictCursor
    return conn

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
                river TEXT, tambon TEXT, amphoe TEXT, province TEXT, location TEXT
            )
        """)
        
        # ✅ ตารางข้อมูลน้ำ — ใช้ station TEXT (ไม่ใช่ station_id)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS water_data (
                id SERIAL PRIMARY KEY,
                station TEXT REFERENCES station_data(station) ON DELETE CASCADE,
                parameter TEXT, unit TEXT, location TEXT,
                check_number TEXT, value TEXT, numeric_value REAL
            )
        """)
        
        # ✅ ตารางข้อมูลดิน — ใช้ station TEXT เช่นกัน
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
        
        # ✅ Indexes — ใช้ชื่อคอลัมน์ที่ถูกต้อง (station)
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

# === Login Required Decorator ===
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
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        print(f"🔍 DEBUG: login attempt - username='{username}'")
        
        # ✅ ตรวจสอบว่าเป็น AJAX request หรือไม่
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT password FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        conn.close()
        
        print(f"🔍 DEBUG: DB result - {row}")
        
        if row and row['password'] == password:
            # ✅ เข้าสู่ระบบสำเร็จ
            session['logged_in'] = True
            session['username'] = username
            
            if is_ajax:
                # ✅ คืนค่า JSON สำหรับ AJAX
                return jsonify({
                    'success': True,
                    'message': 'เข้าสู่ระบบสำเร็จ',
                    'redirect_url': url_for('index')
                })
            else:
                # ✅ Redirect สำหรับ form submit ปกติ (รองรับกรณีไม่มี JS)
                return redirect(url_for('index'))
        else:
            # ❌ เข้าสู่ระบบไม่สำเร็จ
            if is_ajax:
                return jsonify({
                    'success': False,
                    'message': 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'
                }), 401  # HTTP 401 Unauthorized
            else:
                flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง กรุณากรอกใหม่', 'error')
                return redirect(url_for('login'))
    
    # ✅ GET request: แสดงหน้า login
    return render_template('login.html')

# === Logout Route ===
@app.route('/logout')
def logout():
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
@app.route('/')
def index():
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

# === Get Station by Code ===
def get_station_by_code(station_code):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, station, river, tambon, amphoe, province, location
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
            
            # ดึงค่าตรวจน้ำ (3 ครั้งแรกสำหรับ debug)
            for i in range(1, 4):
                check_vals = request.form.getlist(f'check{i}[]')
                if check_vals:
                    print(f"💧 check{i}={check_vals}")
            
            # ดึงค่าตรวจดิน (3 ครั้งแรกสำหรับ debug)
            for i in range(1, 4):
                soil_check_vals = request.form.getlist(f'soil_check{i}[]')
                if soil_check_vals:
                    print(f"🌱 soil_check{i}={soil_check_vals}")
            print(f"🔍 === End Debug ===\n")

            conn = get_db()
            cur = conn.cursor()
            
            # === 1. บันทึกสถานี ===
            cur.execute("""
                INSERT INTO station_data (station, river, tambon, amphoe, province, location)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (station) DO UPDATE SET
                    river = EXCLUDED.river,
                    tambon = EXCLUDED.tambon,
                    amphoe = EXCLUDED.amphoe,
                    province = EXCLUDED.province,
                    location = EXCLUDED.location
            """, (station, river, tambon, amphoe, province, location))
            print(f"✅ Saved station: {station}")

            # === 2. บันทึกข้อมูลน้ำ ===
            water_count = 0
            water_check_count = int(request.form.get('water_check_count', 14))
            
            for i in range(1, water_check_count + 1):
                check_values = request.form.getlist(f'check{i}[]')
                # ข้ามถ้าไม่มีค่าสำหรับครั้งที่ i นี้
                if not check_values or all(v == '' for v in check_values):
                    continue
                    
                for idx, param in enumerate(parameters):
                    if idx >= len(check_values):
                        break
                    value = check_values[idx].strip() if check_values[idx] else ''
                    # ข้ามถ้าค่าว่าง
                    if not value:
                        continue
                        
                    unit = units[idx].strip() if idx < len(units) else ''
                    
                    # แปลงค่าเป็นตัวเลขถ้าเป็นไปได้
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
        
        # ✅ ON DELETE CASCADE จะลบ water_data และ soil_data ให้เอง
        # ลบแค่ station_data ก็พอ
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
        station = get_station_by_code(station_code)
        if not station:
            return f"ไม่พบสถานี: {station_code}", 404
        
        water_data = get_water_data(station_code)
        soil_data = get_soil_data(station_code)
        
        # Debug
        print(f"DEBUG: water_data = {water_data}")
        print(f"DEBUG: soil_data = {soil_data}")
        
        return render_template('station_detail.html',
                             station=station,
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

            conn = get_db()
            cur = conn.cursor()

            # อัปเดตข้อมูลสถานี
            cur.execute("""
                UPDATE station_data 
                SET station = %s, river = %s, tambon = %s, amphoe = %s, province = %s, location = %s
                WHERE station = %s
            """, (station, river, tambon, amphoe, province, location, station_code))

            # ✅ ลบเฉพาะข้อมูลน้ำและดินเดิม (ไม่ต้องลบ station_data เพราะเราแค่ UPDATE)
            cur.execute('DELETE FROM water_data WHERE station = %s', (station_code.strip(),))
            cur.execute('DELETE FROM soil_data WHERE station = %s', (station_code.strip(),))
            # ❌ ลบบรรทัดนี้: cur.execute('DELETE FROM station_data WHERE station = %s', ...)

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

        # ✅ ดึงข้อมูลสถานี (แยก execute กับ fetchone)
        cur.execute("""
            SELECT river, station, location, tambon, amphoe, province
            FROM station_data WHERE station = %s
        """, (station_code.strip(),))
        station_row = cur.fetchone()

        if not station_row:
            conn.close()
            return "ไม่พบสถานี", 404

        # ✅ ดึงข้อมูลน้ำ (แยก execute กับ fetchall)
        cur.execute(r"""
            SELECT parameter, unit, check_number, value
            FROM water_data WHERE station = %s
            ORDER BY 
                NULLIF(REGEXP_REPLACE(check_number, '\D', '', 'g'), '')::INTEGER NULLS LAST,
                check_number
        """, (station_code.strip(),))
        water_rows = cur.fetchall()  # ← แยกจาก execute()

        # ✅ ดึงข้อมูลดิน (แยก execute กับ fetchall)
        cur.execute(r"""
            SELECT parameter, check_number, value
            FROM soil_data WHERE station = %s
            ORDER BY 
                NULLIF(REGEXP_REPLACE(check_number, '\D', '', 'g'), '')::INTEGER NULLS LAST,
                check_number
        """, (station_code.strip(),))
        soil_rows = cur.fetchall()  # ← แยกจาก execute()

        conn.close()

        # จัดรูปแบบข้อมูลสำหรับ template
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
                             water_data=water_data,
                             soil_data=soil_data,
                             water_check_count=water_check_count,
                             soil_check_count=soil_check_count)

    except Exception as e:
        print(f"ERROR in edit_station GET: {e}")
        import traceback
        traceback.print_exc()
        return f"Error loading edit form: {str(e)}", 500
    
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

@app.route('/map/<station_code>')
def map_page(station_code):
    # 1. ดึงข้อมูลสถานี
    station = get_station_by_code(station_code)
    if not station:
        return "ไม่พบสถานี", 404
    
    # 2. ดึงข้อมูลน้ำและดิน
    water_data = get_water_data(station_code)
    soil_data = get_soil_data(station_code)
    
    # 3. Debug: พิมพ์ตรวจสอบข้อมูล (ลบออกเมื่อใช้งานจริง)
    print(f"DEBUG map_page: station={station['station'] if station else None}")
    print(f"DEBUG map_page: water_data keys={water_data.keys() if water_data else None}")
    print(f"DEBUG map_page: soil_data keys={soil_data.keys() if soil_data else None}")
    
    # 4. ส่งข้อมูลไป template
    return render_template(
        'map.html',
        station=station,      # ✅ ส่ง object ทั้งก้อน
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
        
        # ดึง check_numbers ทั้งหมด (เรียงลำดับ)
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
        
        # ดึงพารามิเตอร์
        cur.execute("SELECT DISTINCT parameter, unit FROM water_data ORDER BY parameter")
        water_params = {row['parameter']: row['unit'] for row in cur.fetchall()}
        
        cur.execute("SELECT DISTINCT parameter FROM soil_data ORDER BY parameter")
        soil_params = [row['parameter'] for row in cur.fetchall()]
        
        # ดึงข้อมูลน้ำ: {parameter: {station: [values]}}
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
        
        # ดึงข้อมูลดิน
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
        
        # ✅ ดึงพารามิเตอร์น้ำพร้อมหน่วย
        cur.execute("SELECT DISTINCT parameter, unit FROM water_data ORDER BY parameter")
        water_params = {row['parameter']: row['unit'] for row in cur.fetchall()}
        
        # ✅ ดึงพารามิเตอร์ดิน
        cur.execute("SELECT DISTINCT parameter FROM soil_data ORDER BY parameter")
        soil_params = [row['parameter'] for row in cur.fetchall()]
        
        # ✅ ดึงค่าล่าสุดของน้ำ (ใช้ DISTINCT ON + ORDER BY เพื่อเอาแถวสุดท้าย)
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
        
        # ✅ ดึงค่าล่าสุดของดิน
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
    
@app.route('/api/latest-by-tambon')
def api_latest_by_tambon():
    """ดึงข้อมูลล่าสุดจัดกลุ่มตามตำบล + รายการรอบตรวจวัดทั้งหมด"""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # ดึงข้อมูลสถานีพร้อมตำบล
        cur.execute("""
            SELECT station, tambon, amphoe, province, river, location
            FROM station_data
            ORDER BY tambon, station
        """)
        stations = cur.fetchall()
        
        # ดึงพารามิเตอร์น้ำ
        cur.execute("SELECT DISTINCT parameter, unit FROM water_data ORDER BY parameter")
        water_params = {row['parameter']: row['unit'] for row in cur.fetchall()}
        
        # ดึงพารามิเตอร์ดิน
        cur.execute("SELECT DISTINCT parameter FROM soil_data ORDER BY parameter")
        soil_params = [row['parameter'] for row in cur.fetchall()]
        
        # ✅ 1. ดึง check_numbers ทั้งหมดของน้ำ (เรียงจากใหม่ไปเก่า)
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
        
        # ✅ 2. ดึง check_numbers ทั้งหมดของดิน (เรียงจากใหม่ไปเก่า)
        # ✅ ดึง check_numbers ทั้งหมดของดิน
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
        
        # ✅ 3. หารอบตรวจวัดล่าสุดของน้ำและดิน
        water_latest_check = water_checks[0] if water_checks else None
        soil_latest_check = soil_checks[0] if soil_checks else None
        
        # ✅ 4. กรณีไม่มีข้อมูลเลย
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
                    'check_numbers': []  # ✅ ส่งรายการว่าง
                },
                'soil': {
                    'parameters': soil_params,
                    'latest': {},
                    'check_numbers': []  # ✅ ส่งรายการว่าง
                }
            })
        
        # ✅ 5. ดึงข้อมูลน้ำเฉพาะรอบล่าสุด (สำหรับแสดงเริ่มต้น)
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
        
        # ✅ 6. ดึงข้อมูลดินเฉพาะรอบล่าสุด (สำหรับแสดงเริ่มต้น)
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
                'check_numbers': water_checks  # ✅ เพิ่ม: รายการรอบตรวจวัดของน้ำ
            },
            'soil': {
                'parameters': soil_params,
                'latest': soil_latest,
                'check_numbers': soil_checks  # ✅ เพิ่ม: รายการรอบตรวจวัดของดิน
            }
        })
        
    except Exception as e:
        print(f"❌ API Tambon Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/data-by-check')
def api_data_by_check():
    """ดึงข้อมูลตามรอบตรวจวัดที่ระบุ"""
    try:
        check_number = request.args.get('check_number')
        data_type = request.args.get('type', 'water')  # 'water' หรือ 'soil'
        
        if not check_number:
            return jsonify({'success': False, 'error': 'กรุณาระบุรอบตรวจวัด'}), 400
        
        conn = get_db()
        cur = conn.cursor()
        
        # ดึงข้อมูลสถานีพร้อมตำบล
        cur.execute("""
            SELECT station, tambon, amphoe, province, river, location
            FROM station_data
            ORDER BY tambon, station
        """)
        stations = cur.fetchall()
        
        if data_type == 'water':
            # ดึงพารามิเตอร์น้ำ
            cur.execute("SELECT DISTINCT parameter, unit FROM water_data ORDER BY parameter")
            params = {row['parameter']: row['unit'] for row in cur.fetchall()}
            
            # ดึงข้อมูลน้ำตามรอบตรวจวัด
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
            # ดึงพารามิเตอร์ดิน
            cur.execute("SELECT DISTINCT parameter FROM soil_data ORDER BY parameter")
            params = [row['parameter'] for row in cur.fetchall()]
            
            # ดึงข้อมูลดินตามรอบตรวจวัด
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

# ===== ตั้งค่าแหล่งข่าวที่ต้องการ =====
# ✅ เพิ่ม/แก้ไขลิงก์ที่นี่
NEWS_SOURCES = {
    'ryt9_1': {
        'name': 'กรมอนามัย',
        'url': 'https://www.ryt9.com/s/prg/3596933',
        'icon': '📰'
    },
    'ryt9_2': {
        'name': 'สารหนู',
        'url': 'https://www.ryt9.com/s/iq01/12768056',
        'icon': '⚠️'
    },
    'ryt9_3': {
        'name': 'รองนายก',
        'url': 'https://www.ryt9.com/s/prg/12721189',
        'icon': '🏛️'
    },
    'ryt9_4': {
        'name': 'สทนช',
        'url': 'https://www.ryt9.com/s/prg/12731088',
        'icon': '💰'
    },
    'ryt9_5': {
        'name': 'ครม',
        'url': 'https://www.ryt9.com/s/iq01/12729203',
        'icon': '💰'
    },
    'ryt9_6': {
        'name': 'สวทช',
        'url': 'https://www.ryt9.com/s/prg/12748477',
        'icon': '💰'
    },
    'ryt9_7': {
        'name': 'สวทช',
        'url': 'https://www.ryt9.com/s/prg/12716763',
        'icon': '💰'
    },
    'ryt9_8': {
        'name': 'สวทช',
        'url': 'https://www.ryt9.com/s/prg/3595367',
        'icon': '💰'
    },
}

# ===== ตัวแปรแคช (ปรับให้รองรับหลายแหล่ง) =====
_last_news = {}  # ใช้ dict แทน เพื่อแคชแยกตามแหล่ง
CACHE_DURATION = 1800  # 30 นาที

@app.route('/api/ryt9-news', methods=['GET'])
def get_ryt9_news():
    """ดึงข่าวจากทุกแหล่งใน NEWS_SOURCES"""
    now = time.time()
    
    # ✅ ตรวจสอบแคชรวม
    cache_key = 'all_sources'
    if (_last_news.get(cache_key) and
        (now - _last_news.get(f'{cache_key}_time', 0)) < CACHE_DURATION):
        print("✅ Using cached news from all sources")
        return jsonify({
            'success': True,
            'data': _last_news[cache_key],
            'count': len(_last_news[cache_key]),
            'cached': True
        })
    
    all_news = []
    news_id = 1
    
    try:
        # ✅ ดึงข่าวจากทุกแหล่งใน NEWS_SOURCES
        for source_key, source_info in NEWS_SOURCES.items():
            target_url = source_info['url']
            source_name = source_info['name']
            source_icon = source_info['icon']
            
            print(f"🔄 Fetching from {source_name}: {target_url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            try:
                response = requests.get(target_url, headers=headers, timeout=15)
                response.encoding = 'utf-8'
                
                if response.status_code != 200:
                    print(f"⚠️ Failed to fetch {source_name}: HTTP {response.status_code}")
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # 🔍 ดึงรูปภาพข่าว
                image_url = None
                og_image = soup.find('meta', property='og:image')
                if og_image and og_image.get('content'):
                    image_url = og_image['content']
                
                if not image_url:
                    twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
                    if twitter_image and twitter_image.get('content'):
                        image_url = twitter_image['content']
                
                if not image_url:
                    img_tag = soup.find('img', class_=lambda x: x and ('image' in x.lower() or 'photo' in x.lower()))
                    if img_tag:
                        image_url = img_tag.get('src') or img_tag.get('data-src')
                        if image_url and not image_url.startswith('http'):
                            image_url = f"https://www.ryt9.com{image_url}"
                
                # ค้นหา title ของข่าว
                title_elem = soup.find('h1') or soup.find('h2') or soup.find('title')
                title = title_elem.get_text(strip=True) if title_elem else f'ข่าวจาก {source_name}'
                
                # ค้นหาเนื้อหาข่าว
                content_elem = soup.find('div', class_='detail') or \
                              soup.find('div', class_='content') or \
                              soup.find('article')
                content = content_elem.get_text(strip=True)[:500] + '...' if content_elem else ''
                
                # ค้นหาเวลา
                time_elem = soup.find('time') or soup.find('span', class_='date')
                pub_date = time_elem.get_text(strip=True) if time_elem else datetime.now().strftime('%d %b %y')
                
                # สร้างรายการข่าว (1 ข่าวจากแต่ละแหล่ง)
                all_news.append({
                    'id': news_id,
                    'type': 'normal',
                    'badge': '🔵 ทั่วไป',
                    'badgeClass': 'badge-normal',
                    'title': title,
                    'excerpt': content[:150] + '...' if len(content) > 150 else content,
                    'content': f'''
                        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                    color: white; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                            <span style="background: rgba(255,255,255,0.2); padding: 4px 12px; 
                                         border-radius: 12px; font-size: 12px;">
                                {source_icon} {source_name}
                            </span>
                        </div>
                        <div style="text-align:center; margin: 20px 0;">
                            <a href="{target_url}" target="_blank"
                               style="display: inline-block; padding: 14px 28px;
                                      background: linear-gradient(135deg, #1a73e8, #0d47a1);
                                      color: white; text-decoration: none; border-radius: 8px;
                                      font-weight: 600;">
                                📰 อ่านข่าวเต็มรูปแบบ
                            </a>
                        </div>
                        <div style="margin-top: 25px; padding: 16px; background: #f8f9fa;
                                    border-left: 4px solid #1a73e8; border-radius: 6px;">
                            <p style="margin: 0; color: #555;">
                                <strong>ℹ️ หมายเหตุ:</strong> เนื้อหาข่าวฉบับเต็มแสดงบนเว็บไซต์ต้นทาง
                            </p>
                            <p style="margin: 10px 0 0 0; font-size: 13px; color: #888;">
                                🔗 <a href="{target_url}" target="_blank" style="color:#1a73e8;">{target_url}</a>
                            </p>
                        </div>
                    ''',
                    'date': pub_date,
                    'source': source_name,
                    'externalLink': target_url,
                    'image': image_url,
                    'sourceKey': source_key
                })
                news_id += 1
                
            except Exception as e:
                print(f"⚠️ Error fetching {source_name}: {e}")
                continue
        
        if not all_news:
            all_news = [{
                'id': 1, 'type': 'normal', 'badge': '🔵 ทั่วไป', 'badgeClass': 'badge-normal',
                'title': 'ไม่สามารถดึงข่าวได้ในขณะนี้',
                'excerpt': 'กรุณาลองใหม่อีกครั้งในภายหลัง',
                'content': '<p>ไม่สามารถดึงข่าวจากแหล่งที่กำหนดได้</p>',
                'date': datetime.now().strftime('%d %b %y'),
                'source': 'ระบบ', 'externalLink': '#', 'image': None
            }]
        
        print(f"✅ Fetched {len(all_news)} news items from {len(NEWS_SOURCES)} sources")
        
        # บันทึกแคช
        _last_news[cache_key] = all_news
        _last_news[f'{cache_key}_time'] = time.time()
        
        return jsonify({
            'success': True,
            'data': all_news,
            'count': len(all_news),
            'sources': len(NEWS_SOURCES)
        })
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# === Main Entry Point ===
if __name__ == '__main__':
    # ✅ สร้างตารางถ้ายังไม่มี
    init_db()
    
    port = int(os.environ.get('PORT', 8080))
    print("=" * 50)
    print("🚀 กำลังเริ่มเว็บแอปพลิเคชัน...")
    print("=" * 50)
    print(f"📊 ฐานข้อมูล: PostgreSQL (Neon)")
    print(f"🌐 เปิดเบราว์เซอร์ที่: http://localhost:{port}")
    print("=" * 50)

    app.run(debug=False, host='0.0.0.0', port=port, threaded=True)