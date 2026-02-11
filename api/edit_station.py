from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = Flask(__name__)

def get_db():
    return psycopg2.connect(
        host=os.environ['PG_HOST'],
        port=os.environ['PG_PORT'],
        database=os.environ['PG_DATABASE'],
        user=os.environ['PG_USER'],
        password=os.environ['PG_PASSWORD']
    )

@app.route('/api/edit-station/<station_code>', methods=['POST'])
def edit_station(station_code):
    try:
        data = request.get_json()
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # อัปเดตข้อมูล
        cur.execute('''
            UPDATE station_data 
            SET river = %s, location = %s, tambon = %s, amphoe = %s, province = %s
            WHERE station = %s
        ''', (
            data['river'], data['location'], data['tambon'],
            data['amphoe'], data['province'], station_code
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500