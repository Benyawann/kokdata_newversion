import sqlite3 from 'sqlite3';
import { open } from 'sqlite';

async function getDb() {
    return open({ filename: './my_database.sqlite', driver: sqlite3.Database });
}

export default async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'DELETE');
    
    const { code } = req.query;
    
    if (req.method === 'DELETE') {
        try {
            const db = await getDb();
            // ลบข้อมูลในตารางลูกก่อน
            await db.run('DELETE FROM water_data WHERE station_id = (SELECT id FROM stations WHERE station = ?)', [code]);
            await db.run('DELETE FROM soil_data WHERE station_id = (SELECT id FROM stations WHERE station = ?)', [code]);
            // ลบสถานีหลัก
            await db.run('DELETE FROM stations WHERE station = ?', [code]);
            
            res.status(200).json({ success: true, message: 'ลบสถานีเรียบร้อยแล้ว' });
        } catch (error) {
            res.status(500).json({ success: false, message: error.message });
        }
    } else {
        res.status(405).json({ message: 'Method not allowed' });
    }
}