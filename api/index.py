from http.server import BaseHTTPRequestHandler
import sqlite3
import json
import os
from urllib.parse import urlparse, parse_qs
from jinja2 import Environment, FileSystemLoader

# ตั้งค่า Jinja2
template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')
env = Environment(loader=FileSystemLoader(template_dir))

# เชื่อมต่อฐานข้อมูล
def get_db():
    db_path = os.path.join(os.path.dirname(__file__), '..', 'my_database.sqlite')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# สร้างตารางถ้ายังไม่มี
def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS stations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        station TEXT, river TEXT, tambon TEXT, amphoe TEXT, 
        province TEXT, location TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS water_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        station_id INTEGER, parameter TEXT, unit TEXT,
        check1 TEXT, check2 TEXT, check3 TEXT, check4 TEXT, check5 TEXT,
        check6 TEXT, check7 TEXT, check8 TEXT, check9 TEXT, check10 TEXT,
        check11 TEXT, check12 TEXT, check13 TEXT, check14 TEXT,
        check15 TEXT, check16 TEXT, check17 TEXT, check18 TEXT,
        check19 TEXT, check20 TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS soil_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        station_id INTEGER, parameter TEXT,
        check1 TEXT, check2 TEXT, check3 TEXT, check4 TEXT, check5 TEXT,
        check6 TEXT, check7 TEXT, check8 TEXT, check9 TEXT, check10 TEXT
    )''')
    
    conn.commit()
    conn.close()

# Helper: แปลงข้อมูลน้ำ/ดิน สำหรับ Template
def prepare_water_data(water_rows):
    if not water_rows:
        return None
    
    check_numbers = []
    for i in range(1, 21):
        if any(row[f'check{i}'] for row in water_rows):
            check_numbers.append(i)
    
    pivot_list = []
    for row in water_rows:
        check_values = {str(i): row[f'check{i}'] for i in check_numbers}
        numeric_values = {}
        for i in check_numbers:
            val = row[f'check{i}']
            if val and val not in ['-', 'ND', '']:
                try:
                    numeric_values[str(i)] = float(val)
                except:
                    numeric_values[str(i)] = 0
            else:
                numeric_values[str(i)] = 0
        
        pivot_list.append({
            'parameter': row['parameter'],
            'unit': row['unit'],
            'check_values': check_values,
            'numeric_values': numeric_values
        })
    
    return {
        'pivot': True,
        'check_numbers': check_numbers,
        'pivot_list': pivot_list,
        'pivot_list_filtered': pivot_list  # สำหรับกราฟ
    }

def prepare_soil_data(soil_rows):
    if not soil_rows:
        return None
    
    check_numbers = []
    for i in range(1, 11):
        if any(row[f'check{i}'] for row in soil_rows):
            check_numbers.append(i)
    
    pivot_list = []
    for row in soil_rows:
        check_values = {str(i): row[f'check{i}'] for i in check_numbers}
        numeric_values = {}
        for i in check_numbers:
            val = row[f'check{i}']
            if val and val not in ['-', 'ND', '']:
                try:
                    numeric_values[str(i)] = float(val)
                except:
                    numeric_values[str(i)] = 0
            else:
                numeric_values[str(i)] = 0
        
        pivot_list.append({
            'parameter': row['parameter'],
            'check_values': check_values,
            'numeric_values': numeric_values
        })
    
    return {
        'pivot': True,
        'check_numbers': check_numbers,
        'pivot_list': pivot_list,
        'pivot_list_filtered': pivot_list  # สำหรับกราฟ
    }

# Handler หลัก
def handler(req):
    init_db()
    
    parsed = urlparse(req.path)
    path = parsed.path
    query = parse_qs(parsed.query)
    
    # Route: หน้าแรก
    if path == '/' or path == '/index.html':
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM stations ORDER BY id DESC')
        stations = [dict(row) for row in c.fetchall()]
        conn.close()
        
        template = env.get_template('index.html')
        html = template.render(stations=stations, session={'logged_in': True})
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'text/html'},
            'body': html
        }
    
    # Route: รายละเอียดสถานี
    elif path.startswith('/station/'):
        station_code = path.replace('/station/', '')
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM stations WHERE station = ?', (station_code,))
        station = c.fetchone()
        
        if not station:
            return {'statusCode': 404, 'headers': {'Content-Type': 'text/html'}, 'body': 'ไม่พบสถานี'}
        
        station = dict(station)
        station_id = station['id']
        
        c.execute('SELECT * FROM water_data WHERE station_id = ?', (station_id,))
        water_rows = [dict(row) for row in c.fetchall()]
        
        c.execute('SELECT * FROM soil_data WHERE station_id = ?', (station_id,))
        soil_rows = [dict(row) for row in c.fetchall()]
        
        conn.close()
        
        water_data = prepare_water_data(water_rows)
        soil_data = prepare_soil_data(soil_rows)
        
        template = env.get_template('station-detail.html')
        html = template.render(
            station=station, 
            water_data=water_data, 
            soil_data=soil_data,
            session={'logged_in': True}
        )
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'text/html'},
            'body': html
        }
    
    # Route: เพิ่มสถานี (GET = แสดงฟอร์ม, POST = บันทึก)
    elif path == '/add-station' or path == '/add-station.html':
        if req.method == 'GET':
            template = env.get_template('add-station.html')
            html = template.render(session={'logged_in': True})
            return {'statusCode': 200, 'headers': {'Content-Type': 'text/html'}, 'body': html}
        
        elif req.method == 'POST':
            content_length = int(req.headers.get('Content-Length', 0))
            body = req.body.read(content_length).decode('utf-8')
            data = json.loads(body) if body else {}
            
            conn = get_db()
            c = conn.cursor()
            c.execute('''INSERT INTO stations (station, river, tambon, amphoe, province, location)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (data.get('station'), data.get('river'), data.get('tambon'),
                      data.get('amphoe'), data.get('province'), data.get('location')))
            station_id = c.lastrowid
            
            # บันทึกข้อมูลน้ำ
            for item in data.get('waterData', []):
                c.execute('''INSERT INTO water_data 
                            (station_id, parameter, unit, check1, check2, check3, check4, check5,
                            check6, check7, check8, check9, check10, check11, check12, check13, check14,
                            check15, check16, check17, check18, check19, check20)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (station_id, item['parameter'], item.get('unit', ''),
                          item.get('check1', ''), item.get('check2', ''), item.get('check3', ''),
                          item.get('check4', ''), item.get('check5', ''), item.get('check6', ''),
                          item.get('check7', ''), item.get('check8', ''), item.get('check9', ''),
                          item.get('check10', ''), item.get('check11', ''), item.get('check12', ''),
                          item.get('check13', ''), item.get('check14', ''), item.get('check15', ''),
                          item.get('check16', ''), item.get('check17', ''), item.get('check18', ''),
                          item.get('check19', ''), item.get('check20', '')))
            
            # บันทึกข้อมูลดิน
            for item in data.get('soilData', []):
                c.execute('''INSERT INTO soil_data 
                            (station_id, parameter, check1, check2, check3, check4, check5,
                            check6, check7, check8, check9, check10)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (station_id, item['parameter'],
                          item.get('check1', ''), item.get('check2', ''), item.get('check3', ''),
                          item.get('check4', ''), item.get('check5', ''), item.get('check6', ''),
                          item.get('check7', ''), item.get('check8', ''), item.get('check9', ''),
                          item.get('check10', '')))
            
            conn.commit()
            conn.close()
            
            return {
                'statusCode': 302,
                'headers': {'Location': '/'},
                'body': ''
            }
    
    # Route: แก้ไขสถานี
    elif path == '/edit-station' or path == '/edit-station.html':
        station_id = query.get('id', [None])[0]
        
        if req.method == 'GET' and station_id:
            conn = get_db()
            c = conn.cursor()
            c.execute('SELECT * FROM stations WHERE id = ?', (station_id,))
            station = c.fetchone()
            
            if not station:
                return {'statusCode': 404, 'headers': {'Content-Type': 'text/html'}, 'body': 'ไม่พบสถานี'}
            
            station = dict(station)
            c.execute('SELECT * FROM water_data WHERE station_id = ?', (station_id,))
            water_rows = [dict(row) for row in c.fetchall()]
            c.execute('SELECT * FROM soil_data WHERE station_id = ?', (station_id,))
            soil_rows = [dict(row) for row in c.fetchall()]
            conn.close()
            
            water_data = prepare_water_data(water_rows)
            soil_data = prepare_soil_data(soil_rows)
            
            template = env.get_template('edit-station.html')
            html = template.render(
                station=station, 
                water_data=water_data, 
                soil_data=soil_data,
                session={'logged_in': True}
            )
            return {'statusCode': 200, 'headers': {'Content-Type': 'text/html'}, 'body': html}
        
        elif req.method == 'PUT' and station_id:
            content_length = int(req.headers.get('Content-Length', 0))
            body = req.body.read(content_length).decode('utf-8')
            data = json.loads(body) if body else {}
            
            conn = get_db()
            c = conn.cursor()
            c.execute('''UPDATE stations SET station=?, river=?, tambon=?, amphoe=?, province=?, location=?
                        WHERE id=?''',
                     (data['station'], data['river'], data['tambon'], 
                      data['amphoe'], data['province'], data['location'], station_id))
            
            c.execute('DELETE FROM water_data WHERE station_id = ?', (station_id,))
            c.execute('DELETE FROM soil_data WHERE station_id = ?', (station_id,))
            
            for item in data.get('waterData', []):
                c.execute('''INSERT INTO water_data 
                            (station_id, parameter, unit, check1, check2, check3, check4, check5,
                            check6, check7, check8, check9, check10, check11, check12, check13, check14,
                            check15, check16, check17, check18, check19, check20)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (station_id, item['parameter'], item.get('unit', ''),
                          item.get('check1', ''), item.get('check2', ''), item.get('check3', ''),
                          item.get('check4', ''), item.get('check5', ''), item.get('check6', ''),
                          item.get('check7', ''), item.get('check8', ''), item.get('check9', ''),
                          item.get('check10', ''), item.get('check11', ''), item.get('check12', ''),
                          item.get('check13', ''), item.get('check14', ''), item.get('check15', ''),
                          item.get('check16', ''), item.get('check17', ''), item.get('check18', ''),
                          item.get('check19', ''), item.get('check20', '')))
            
            for item in data.get('soilData', []):
                c.execute('''INSERT INTO soil_data 
                            (station_id, parameter, check1, check2, check3, check4, check5,
                            check6, check7, check8, check9, check10)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (station_id, item['parameter'],
                          item.get('check1', ''), item.get('check2', ''), item.get('check3', ''),
                          item.get('check4', ''), item.get('check5', ''), item.get('check6', ''),
                          item.get('check7', ''), item.get('check8', ''), item.get('check9', ''),
                          item.get('check10', '')))
            
            conn.commit()
            conn.close()
            
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'success': True})
            }
    
    # Route: ลบสถานี
    elif path.startswith('/delete-station/'):
        station_code = path.replace('/delete-station/', '')
        
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id FROM stations WHERE station = ?', (station_code,))
        station = c.fetchone()
        
        if station:
            station_id = station['id']
            c.execute('DELETE FROM water_data WHERE station_id = ?', (station_id,))
            c.execute('DELETE FROM soil_data WHERE station_id = ?', (station_id,))
            c.execute('DELETE FROM stations WHERE id = ?', (station_id,))
            conn.commit()
        
        conn.close()
        
        return {
            'statusCode': 302,
            'headers': {'Location': '/'},
            'body': ''
        }
    
    # API Endpoint (สำหรับ JavaScript)
    elif path.startswith('/api/'):
        return handle_api(req, path, query)
    
    # Static Files
    elif path.startswith('/static/'):
        return {'statusCode': 404, 'headers': {'Content-Type': 'text/html'}, 'body': 'Not Found'}
    
    else:
        return {'statusCode': 404, 'headers': {'Content-Type': 'text/html'}, 'body': 'Not Found'}

def handle_api(req, path, query):
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE',
        'Content-Type': 'application/json'
    }
    
    if req.method == 'OPTIONS':
        return {'statusCode': 200, 'headers': headers, 'body': ''}
    
    conn = get_db()
    c = conn.cursor()
    
    if path == '/api/stations':
        station_id = query.get('id', [None])[0]
        
        if req.method == 'GET':
            if station_id:
                c.execute('SELECT * FROM stations WHERE id = ?', (station_id,))
                station = c.fetchone()
                if not station:
                    return {'statusCode': 404, 'headers': headers, 'body': json.dumps({'success': False})}
                
                station = dict(station)
                c.execute('SELECT * FROM water_data WHERE station_id = ?', (station_id,))
                water = [dict(row) for row in c.fetchall()]
                c.execute('SELECT * FROM soil_data WHERE station_id = ?', (station_id,))
                soil = [dict(row) for row in c.fetchall()]
                
                return {'statusCode': 200, 'headers': headers, 'body': json.dumps({
                    'success': True,
                    'data': {'station': station, 'water': water, 'soil': soil}
                })}
            else:
                c.execute('SELECT * FROM stations ORDER BY id DESC')
                stations = [dict(row) for row in c.fetchall()]
                return {'statusCode': 200, 'headers': headers, 'body': json.dumps({
                    'success': True,
                    'data': stations
                })}
        
        elif req.method == 'DELETE' and station_id:
            c.execute('DELETE FROM water_data WHERE station_id = ?', (station_id,))
            c.execute('DELETE FROM soil_data WHERE station_id = ?', (station_id,))
            c.execute('DELETE FROM stations WHERE id = ?', (station_id,))
            conn.commit()
            return {'statusCode': 200, 'headers': headers, 'body': json.dumps({'success': True})}
    
    conn.close()
    return {'statusCode': 405, 'headers': headers, 'body': json.dumps({'message': 'Method not allowed'})}

# Vercel Python Runtime Entry Point
def main(req):
    return handler(req)