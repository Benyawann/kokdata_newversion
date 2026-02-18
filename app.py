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

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(16)

# === Database Connection (PostgreSQL/Neon) ===
def get_db():
    """เชื่อมต่อ PostgreSQL"""
    conn = psycopg2.connect(
        host=os.environ['POSTGRES_HOST'],
        database=os.environ['POSTGRES_DATABASE'],
        user=os.environ['POSTGRES_USER'],
        password=os.environ['POSTGRES_PASSWORD'],
        port=os.environ.get('POSTGRES_PORT', '5432')
    )
    # ใช้ RealDictCursor เพื่อเข้าถึง column ด้วยชื่อ
    conn.cursor_factory = RealDictCursor
    return conn

# === Initialize Database ===
def init_db():
    """สร้างตารางทั้งหมดถ้ายังไม่มี (PostgreSQL syntax)"""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # ตารางสถานี
        cur.execute("""
            CREATE TABLE IF NOT EXISTS station_data (
                id SERIAL PRIMARY KEY,
                station TEXT UNIQUE NOT NULL,
                river TEXT,
                tambon TEXT,
                amphoe TEXT,
                province TEXT,
                location TEXT
            )
        """)
        
        # ตารางข้อมูลน้ำ
        cur.execute("""
            CREATE TABLE IF NOT EXISTS water_data (
                id SERIAL PRIMARY KEY,
                station_id INTEGER REFERENCES station_data(id) ON DELETE CASCADE,
                parameter TEXT,
                unit TEXT,
                location TEXT,
                check_number TEXT,
                value TEXT,
                numeric_value REAL
            )
        """)
        
        # ตารางข้อมูลดิน
        cur.execute("""
            CREATE TABLE IF NOT EXISTS soil_data (
                id SERIAL PRIMARY KEY,
                station_id INTEGER REFERENCES station_data(id) ON DELETE CASCADE,
                parameter TEXT,
                location TEXT,
                check_number TEXT,
                value TEXT,
                numeric_value REAL
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
        
        # สร้าง indexes เพื่อความเร็ว
        cur.execute("CREATE INDEX IF NOT EXISTS idx_water_station ON water_data(station_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_soil_station ON soil_data(station_id)")
        
        # สร้าง user admin เริ่มต้น (ถ้ายังไม่มี)
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
        username = request.form['username']
        password = request.form['password']
        
        print(f"DEBUG: กรอก username='{username}', password='{password}'")
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT password FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        conn.close()
        
        print(f"DEBUG: ดึงข้อมูลจาก DB ได้: {row}")
        
        if row and row['password'] == password:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง กรุณากรอกใหม่', 'error')
    
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
    cur.execute("""
        SELECT parameter, unit, location, check_number, value, numeric_value
        FROM water_data
        WHERE TRIM(station) = %s
        ORDER BY CAST(SUBSTRING(check_number FROM 6) AS INTEGER), parameter
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
    cur.execute("""
        SELECT parameter, location, check_number, value, numeric_value
        FROM soil_data
        WHERE TRIM(station) = %s
        ORDER BY CAST(SUBSTRING(check_number FROM 6) AS INTEGER), parameter
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
            station = request.form['station'].strip()
            river = request.form['river'].strip()
            tambon = request.form['tambon'].strip()
            amphoe = request.form['amphoe'].strip()
            province = request.form['province'].strip()
            location = request.form['location'].strip()

            conn = get_db()
            cur = conn.cursor()

            # บันทึกสถานี
            cur.execute("""
                INSERT INTO station_data (station, river, tambon, amphoe, province, location)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (station, river, tambon, amphoe, province, location))
            
            # ดึง id ที่เพิ่ง insert
            cur.execute('SELECT id FROM station_data WHERE station = %s', (station,))
            station_id = cur.fetchone()['id']

            parameters = request.form.getlist('parameter[]')
            units = request.form.getlist('unit[]')
            soil_params = request.form.getlist('soil_parameter[]')

            # บันทึกข้อมูลน้ำ
            for i in range(1, 15):
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
                            INSERT INTO water_data (station_id, parameter, unit, location, check_number, value, numeric_value)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (station_id, param, unit, location, f'ครั้งที่ {i}', value, numeric_value))

            # บันทึกข้อมูลดิน
            for i in range(1, 9):
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
                            INSERT INTO soil_data (station_id, parameter, location, check_number, value, numeric_value)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (station_id, param, location, f'ครั้งที่ {i}', value, numeric_value))

            conn.commit()
            conn.close()
            return jsonify({'success': True})

        except Exception as e:
            print("Error saving station:", str(e))
            return jsonify({'success': False, 'message': str(e)})

    return render_template('add_station.html')

# === Delete Station Route ===
@app.route('/delete-station/<station_code>', methods=['DELETE'])
@login_required
def delete_station(station_code):
    try:
        conn = get_db()
        cur = conn.cursor()
        # ลบข้อมูลในตารางลูกก่อน (Foreign Key จะจัดการให้ถ้ามี ON DELETE CASCADE)
        cur.execute('DELETE FROM water_data WHERE TRIM(station) = %s', (station_code.strip(),))
        cur.execute('DELETE FROM soil_data WHERE TRIM(station) = %s', (station_code.strip(),))
        cur.execute('DELETE FROM station_data WHERE TRIM(station) = %s', (station_code.strip(),))
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
        return render_template('station_detail.html',
                             station=station,
                             water_data=water_data,
                             soil_data=soil_data)
    except Exception as e:
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
                WHERE TRIM(station) = %s
            """, (station, river, tambon, amphoe, province, location, station_code))

            # ลบข้อมูลน้ำและดินเดิม
            cur.execute('DELETE FROM water_data WHERE TRIM(station) = %s', (station_code,))
            cur.execute('DELETE FROM soil_data WHERE TRIM(station) = %s', (station_code,))

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
                            INSERT INTO water_data (station_id, parameter, unit, location, check_number, value, numeric_value)
                            VALUES ((SELECT id FROM station_data WHERE station = %s), %s, %s, %s, %s, %s, %s)
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
                            INSERT INTO soil_data (station_id, parameter, location, check_number, value, numeric_value)
                            VALUES ((SELECT id FROM station_data WHERE station = %s), %s, %s, %s, %s, %s)
                        """, (station, param, location, f'ครั้งที่ {i}', value, numeric_value))
            
            conn.commit()
            conn.close()
            return jsonify({'success': True})

        except Exception as e:
            print("Error updating station:", str(e))
            return jsonify({'success': False, 'message': str(e)})

    # GET: ดึงข้อมูลเดิมมา pre-fill
    try:
        conn = get_db()
        cur = conn.cursor()

        station_row = cur.execute("""
            SELECT river, station, location, tambon, amphoe, province
            FROM station_data WHERE TRIM(station) = %s
        """, (station_code.strip(),)).fetchone()

        if not station_row:
            return "ไม่พบสถานี", 404

        water_rows = cur.execute("""
            SELECT parameter, unit, check_number, value
            FROM water_data WHERE TRIM(station) = %s
            ORDER BY CAST(SUBSTRING(check_number FROM 6) AS INTEGER)
        """, (station_code.strip(),)).fetchall()

        soil_rows = cur.execute("""
            SELECT parameter, check_number, value
            FROM soil_data WHERE TRIM(station) = %s
            ORDER BY CAST(SUBSTRING(check_number FROM 6) AS INTEGER)
        """, (station_code.strip(),)).fetchall()

        conn.close()

        water_data = {}
        for row in water_rows:
            param = row['parameter']
            if param not in water_data:
                water_data[param] = {'unit': row['unit'], 'checks': {}}
            check_num = int(row['check_number'].replace('ครั้งที่', '').strip())
            water_data[param]['checks'][check_num] = row['value']

        soil_data = {}
        for row in soil_rows:
            param = row['parameter']
            if param not in soil_data:
                soil_data[param] = {'checks': {}}
            check_num = int(row['check_number'].replace('ครั้งที่', '').strip())
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
        return f"Error loading edit form: {str(e)}", 500

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