import sqlite3
import json
import os
from http.server import BaseHTTPRequestHandler

# ตั้งค่า CORS
def set_cors_headers(response):
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

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

# Handler หลักสำหรับ Vercel
def handler(req):
    headers = {}
    headers = set_cors_headers(headers)
    
    # รองรับ OPTIONS request (CORS preflight)
    if req.method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': headers,
            'body': ''
        }
    
    # ดึง query parameters
    query_string = req.query_string or ''
    params = {}
    if query_string:
        for param in query_string.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                params[key] = value
    
    station_id = params.get('id')
    
    # === GET ===
    if req.method == 'GET':
        try:
            init_db()
            conn = get_db()
            c = conn.cursor()
            
            if not station_id:
                # ดึงรายการทั้งหมด
                c.execute('SELECT * FROM stations ORDER BY id DESC')
                stations = [dict(row) for row in c.fetchall()]
                conn.close()
                return {
                    'statusCode': 200,
                    'headers': {**headers, 'Content-Type': 'application/json'},
                    'body': json.dumps({'success': True, 'data': stations})
                }
            else:
                # ดึงรายละเอียดสถานี
                c.execute('SELECT * FROM stations WHERE id = ?', (station_id,))
                station = c.fetchone()
                if not station:
                    conn.close()
                    return {
                        'statusCode': 404,
                        'headers': {**headers, 'Content-Type': 'application/json'},
                        'body': json.dumps({'success': False, 'message': 'ไม่พบสถานี'})
                    }
                
                station = dict(station)
                
                c.execute('SELECT * FROM water_data WHERE station_id = ?', (station_id,))
                water = [dict(row) for row in c.fetchall()]
                
                c.execute('SELECT * FROM soil_data WHERE station_id = ?', (station_id,))
                soil = [dict(row) for row in c.fetchall()]
                
                conn.close()
                return {
                    'statusCode': 200,
                    'headers': {**headers, 'Content-Type': 'application/json'},
                    'body': json.dumps({'success': True, 'data': {'station': station, 'water': water, 'soil': soil}})
                }
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {**headers, 'Content-Type': 'application/json'},
                'body': json.dumps({'success': False, 'message': str(e)})
            }
    
    # === POST ===
    elif req.method == 'POST':
        try:
            init_db()
            content_length = int(req.headers.get('Content-Length', 0))
            body = req.body.read(content_length).decode('utf-8')
            data = json.loads(body)
            
            conn = get_db()
            c = conn.cursor()
            
            # บันทึกข้อมูลสถานี
            c.execute('''INSERT INTO stations (station, river, tambon, amphoe, province, location)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (data['station'], data['river'], data['tambon'], 
                      data['amphoe'], data['province'], data['location']))
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
                'statusCode': 200,
                'headers': {**headers, 'Content-Type': 'application/json'},
                'body': json.dumps({'success': True, 'message': 'บันทึกข้อมูลเรียบร้อย'})
            }
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {**headers, 'Content-Type': 'application/json'},
                'body': json.dumps({'success': False, 'message': str(e)})
            }
    
    # === PUT ===
    elif req.method == 'PUT':
        try:
            init_db()
            content_length = int(req.headers.get('Content-Length', 0))
            body = req.body.read(content_length).decode('utf-8')
            data = json.loads(body)
            
            conn = get_db()
            c = conn.cursor()
            
            # อัปเดตข้อมูลสถานี
            c.execute('''UPDATE stations SET station=?, river=?, tambon=?, amphoe=?, province=?, location=?
                        WHERE id=?''',
                     (data['station'], data['river'], data['tambon'], 
                      data['amphoe'], data['province'], data['location'], station_id))
            
            # ลบข้อมูลเก่า
            c.execute('DELETE FROM water_data WHERE station_id = ?', (station_id,))
            c.execute('DELETE FROM soil_data WHERE station_id = ?', (station_id,))
            
            # บันทึกข้อมูลใหม่
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
                'headers': {**headers, 'Content-Type': 'application/json'},
                'body': json.dumps({'success': True, 'message': 'อัปเดตข้อมูลเรียบร้อย'})
            }
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {**headers, 'Content-Type': 'application/json'},
                'body': json.dumps({'success': False, 'message': str(e)})
            }
    
    # === DELETE ===
    elif req.method == 'DELETE':
        try:
            init_db()
            if not station_id:
                return {
                    'statusCode': 400,
                    'headers': {**headers, 'Content-Type': 'application/json'},
                    'body': json.dumps({'success': False, 'message': 'ไม่พบรหัสสถานี'})
                }
            
            conn = get_db()
            c = conn.cursor()
            
            c.execute('DELETE FROM water_data WHERE station_id = ?', (station_id,))
            c.execute('DELETE FROM soil_data WHERE station_id = ?', (station_id,))
            c.execute('DELETE FROM stations WHERE id = ?', (station_id,))
            
            conn.commit()
            conn.close()
            
            return {
                'statusCode': 200,
                'headers': {**headers, 'Content-Type': 'application/json'},
                'body': json.dumps({'success': True, 'message': 'ลบข้อมูลเรียบร้อย'})
            }
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {**headers, 'Content-Type': 'application/json'},
                'body': json.dumps({'success': False, 'message': str(e)})
            }
    
    else:
        return {
            'statusCode': 405,
            'headers': {**headers, 'Content-Type': 'application/json'},
            'body': json.dumps({'message': 'Method not allowed'})
        }