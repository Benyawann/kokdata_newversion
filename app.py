#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask web application to display station list (PostgreSQL version)
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
import os
import secrets
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(16)

# ใช้ DATABASE_URL จาก Render
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    """สร้าง connection กับ PostgreSQL"""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# === Helper: ตรวจสอบว่าล็อกอินหรือยัง ===
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# === หน้าล็อกอิน ===
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT password FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        conn.close()
        
        if row and row['password'] == password:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง กรุณากรอกใหม่', 'error')
    
    return render_template('login.html')

# === ออกจากระบบ ===
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# Enable CORS
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

def get_stations():
    """Get all stations from PostgreSQL"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            id,
            "แม่น้ำ" as river,
            "สถานี" as station,
            "บริเวณที่เก็บ" as location,
            "ตำบล" as tambon,
            "อำเภอ" as amphoe,
            "จังหวัด" as province
        FROM station_data
        ORDER BY "แม่น้ำ", "สถานี"
    """)
    
    stations = []
    for row in cur.fetchall():
        station_dict = dict(row)
        for key, value in station_dict.items():
            if isinstance(value, str):
                station_dict[key] = value.strip()
        stations.append(station_dict)
    
    conn.close()
    return stations

@app.route('/')
def index():
    """Main page showing station list"""
    try:
        stations = get_stations()
        
        # Get unique values for filters
        unique_rivers = sorted(list(set([s['river'] for s in stations if s['river']])))
        unique_provinces = sorted(list(set([s['province'] for s in stations if s['province']])))
        unique_tambons = sorted(list(set([s['tambon'] for s in stations if s['tambon']])))
        unique_amphoes = sorted(list(set([s['amphoe'] for s in stations if s['amphoe']])))
        
        # Build hierarchical structure for cascading dropdowns
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
        
        # Convert sets to sorted lists
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
    
@app.route('/api/stations')
def api_stations():
    """API endpoint for stations data"""
    stations = get_stations()
    return jsonify(stations)

@app.route('/test')
def test():
    """Simple test endpoint"""
    return "Flask app is working!"

def get_station_by_code(station_code):
    """Get station information by station code"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            id,
            "แม่น้ำ" as river,
            "สถานี" as station,
            "บริเวณที่เก็บ" as location,
            "ตำบล" as tambon,
            "อำเภอ" as amphoe,
            "จังหวัด" as province
        FROM station_data
        WHERE TRIM("สถานี") = %s
    """, (station_code.strip(),))
    
    row = cur.fetchone()
    conn.close()
    
    if row:
        station_dict = dict(row)
        for key, value in station_dict.items():
            if isinstance(value, str):
                station_dict[key] = value.strip()
        return station_dict
    return None

def get_water_data(station_code):
    """Get water quality data for a station, organized as pivot table"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            "สิ่งที่ตรวจ" as parameter,
            "ที่ตั้ง" as location,
            "ครั้งที่ตรวจ" as check_number,
            "ค่าที่ได้" as value,
            "ค่าที่วัดได้" as numeric_value,
            "หน่วย" as unit
        FROM water_data
        WHERE TRIM("สถานี") = %s
        ORDER BY CAST(SUBSTR("ครั้งที่ตรวจ", 6) AS INTEGER), "สิ่งที่ตรวจ"
    """, (station_code.strip(),))
    
    # Organize data as pivot table
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
        
        # ดึงตัวเลขจาก "ครั้งที่ X"
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
    
    # จัดเรียง check_numbers
    numeric_checks = sorted([c for c in check_numbers if isinstance(c, int)])
    text_checks = sorted([c for c in check_numbers if not isinstance(c, int)])
    sorted_checks = numeric_checks + text_checks
    
    # Convert to list format for template
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

def get_soil_data(station_code):
    """Get soil quality data for a station, organized as pivot table"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            "สารที่ตรวจ" as parameter,
            "บริเวณจุดเก็บ" as location,
            "ครั้งที่ตรวจ" as check_number,
            "ค่าที่ได้" as value,
            "ค่าที่วัดได้" as numeric_value
        FROM soil_data
        WHERE TRIM("สถานี") = %s
        ORDER BY CAST(SUBSTR("ครั้งที่ตรวจ", 6) AS INTEGER), "สารที่ตรวจ"
    """, (station_code.strip(),))
    
    # Organize data as pivot table
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
        
        # ดึงตัวเลขจาก "ครั้งที่ X"
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
    
    # จัดเรียง check_numbers
    numeric_checks = sorted([c for c in check_numbers if isinstance(c, int)])
    text_checks = sorted([c for c in check_numbers if not isinstance(c, int)])
    sorted_checks = numeric_checks + text_checks
    
    # Convert to list format for template
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

@app.route('/add-station', methods=['GET', 'POST'])
@login_required
def add_station():
    if request.method == 'POST':
        try:
            # 1. รับข้อมูลสถานี
            station = request.form['station'].strip()
            river = request.form['river'].strip()
            tambon = request.form['tambon'].strip()
            amphoe = request.form['amphoe'].strip()
            province = request.form['province'].strip()
            location = request.form['location'].strip()

            conn = get_db_connection()
            cur = conn.cursor()

            # 2. บันทึกสถานี
            cur.execute('''
                INSERT INTO station_data ("สถานี", "แม่น้ำ", "ตำบล", "อำเภอ", "จังหวัด", "บริเวณที่เก็บ")
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (station, river, tambon, amphoe, province, location))

            # 3. รับพารามิเตอร์น้ำและดิน
            parameters = request.form.getlist('parameter[]')
            units = request.form.getlist('unit[]')
            soil_params = request.form.getlist('soil_parameter[]')

            # 4. บันทึกข้อมูลน้ำ
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
                        cur.execute('''
                            INSERT INTO water_data ("สถานี", "สิ่งที่ตรวจ", "หน่วย", "ครั้งที่ตรวจ", "ค่าที่ได้", "ค่าที่วัดได้")
                            VALUES (%s, %s, %s, %s, %s, %s)
                        ''', (station, param, unit, f'ครั้งที่ {i}', value, numeric_value))

            # 5. บันทึกข้อมูลดิน
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
                        cur.execute('''
                            INSERT INTO soil_data ("สถานี", "สารที่ตรวจ", "ครั้งที่ตรวจ", "ค่าที่ได้", "ค่าที่วัดได้")
                            VALUES (%s, %s, %s, %s, %s)
                        ''', (station, param, f'ครั้งที่ {i}', value, numeric_value))

            conn.commit()
            conn.close()
            return jsonify({'success': True})

        except Exception as e:
            print("Error saving station:", str(e))
            return jsonify({'success': False, 'message': str(e)})

    # GET: แสดงฟอร์ม
    return render_template('add_station.html')

@app.route('/delete-station/<station_code>', methods=['DELETE'])
@login_required
def delete_station(station_code):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ลบข้อมูลทั้งหมดที่เกี่ยวข้องกับสถานีนี้
        cur.execute('DELETE FROM water_data WHERE TRIM("สถานี") = %s', (station_code.strip(),))
        cur.execute('DELETE FROM soil_data WHERE TRIM("สถานี") = %s', (station_code.strip(),))
        cur.execute('DELETE FROM station_data WHERE TRIM("สถานี") = %s', (station_code.strip(),))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        print("Error deleting station:", str(e))
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/station/<station_code>')
def station_detail(station_code):
    """Display detailed information for a specific station"""
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

@app.route('/edit-station/<station_code>', methods=['GET', 'POST'])
@login_required
def edit_station(station_code):
    if request.method == 'POST':
        try:
            # รับข้อมูลใหม่
            station = request.form['station'].strip()
            river = request.form['river'].strip()
            tambon = request.form['tambon'].strip()
            amphoe = request.form['amphoe'].strip()
            province = request.form['province'].strip()
            location = request.form['location'].strip()

            conn = get_db_connection()
            cur = conn.cursor()

            # 1. อัปเดตข้อมูลสถานี
            cur.execute('''
                UPDATE station_data 
                SET "สถานี" = %s, "แม่น้ำ" = %s, "ตำบล" = %s, "อำเภอ" = %s, "จังหวัด" = %s, "บริเวณที่เก็บ" = %s
                WHERE TRIM("สถานี") = %s
            ''', (station, river, tambon, amphoe, province, location, station_code))

            # 2. ลบข้อมูลน้ำและดินเดิม
            cur.execute('DELETE FROM water_data WHERE TRIM("สถานี") = %s', (station_code,))
            cur.execute('DELETE FROM soil_data WHERE TRIM("สถานี") = %s', (station_code,))

            # 3. รับพารามิเตอร์ใหม่
            parameters = request.form.getlist('parameter[]')
            units = request.form.getlist('unit[]')
            soil_params = request.form.getlist('soil_parameter[]') 

            # 4. บันทึกข้อมูลน้ำ
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
                        cur.execute('''
                            INSERT INTO water_data ("สถานี", "สิ่งที่ตรวจ", "หน่วย", "ครั้งที่ตรวจ", "ค่าที่ได้", "ค่าที่วัดได้")
                            VALUES (%s, %s, %s, %s, %s, %s)
                        ''', (station, param, unit, f'ครั้งที่ {i}', value, numeric_value))

            # 5. บันทึกข้อมูลดิน
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
                        cur.execute('''
                            INSERT INTO soil_data ("สถานี", "สารที่ตรวจ", "ครั้งที่ตรวจ", "ค่าที่ได้", "ค่าที่วัดได้")
                            VALUES (%s, %s, %s, %s, %s)
                        ''', (station, param, f'ครั้งที่ {i}', value, numeric_value))

            conn.commit()
            conn.close()
            return jsonify({'success': True})

        except Exception as e:
            print("Error updating station:", str(e))
            return jsonify({'success': False, 'message': str(e)})

    # GET: ดึงข้อมูลเดิมมา pre-fill
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute('''
            SELECT "แม่น้ำ" as river, "สถานี" as station, "บริเวณที่เก็บ" as location,
                   "ตำบล" as tambon, "อำเภอ" as amphoe, "จังหวัด" as province
            FROM station_data WHERE TRIM("สถานี") = %s
        ''', (station_code.strip(),))
        station_row = cur.fetchone()

        if not station_row:
            return "ไม่พบสถานี", 404

        station_data = dict(station_row)

        # ดึงข้อมูลน้ำ
        cur.execute('''
            SELECT "สิ่งที่ตรวจ" as parameter, "หน่วย" as unit, "ครั้งที่ตรวจ" as check_number, "ค่าที่ได้" as value
            FROM water_data WHERE TRIM("สถานี") = %s
            ORDER BY CAST(SUBSTR("ครั้งที่ตรวจ", 6) AS INTEGER)
        ''', (station_code.strip(),))
        water_rows = cur.fetchall()

        # ดึงข้อมูลดิน
        cur.execute('''
            SELECT "สารที่ตรวจ" as parameter, "ครั้งที่ตรวจ" as check_number, "ค่าที่ได้" as value
            FROM soil_data WHERE TRIM("สถานี") = %s
            ORDER BY CAST(SUBSTR("ครั้งที่ตรวจ", 6) AS INTEGER)
        ''', (station_code.strip(),))
        soil_rows = cur.fetchall()

        conn.close()

        # ประมวลผลข้อมูลน้ำ
        water_data = {}
        for row in water_rows:
            param = row['parameter']
            if param not in water_data:
                water_data[param] = {'unit': row['unit'], 'checks': {}}
            check_num = int(row['check_number'].replace('ครั้งที่', '').strip())
            water_data[param]['checks'][check_num] = row['value']

        # ประมวลผลข้อมูลดิน
        soil_data = {}
        for row in soil_rows:
            param = row['parameter']
            if param not in soil_data:
                soil_data[param] = {'checks': {}}
            check_num = int(row['check_number'].replace('ครั้งที่', '').strip())
            soil_data[param]['checks'][check_num] = row['value']

        # คำนวณจำนวนครั้งสูงสุด
        water_check_count = len(next(iter(water_data.values()))['checks']) if water_data else 14
        soil_check_count = len(next(iter(soil_data.values()))['checks']) if soil_data else 8

        return render_template('edit_station.html',
                             station=station_data,
                             water_data=water_data,
                             soil_data=soil_data,
                             water_check_count=water_check_count,
                             soil_check_count=soil_check_count)

    except Exception as e:
        return f"Error loading edit form: {str(e)}", 500