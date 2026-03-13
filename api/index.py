#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API endpoints for Kok Data Application
"""
# api/index.py ทำหน้าที่เป็น API Layer แยกออกมาจากไฟล์หลัก app.py โดยใช้หลักการ Flask Blueprint เพื่อจัดกลุ่มเส้นทาง (Routes) ที่เป็น API โดยเฉพาะ 

#Blueprint: ใช้สร้างกลุ่มของ Route แยกออกมา ในที่นี้ชื่อว่า 'api'
# jsonify: ฟังก์ชันสำหรับแปลงข้อมูล Python (Dict/List) ให้เป็นรูปแบบ JSON เพื่อส่งกลับให้ Frontend
# request: ใช้สำหรับรับข้อมูลจากผู้ใช้ (เช่น JSON Body, Query Parameters)
#RealDictCursor: ทำให้ผลลัพธ์จากฐานข้อมูลเข้าถึงคอลัมน์ด้วยชื่อได้ (เช่น row['station']) แทนการใช้ดัชนี (เช่น row[0])
from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor
import re

# สร้าง Blueprint สำหรับ API
# url_prefix='/api' กำหนดว่าทุก Route ในไฟล์นี้จะต้องขึ้นต้นด้วย /api โดยอัตโนมัติ (เช่น /stations จะกลายเป็น /api/stations)
api_bp = Blueprint('api', __name__, url_prefix='/api')

# ฟังก์ชันช่วยแปลงค่าตัวเลข 
def safe_float(value):
    """แปลง string เป็น float อย่างปลอดภัย"""
    if value is None:
        return None
    val_str = str(value).strip()
    val_str = val_str.replace(',', '').replace(' ', '') # ตัดช่องว่างและเครื่องหมายลูกน้ำออก
    if not val_str or val_str[0] in '<>' or not val_str.replace('.', '', 1).isdigit(): # ตรวจสอบกรณีพิเศษ เช่น ค่าที่ขึ้นต้นด้วย < หรือ > (เช่น <5.0) ซึ่งมักพบในข้อมูลคุณภาพน้ำ
        return None #ถ้าแปลงไม่ได้จะคืนค่า None แทนที่จะทำให้โปรแกรม Error

    try:
        return float(val_str)
    except (ValueError, TypeError):
        return None


# === GET /api/stations - ดึงรายการสถานีทั้งหมด ===
@api_bp.route('/stations', methods=['GET'])
def get_stations():
    try:
        from app import get_db  # import ฟังก์ชันจาก app.py เพื่อเชื่อมต่อ Database
        conn = get_db()
        cur = conn.cursor()
        
        # ดึงข้อมูลจากตาราง station_data เรียงลำดับตามชื่อแม่น้ำและชื่อสถานี
        cur.execute("""
            SELECT id, station, river, tambon, amphoe, province, location
            FROM station_data
            ORDER BY river, station
        """)
        stations = cur.fetchall()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': [dict(s) for s in stations]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# === POST /api/stations - เพิ่มสถานีใหม่ (รองรับ JSON จาก Frontend) ===
@api_bp.route('/stations', methods=['POST'])
def add_station_api():
    try:
        from app import get_db
        data = request.get_json() # รับข้อมูล: request.get_json() ดึงข้อมูล JSON ที่ส่งมา
        
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data received'}), 400
        
        # === 1. ดึงข้อมูลพื้นฐาน ===
        station = data.get('station', '').strip()
        river = data.get('river', '').strip()
        tambon = data.get('tambon', '').strip()
        amphoe = data.get('amphoe', '').strip()
        province = data.get('province', '').strip()
        location = data.get('location', '').strip()
        
        if not station:
            return jsonify({'success': False, 'error': 'station is required'}), 400
        
        conn = get_db()
        cur = conn.cursor()
        
        # === 2. บันทึกสถานี ===
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
        
        # === 3. บันทึกข้อมูลน้ำ ===
        water_count = 0
        water_data = data.get('waterData', [])
        
        for item in water_data:
            param = item.get('parameter', '').strip()
            unit = item.get('unit', '').strip()
            if not param:
                continue
                
            for i in range(1, 15):  # 14 ครั้ง
                check_key = f'check{i}'
                value = item.get(check_key, '').strip() if item.get(check_key) else ''
                if not value:
                    continue
                    
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
        
        # === 4. บันทึกข้อมูลดิน ===
        soil_count = 0
        soil_data = data.get('soilData', [])
        
        for item in soil_data:
            param = item.get('parameter', '').strip()
            if not param:
                continue
                
            for i in range(1, 9):  # 8 ครั้ง
                check_key = f'check{i}'
                value = item.get(check_key, '').strip() if item.get(check_key) else ''
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
            'message': 'Station, water data, and soil data saved successfully',
            'station': station,
            'water_count': water_count,
            'soil_count': soil_count
        }), 201
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# === GET /api/stations/<station_code> - ดึงข้อมูลสถานีเดียว ===
@api_bp.route('/stations/<station_code>', methods=['GET'])
def get_station_detail(station_code): 
    try:
        from app import get_db
        conn = get_db()
        cur = conn.cursor()
        
        # ดึงข้อมูลสถานี
        cur.execute("""
            SELECT id, station, river, tambon, amphoe, province, location
            FROM station_data
            WHERE station = %s
        """, (station_code.strip(),))
        station = cur.fetchone()
        
        if not station:
            conn.close()
            return jsonify({'success': False, 'error': 'Station not found'}), 404
        
        # ดึงข้อมูลน้ำ
        cur.execute(r"""
            SELECT parameter, unit, location, check_number, value, numeric_value
            FROM water_data
            WHERE station = %s
            ORDER BY 
                NULLIF(REGEXP_REPLACE(check_number, '\D', '', 'g'), '')::INTEGER NULLS LAST,
                check_number,
                parameter
        """, (station_code.strip(),))
        water_rows = cur.fetchall()
        
        # ดึงข้อมูลดิน
        cur.execute(r"""
            SELECT parameter, location, check_number, value, numeric_value
            FROM soil_data
            WHERE station = %s
            ORDER BY 
                NULLIF(REGEXP_REPLACE(check_number, '\D', '', 'g'), '')::INTEGER NULLS LAST,
                check_number,
                parameter
        """, (station_code.strip(),))
        soil_rows = cur.fetchall()
        
        conn.close()
        
        # จัดรูปแบบข้อมูลน้ำเป็น pivot
        water_data = {}
        for row in water_rows:
            param = row['parameter']
            if param not in water_data:
                water_data[param] = {'unit': row['unit'], 'checks': {}}
            check_num = row['check_number']
            water_data[param]['checks'][check_num] = {
                'value': row['value'],
                'numeric_value': row['numeric_value']
            }
        
        # จัดรูปแบบข้อมูลดินเป็น pivot
        soil_data = {}
        for row in soil_rows:
            param = row['parameter']
            if param not in soil_data:
                soil_data[param] = {'checks': {}}
            check_num = row['check_number']
            soil_data[param]['checks'][check_num] = {
                'value': row['value'],
                'numeric_value': row['numeric_value']
            }
        
        # ส่งข้อมูลไปแสดงผลที่ frontend หน้า station detail
        return jsonify({
            'success': True,
            'data': {
                'station': dict(station),
                'water_data': water_data,
                'soil_data': soil_data
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# === PUT /api/stations/<station_code> - อัปเดตสถานี ===
@api_bp.route('/stations/<station_code>', methods=['PUT'])
def update_station_api(station_code): # แก้ไขข้อมูลพื้นฐานของสถานี (ชื่อ, ที่อยู่, พิกัด)
    try:
        from app import get_db
        data = request.get_json() or request.form.to_dict()
        
        station = data.get('station', '').strip()
        river = data.get('river', '').strip()
        tambon = data.get('tambon', '').strip()
        amphoe = data.get('amphoe', '').strip()
        province = data.get('province', '').strip()
        location = data.get('location', '').strip()
        
        conn = get_db()
        cur = conn.cursor()
        
        # อัปเดตข้อมูลสถานี
        cur.execute("""
            UPDATE station_data
            SET station = %s, river = %s, tambon = %s, amphoe = %s, 
                province = %s, location = %s
            WHERE station = %s
            RETURNING id
        """, (station, river, tambon, amphoe, province, location, station_code))
        
        result = cur.fetchone()
        if not result:
            conn.close()
            return jsonify({'success': False, 'error': 'Station not found'}), 404
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Station updated successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# === DELETE /api/stations/<station_code> - ลบสถานี ===
@api_bp.route('/stations/<station_code>', methods=['DELETE'])
def delete_station_api(station_code):# ลบสถานีออกจากระบบ
    try:
        from app import get_db
        conn = get_db()
        cur = conn.cursor()
        
        # ON DELETE CASCADE จะลบ water_data และ soil_data อัตโนมัติ
        cur.execute("""
            DELETE FROM station_data
            WHERE station = %s
        """, (station_code.strip(),))
        
        # ถ้าไม่พบสถานี  จะส่ง Error 404 กลับ
        if cur.rowcount == 0:
            conn.close()
            return jsonify({'success': False, 'error': 'Station not found'}), 404
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Station deleted successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# === GET /api/stations/<station_code>/water - ดึงเฉพาะข้อมูลน้ำ ===
@api_bp.route('/stations/<station_code>/water', methods=['GET'])
def get_water_data_api(station_code):
    try:
        from app import get_db
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute(r"""
            SELECT parameter, unit, location, check_number, value, numeric_value
            FROM water_data
            WHERE station = %s
            ORDER BY 
                NULLIF(REGEXP_REPLACE(check_number, '\D', '', 'g'), '')::INTEGER NULLS LAST,
                check_number,
                parameter
        """, (station_code.strip(),))
        
        rows = cur.fetchall()
        conn.close()
        
        # จัดรูปแบบเป็น pivot
        pivot = {}
        for row in rows:
            param = row['parameter']
            if param not in pivot:
                pivot[param] = {
                    'unit': row['unit'],
                    'location': row['location'],
                    'values': {}
                }
            pivot[param]['values'][row['check_number']] = {
                'value': row['value'],
                'numeric_value': row['numeric_value']
            }
        
        return jsonify({
            'success': True,
            'data': pivot
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# === GET /api/stations/<station_code>/soil - ดึงเฉพาะข้อมูลดิน ===
@api_bp.route('/stations/<station_code>/soil', methods=['GET'])
def get_soil_data_api(station_code):
    try:
        from app import get_db
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute(r"""
            SELECT parameter, location, check_number, value, numeric_value
            FROM soil_data
            WHERE station = %s
            ORDER BY 
                NULLIF(REGEXP_REPLACE(check_number, '\D', '', 'g'), '')::INTEGER NULLS LAST,
                check_number,
                parameter
        """, (station_code.strip(),))
        
        rows = cur.fetchall()
        conn.close()
        
        # จัดรูปแบบเป็น pivot
        pivot = {}
        for row in rows:
            param = row['parameter']
            if param not in pivot:
                pivot[param] = {
                    'location': row['location'],
                    'values': {}
                }
            pivot[param]['values'][row['check_number']] = {
                'value': row['value'],
                'numeric_value': row['numeric_value']
            }
        
        return jsonify({
            'success': True,
            'data': pivot
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500