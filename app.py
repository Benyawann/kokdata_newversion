#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask web application to display station list
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
import sqlite3
import os
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(16)  # จำเป็นสำหรับ session
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kok_data.db")
print("DB Path:", os.path.abspath(DB_PATH))

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
        
        print(f"DEBUG: กรอก username='{username}', password='{password}'")  # ← เพิ่มบรรทัดนี้
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT password FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        conn.close()
        
        print(f"DEBUG: ดึงข้อมูลจาก DB ได้: {row}")  # ← เพิ่มบรรทัดนี้
        
        if row and row[0] == password:
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

# Enable CORS and remove security restrictions for local development
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

def get_stations():
    """Get all stations from database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    cursor = conn.execute("""
        SELECT 
            id,
            "\ufeffแม่น้ำ" as river,
            "สถานี" as station,
            "บริเวณที่เก็บ" as location,
            "ตำบล" as tambon,
            "อำเภอ" as amphoe,
            "จังหวัด" as province
        FROM station_data
        ORDER BY "\ufeffแม่น้ำ", "สถานี"
    """)
    
    stations = []
    for row in cursor.fetchall():
        station_dict = dict(row)
        # Clean up whitespace from all string fields
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
        # Structure: {province: {amphoe: [tambon1, tambon2, ...]}}
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    cursor = conn.execute("""
        SELECT 
            id,
            "\ufeffแม่น้ำ" as river,
            "สถานี" as station,
            "บริเวณที่เก็บ" as location,
            "ตำบล" as tambon,
            "อำเภอ" as amphoe,
            "จังหวัด" as province
        FROM station_data
        WHERE TRIM("สถานี") = ?
    """, (station_code.strip(),))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        station_dict = dict(row)
        # Clean up whitespace
        for key, value in station_dict.items():
            if isinstance(value, str):
                station_dict[key] = value.strip()
        return station_dict
    return None

def get_water_data(station_code):
    """Get water quality data for a station, organized as pivot table"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    cursor = conn.execute("""
        SELECT 
            "\ufeffสิ่งที่ตรวจ" as parameter,
            "ที่ตั้ง" as location,
            "ครั้งที่ตรวจ" as check_number,
            "ค่าที่ได้" as value,
            "ค่าที่วัดได้" as numeric_value,
            "หน่วย" as unit
        FROM water_data
        WHERE TRIM("สถานี") = ?
        ORDER BY CAST(SUBSTR("ครั้งที่ตรวจ", 6) AS INTEGER), "\ufeffสิ่งที่ตรวจ"
    """, (station_code.strip(),))
    
    # Organize data as pivot table: {parameter: {check_number: value}}
    pivot_data = {}
    numeric_data = {}
    check_numbers = []  # เปลี่ยนจาก set() เป็น list เพื่อรักษาลำดับ
    unit_info = {}
    
    for row in cursor.fetchall():
        row_dict = dict(row)
        for key, value in row_dict.items():
            if isinstance(value, str):
                row_dict[key] = value.strip()
        
        param = row_dict['parameter']
        check_num = row_dict['check_number']
        value = row_dict['value']
        numeric_value = row_dict.get('numeric_value', 0) if row_dict.get('numeric_value') is not None else 0
        unit = row_dict['unit']
        
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    cursor = conn.execute("""
        SELECT 
            "สารที่ตรวจ" as parameter,
            "บริเวณจุดเก็บ" as location,
            "ครั้งที่ตรวจ" as check_number,
            "ค่าที่ได้" as value,
            "ค่าที่วัดได้" as numeric_value
        FROM soil_data
        WHERE TRIM("สถานี") = ?
        ORDER BY CAST(SUBSTR("ครั้งที่ตรวจ", 6) AS INTEGER), "สารที่ตรวจ"
    """, (station_code.strip(),))
    
    # Organize data as pivot table: {parameter: {check_number: value}}
    pivot_data = {}
    numeric_data = {}
    check_numbers = []  # เปลี่ยนจาก set() เป็น list เพื่อรักษาลำดับ
    
    for row in cursor.fetchall():
        row_dict = dict(row)
        for key, value in row_dict.items():
            if isinstance(value, str):
                row_dict[key] = value.strip()
        
        param = row_dict['parameter']
        check_num = row_dict['check_number']
        value = row_dict['value']
        numeric_value = row_dict.get('numeric_value', 0) if row_dict.get('numeric_value') is not None else 0
        
        if param not in pivot_data:
            pivot_data[param] = {}
            numeric_data[param] = {}
        
        # ดึงตัวเลขจาก "ครั้งที่ X"
        try:
            check_num_int = int(check_num.split('ครั้งที่')[-1].strip())
            # เพิ่มเฉพาะตัวเลขที่ยังไม่มีใน list
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
    
    # จัดเรียง check_numbers (ถ้ามีทั้งตัวเลขและ text)
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

            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()

            # 2. บันทึกสถานี
            cur.execute('''
                INSERT INTO station_data ("สถานี", "\ufeffแม่น้ำ", "ตำบล", "อำเภอ", "จังหวัด", "บริเวณที่เก็บ")
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (station, river, tambon, amphoe, province, location))

            # 3. รับพารามิเตอร์น้ำและดิน
            parameters = request.form.getlist('parameter[]')
            units = request.form.getlist('unit[]')
            soil_params = request.form.getlist('soil_parameter[]')  # ⚠️ ลืมประกาศ!

            # 4. บันทึกข้อมูลน้ำ (14 ครั้ง)
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
                        cur.execute('''
                            INSERT INTO water_data ("สถานี", "\ufeffสิ่งที่ตรวจ", "หน่วย", "ครั้งที่ตรวจ", "ค่าที่ได้", "ค่าที่วัดได้")
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (station, param, unit, f'ครั้งที่ {i}', value, numeric_value))

            # 5. บันทึกข้อมูลดิน (8 ครั้ง)
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
                        cur.execute('''
                            INSERT INTO soil_data ("สถานี", "สารที่ตรวจ", "ครั้งที่ตรวจ", "ค่าที่ได้", "ค่าที่วัดได้")
                            VALUES (?, ?, ?, ?, ?)
                        ''', (station, param, f'ครั้งที่ {i}', value, numeric_value))
                        pass

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
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # ลบข้อมูลทั้งหมดที่เกี่ยวข้องกับสถานีนี้
        cur.execute('DELETE FROM water_data WHERE TRIM("สถานี") = ?', (station_code.strip(),))
        cur.execute('DELETE FROM soil_data WHERE TRIM("สถานี") = ?', (station_code.strip(),))
        cur.execute('DELETE FROM station_data WHERE TRIM("สถานี") = ?', (station_code.strip(),))
        
        conn.commit()
        conn.close()
        pass
        
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

            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()

            # 1. อัปเดตข้อมูลสถานี
            cur.execute('''
                UPDATE station_data 
                SET "สถานี" = ?, "\ufeffแม่น้ำ" = ?, "ตำบล" = ?, "อำเภอ" = ?, "จังหวัด" = ?, "บริเวณที่เก็บ" = ?
                WHERE TRIM("สถานี") = ?
            ''', (station, river, tambon, amphoe, province, location, station_code))

            # 2. ลบข้อมูลน้ำและดินเดิม
            cur.execute('DELETE FROM water_data WHERE TRIM("สถานี") = ?', (station_code,))
            cur.execute('DELETE FROM soil_data WHERE TRIM("สถานี") = ?', (station_code,))

            # 3. รับพารามิเตอร์ใหม่
            parameters = request.form.getlist('parameter[]')
            units = request.form.getlist('unit[]')
            soil_params = request.form.getlist('soil_parameter[]') 

            # 4. บันทึกน้ำ (14 ครั้ง)
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
                        cur.execute('''
                            INSERT INTO water_data ("สถานี", "\ufeffสิ่งที่ตรวจ", "หน่วย", "ครั้งที่ตรวจ", "ค่าที่ได้", "ค่าที่วัดได้")
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (station, param, unit, f'ครั้งที่ {i}', value, numeric_value))

            # 5. บันทึกดิน (8 ครั้ง)
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
                        cur.execute('''
                            INSERT INTO soil_data ("สถานี", "สารที่ตรวจ", "ครั้งที่ตรวจ", "ค่าที่ได้", "ค่าที่วัดได้")
                            VALUES (?, ?, ?, ?, ?)
                        ''', (station, param, f'ครั้งที่ {i}', value, numeric_value))

            conn.commit()
            conn.close()
            return jsonify({'success': True})

        except Exception as e:
            print("Error updating station:", str(e))
            return jsonify({'success': False, 'message': str(e)})

    # GET: ดึงข้อมูลเดิมมา pre-fill
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        station_row = conn.execute('''
            SELECT "\ufeffแม่น้ำ" as river, "สถานี" as station, "บริเวณที่เก็บ" as location,
                   "ตำบล" as tambon, "อำเภอ" as amphoe, "จังหวัด" as province
            FROM station_data WHERE TRIM("สถานี") = ?
        ''', (station_code.strip(),)).fetchone()

        if not station_row:
            return "ไม่พบสถานี", 404

        station_data = dict(station_row)

        water_rows = conn.execute('''
            SELECT "\ufeffสิ่งที่ตรวจ" as parameter, "หน่วย" as unit, "ครั้งที่ตรวจ" as check_number, "ค่าที่ได้" as value
            FROM water_data WHERE TRIM("สถานี") = ?
            ORDER BY CAST(SUBSTR("ครั้งที่ตรวจ", 6) AS INTEGER)
        ''', (station_code.strip(),)).fetchall()

        soil_rows = conn.execute('''
            SELECT "สารที่ตรวจ" as parameter, "ครั้งที่ตรวจ" as check_number, "ค่าที่ได้" as value
            FROM soil_data WHERE TRIM("สถานี") = ?
            ORDER BY CAST(SUBSTR("ครั้งที่ตรวจ", 6) AS INTEGER)
        ''', (station_code.strip(),)).fetchall()

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
            pass

        return render_template('edit_station.html',
                             station=station_data,
                             water_data=water_data,
                             soil_data=soil_data)
                             

    except Exception as e:
        return f"Error loading edit form: {str(e)}", 500
    
if __name__ == '__main__':
    # Get port from environment variable or use default
    port = int(os.environ.get('PORT', 8080))
    print("=" * 50)
    print("🚀 กำลังเริ่มเว็บแอปพลิเคชัน...")
    print("=" * 50)
    print(f"📊 ฐานข้อมูล: {DB_PATH}")
    print(f"🌐 เปิดเบราว์เซอร์ที่: http://localhost:{port}")
    print(f"🌐 หรือ: http://127.0.0.1:{port}")
    print("=" * 50)
    print("กด Ctrl+C เพื่อหยุดการทำงาน")
    print("=" * 50)
    try:
        # Use threaded=True to handle multiple requests
        # Use 0.0.0.0 to allow connections from all interfaces
        # Port 8080 instead of 5000 (5000 is used by AirPlay on macOS)
        app.run(debug=False, host='0.0.0.0', port=port, threaded=True, use_reloader=False)
    except OSError as e:
        if "Address already in use" in str(e):
            print("\n❌ Error: Port 8080 ถูกใช้งานอยู่แล้ว")
            print("💡 แนะนำ: ปิดโปรแกรมอื่นที่ใช้ port 8080 หรือเปลี่ยน port")
            print("   ตัวอย่าง: app.run(debug=True, host='0.0.0.0', port=8081)")
        else:
            print(f"\n❌ Error: {e}")