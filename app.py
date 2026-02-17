#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask web application to display station list
"""
import os
import sys  # ✅ เพิ่มสำหรับการตรวจสอบข้อผิดพลาด

# ✅ นำเข้า psycopg2 ก่อนการใช้งานทั้งหมด
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError as e:
    print(f"❌ ข้อผิดพลาด: ไม่พบ psycopg2 - {e}", file=sys.stderr)
    print("💡 ติดตั้งด้วยคำสั่ง: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
import secrets

def get_pg_connection():
    """เชื่อมต่อฐานข้อมูลผ่าน DATABASE_URL เท่านั้น"""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        raise Exception("❌ ไม่พบ DATABASE_URL - ตั้งค่าด้วย fly secrets set")
    
    # แปลง postgres:// เป็น postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    print(f"✅ เชื่อมต่อฐานข้อมูลด้วย DATABASE_URL (ซ่อนรหัส)")
    return psycopg2.connect(database_url)

def pg_execute(query, params=None, fetch=False):
    """รันคำสั่ง SQL กับ PostgreSQL"""
    conn = get_pg_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(query, params)
        if fetch:
            result = cur.fetchall()
            conn.close()
            return result
        else:
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"❌ SQL Error: {e}", file=sys.stderr)
        raise e

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

@app.route('/debug-branch')
def debug_branch():
    """ตรวจสอบ Branch ที่เชื่อมต่อ"""
    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        
        # ตรวจสอบ Branch ที่ใช้
        cur.execute("SELECT current_database()")
        branch = cur.fetchone()[0]
        
        # ตรวจสอบว่ามีตาราง station_data หรือไม่
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.tables 
                WHERE table_name = 'station_data'
            )
        """)
        has_table = cur.fetchone()[0]
        
        conn.close()
        
        return {
            'connected_branch': branch,
            'has_station_data': has_table,
            'database_url_sample': os.environ.get('DATABASE_URL', '')[:50] + '...'
        }
    except Exception as e:
        return {'error': str(e)}

# === หน้าล็อกอิน ===
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        query = "SELECT password FROM users WHERE username = %s"
        rows = pg_execute(query, (username,), fetch=True)
        
        if rows and rows[0]['password'] == password:
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
    """Get all stations from PostgreSQL"""
    query = """
        SELECT 
            id,
            river,
            station,
            location,
            tambon,
            amphoe,
            province
        FROM station_data
        ORDER BY id ASC
    """
    rows = pg_execute(query, fetch=True)
    
    # Clean whitespace
    stations = []
    for row in rows:
        station_dict = dict(row)
        for key, value in station_dict.items():
            if isinstance(value, str):
                station_dict[key] = value.strip()
        stations.append(station_dict)
    
    return stations

@app.route('/')
def index():
    """Main page showing station list"""
    try:
        stations = get_stations()
        print(f"DEBUG: ได้ {len(stations)} สถานี")
        if stations:
            print(f"ตัวอย่าง: {stations[0]}")
        
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
        print(f"ERROR: {e}")
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
    """Get station information by station code from PostgreSQL"""
    query = """
        SELECT 
            id,
            river,
            station,
            location,
            tambon,
            amphoe,
            province
        FROM station_data
        WHERE TRIM(station) = %s
    """
    rows = pg_execute(query, (station_code.strip(),), fetch=True)
    
    if rows:
        station_dict = dict(rows[0])
        # Clean up whitespace
        for key, value in station_dict.items():
            if isinstance(value, str):
                station_dict[key] = value.strip()
        return station_dict
    return None

def get_water_data(station_code):
    station_code_clean = station_code.strip()
    print(f"🔍 get_water_data: ค่า station_code_clean = '{station_code_clean}'")
    
    query = """
        SELECT parameter, location, check_number, value, numeric_value, unit
        FROM water_data
        WHERE LOWER(TRIM(station)) = LOWER(%s)
    """
    rows = pg_execute(query, (station_code_clean,), fetch=True)
    print(f"✅ ดึงได้ {len(rows)} แถว จาก water_data")

    if not rows:
        return {
            'pivot_list_filtered': [],
            'check_numbers': [],
            'units': {},
            'parameters': []
        }
    
    # ประกาศตัวแปร
    pivot_data = {}
    numeric_data = {}
    check_numbers = []
    unit_info = {}
    
    for row in rows:
        # ✅ ตรวจสอบ None ก่อนใช้งาน
        param = row['parameter'] if row['parameter'] is not None else 'ไม่ระบุ'
        check_num = row['check_number'] if row['check_number'] is not None else 'ไม่ระบุ'
        value = row['value'] if row['value'] is not None else ''
        numeric_value = row.get('numeric_value', 0) if row.get('numeric_value') is not None else 0
        unit = row['unit'] if row['unit'] is not None else ''
        
        if param not in pivot_data:
            pivot_data[param] = {}
            numeric_data[param] = {}
            unit_info[param] = unit
        
        try:
            # ✅ ตรวจสอบ check_num ก่อนแปลง
            if isinstance(check_num, str) and 'ครั้งที่' in check_num:
                check_num_int = int(check_num.split('ครั้งที่')[-1].strip())
                if check_num_int not in check_numbers:
                    check_numbers.append(check_num_int)
                pivot_data[param][check_num_int] = value
                numeric_data[param][check_num_int] = numeric_value
            else:
                if check_num not in check_numbers:
                    check_numbers.append(check_num)
                pivot_data[param][check_num] = value
                numeric_data[param][check_num] = numeric_value
        except (ValueError, IndexError, AttributeError):
            # ถ้าไม่สามารถแปลงได้ ให้ใช้ค่าเดิม
            if check_num not in check_numbers:
                check_numbers.append(check_num)
            pivot_data[param][check_num] = value
            numeric_data[param][check_num] = numeric_value
    
    # จัดเรียง check_numbers
    numeric_checks = sorted([c for c in check_numbers if isinstance(c, int)])
    text_checks = sorted([c for c in check_numbers if not isinstance(c, int)])
    sorted_checks = numeric_checks + text_checks
    
    # Convert to list format
    parameters = sorted(pivot_data.keys())
    pivot_list_filtered = []
    for param in parameters:
        row_data_filtered = {
            'parameter': param, 
            'check_values': {}, 
            'numeric_values': {}, 
            'unit': unit_info.get(param, '')
        }
        for check_num in sorted_checks:
            value = pivot_data[param].get(check_num, None)
            numeric_value = numeric_data[param].get(check_num, 0)
            row_data_filtered['check_values'][str(check_num)] = value if value else None
            row_data_filtered['numeric_values'][str(check_num)] = numeric_value
        pivot_list_filtered.append(row_data_filtered)
    
    return {
        'pivot_list_filtered': pivot_list_filtered,
        'check_numbers': sorted_checks,
        'units': unit_info,
        'parameters': parameters
    }

def get_soil_data(station_code):
    station_code_clean = station_code.strip()
    print(f"🔍 get_soil_data: ค่า station_code_clean = '{station_code_clean}'")
    
    query = """
        SELECT parameter, location, check_number, value, numeric_value
        FROM soil_data
        WHERE LOWER(TRIM(station)) = LOWER(%s)
    """
    rows = pg_execute(query, (station_code_clean,), fetch=True)
    print(f"✅ ดึงได้ {len(rows)} แถว จาก soil_data")

    if not rows:
        return {
            'pivot_list_filtered': [],
            'check_numbers': [],
            'parameters': []
        }
    
    # ประกาศตัวแปร
    pivot_data = {}
    numeric_data = {}
    check_numbers = []
    
    for row in rows:
        # ✅ ตรวจสอบ None ก่อนใช้งาน
        param = row['parameter'] if row['parameter'] is not None else 'ไม่ระบุ'
        check_num = row['check_number'] if row['check_number'] is not None else 'ไม่ระบุ'
        value = row['value'] if row['value'] is not None else ''
        numeric_value = row.get('numeric_value', 0) if row.get('numeric_value') is not None else 0
        
        if param not in pivot_data:
            pivot_data[param] = {}
            numeric_data[param] = {}
        
        try:
            # ✅ ตรวจสอบ check_num ก่อนแปลง
            if isinstance(check_num, str) and 'ครั้งที่' in check_num:
                check_num_int = int(check_num.split('ครั้งที่')[-1].strip())
                if check_num_int not in check_numbers:
                    check_numbers.append(check_num_int)
                pivot_data[param][check_num_int] = value
                numeric_data[param][check_num_int] = numeric_value
            else:
                if check_num not in check_numbers:
                    check_numbers.append(check_num)
                pivot_data[param][check_num] = value
                numeric_data[param][check_num] = numeric_value
        except (ValueError, IndexError, AttributeError):
            # ถ้าไม่สามารถแปลงได้ ให้ใช้ค่าเดิม
            if check_num not in check_numbers:
                check_numbers.append(check_num)
            pivot_data[param][check_num] = value
            numeric_data[param][check_num] = numeric_value
    
    # จัดเรียง check_numbers
    numeric_checks = sorted([c for c in check_numbers if isinstance(c, int)])
    text_checks = sorted([c for c in check_numbers if not isinstance(c, int)])
    sorted_checks = numeric_checks + text_checks
    
    parameters = sorted(pivot_data.keys())
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
        'pivot_list_filtered': pivot_list_filtered,
        'check_numbers': sorted_checks,
        'parameters': parameters
    }

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

            # ✅ ตรวจสอบก่อน insert
            check_query = "SELECT 1 FROM station_data WHERE TRIM(station) = %s"
            exists = pg_execute(check_query, (station,), fetch=True)
            
            if exists:
                flash('สถานีนี้มีอยู่แล้ว', 'error')
                return redirect(url_for('add_station'))

            # ✅ insert เฉพาะเมื่อไม่มีซ้ำ
            query = '''
                INSERT INTO station_data (station, river, tambon, amphoe, province, location)
                VALUES (%s, %s, %s, %s, %s, %s)
            '''
            pg_execute(query, (station, river, tambon, amphoe, province, location))

            # ... (บันทึกข้อมูลน้ำและดินเหมือนเดิม)

            return redirect(url_for('index')) 

        except Exception as e:
            print("Error saving station:", str(e))
            flash('เกิดข้อผิดพลาด: ' + str(e), 'error')
            return redirect(url_for('add_station'))
        
@app.route('/delete-station/<station_code>', methods=['DELETE'])
@login_required
def delete_station(station_code):
    try:
        # ใช้ชื่อคอลัมน์ภาษาอังกฤษ
        pg_execute('DELETE FROM water_data WHERE TRIM(station) = %s', (station_code.strip(),))
        pg_execute('DELETE FROM soil_data WHERE TRIM(station) = %s', (station_code.strip(),))
        pg_execute('DELETE FROM station_data WHERE TRIM(station) = %s', (station_code.strip(),))
        
        return jsonify({'success': True})
    except Exception as e:
        print("Error deleting station:", str(e))
        return jsonify({'success': False, 'message': str(e)}), 500
    
@app.route('/station/<station_code>')
def station_detail(station_code):
    try:
        station = get_station_by_code(station_code)
        if not station:
            return f"ไม่พบสถานี: {station_code}", 404
        
        water_data = get_water_data(station_code)
        soil_data = get_soil_data(station_code)
        
        # เพิ่ม debug
        print(f"DEBUG water_data: {len(water_data['pivot_list_filtered'])} parameters")
        print(f"DEBUG soil_data: {len(soil_data['pivot_list_filtered'])} parameters")
        
        return render_template('station_detail.html',
                             station=station,
                             water_data=water_data,
                             soil_data=soil_data)
    except Exception as e:
        print(f"ERROR in station_detail: {e}")
        return f"Error: {e}", 500
    
@app.route('/api/water/<station_code>')
def api_water(station_code):
    water_data = get_water_data(station_code)
    return jsonify(water_data)

def api_water(station_code):
    water_data = get_water_data(station_code)
    return jsonify(water_data)

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

            # 1. อัปเดตข้อมูลสถานี
            update_query = '''
                UPDATE station_data 
                SET station = %s, river = %s, tambon = %s, amphoe = %s, province = %s, location = %s
                WHERE TRIM(station) = %s
                '''
            pg_execute(update_query, (station, river, tambon, amphoe, province, location, station_code))

            # 2. ลบข้อมูลน้ำและดินเดิม
            pg_execute('DELETE FROM water_data WHERE TRIM(station) = %s', (station_code,))
            pg_execute('DELETE FROM soil_data WHERE TRIM(station) = %s', (station_code,))

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
                        # บันทึกข้อมูลน้ำ
                        insert_water = '''
                            INSERT INTO water_data (station, parameter, unit, check_number, value, numeric_value)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        '''
                        pg_execute(insert_water, (station, param, unit, f'ครั้งที่ {i}', value, numeric_value))

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
                        # บันทึกข้อมูลดิน
                        insert_soil = '''
                            INSERT INTO soil_data (station, parameter, check_number, value, numeric_value)
                            VALUES (%s, %s, %s, %s, %s)
                        '''
                        pg_execute(insert_soil, (station, param, f'ครั้งที่ {i}', value, numeric_value))

            return jsonify({'success': True})

        except Exception as e:
            print("Error updating station:", str(e))
            return jsonify({'success': False, 'message': str(e)})

        # GET: ดึงข้อมูลเดิมมา pre-fill
    try:
        # ดึงข้อมูลสถานี
        station_query = '''
            SELECT river, station, location, tambon, amphoe, province
            FROM station_data WHERE TRIM(station) = %s
        '''
        station_rows = pg_execute(station_query, (station_code.strip(),), fetch=True)
        if not station_rows:
            return "ไม่พบสถานี", 404
        station_data = dict(station_rows[0])

        # ดึงข้อมูลน้ำ
        water_query = '''
            SELECT parameter, unit, check_number, value
            FROM water_data WHERE TRIM(station) = %s
        '''
        water_rows = pg_execute(water_query, (station_code.strip(),), fetch=True)

        # ดึงข้อมูลดิน
        soil_query = '''
            SELECT parameter, check_number, value
            FROM soil_data WHERE TRIM(station) = %s
        '''
        soil_rows = pg_execute(soil_query, (station_code.strip(),), fetch=True)

        # จัดเรียงข้อมูลน้ำ
        water_data = {}
        for row in water_rows:
            param = row['parameter']
            if param not in water_data:
                water_data[param] = {'unit': row['unit'], 'checks': {}}
            try:
                check_num = int(row['check_number'].replace('ครั้งที่', '').strip())
                water_data[param]['checks'][check_num] = row['value']
            except:
                water_data[param]['checks'][row['check_number']] = row['value']

        # จัดเรียงข้อมูลดิน
        soil_data = {}
        for row in soil_rows:
            param = row['parameter']
            if param not in soil_data:
                soil_data[param] = {'checks': {}}
            try:
                check_num = int(row['check_number'].replace('ครั้งที่', '').strip())
                soil_data[param]['checks'][check_num] = row['value']
            except:
                soil_data[param]['checks'][row['check_number']] = row['value']

        # คำนวณจำนวนครั้งสูงสุด
        water_check_count = max((max(d['checks'].keys()) for d in water_data.values()), default=14) if water_data else 14
        soil_check_count = max((max(d['checks'].keys()) for d in soil_data.values()), default=8) if soil_data else 8

        return render_template('edit_station.html',
                             station=station_data,
                             water_data=water_data,
                             soil_data=soil_data,
                             water_check_count=water_check_count,
                             soil_check_count=soil_check_count)

    except Exception as e:
        return f"Error loading edit form: {str(e)}", 500
    
@app.route('/migrate')
def migrate():
    # รันสคริปต์ migrate ที่นี่
    return "Migrated!"

@app.route('/debug/station/<station_code>')
def debug_station(station_code):
    """Endpoint สำหรับทดสอบการดึงข้อมูลสถานี"""
    station = get_station_by_code(station_code)
    water = get_water_data(station_code)
    soil = get_soil_data(station_code)

    return {
        'station': station,
        'water_count': len(water['pivot_list_filtered']),
        'soil_count': len(soil['pivot_list_filtered']),
        'station_code': station_code
    }

@app.route('/debug-env')
def debug_env():
    has_db_url = 'DATABASE_URL' in os.environ
    has_pg_host = 'PG_HOST' in os.environ
    
    return {
        'has_DATABASE_URL': has_db_url,
        'has_PG_HOST': has_pg_host,
        'DATABASE_URL_sample': os.environ.get('DATABASE_URL', '')[:50] + '...' if has_db_url else None
    }

@app.route('/debug/db')
def debug_db():
    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute("SELECT version(), current_database()")
        db_info = cur.fetchone()
        conn.close()
        
        return {
            "status": "✅ เชื่อมต่อสำเร็จ",
            "database": db_info[1],
            "version": db_info[0].split()[0]
        }
    except Exception as e:
        return {"error": str(e)}
    
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

    app.run(debug=False, host='0.0.0.0', port=port, threaded=True)
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