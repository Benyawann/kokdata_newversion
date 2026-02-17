import sqlite3 from 'sqlite3';
import { open } from 'sqlite';

async function getDb() {
    return open({ filename: './my_database.sqlite', driver: sqlite3.Database });
}

async function initDb() {
    const db = await getDb();
    await db.exec(`CREATE TABLE IF NOT EXISTS stations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, station TEXT, river TEXT, tambon TEXT, 
        amphoe TEXT, province TEXT, location TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )`);
    await db.exec(`CREATE TABLE IF NOT EXISTS water_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT, station_id INTEGER, parameter TEXT, unit TEXT,
        check1 TEXT, check2 TEXT, check3 TEXT, check4 TEXT, check5 TEXT, check6 TEXT, 
        check7 TEXT, check8 TEXT, check9 TEXT, check10 TEXT, check11 TEXT, check12 TEXT, 
        check13 TEXT, check14 TEXT, check15 TEXT, check16 TEXT, check17 TEXT, check18 TEXT, 
        check19 TEXT, check20 TEXT, FOREIGN KEY(station_id) REFERENCES stations(id) ON DELETE CASCADE
    )`);
    await db.exec(`CREATE TABLE IF NOT EXISTS soil_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT, station_id INTEGER, parameter TEXT,
        check1 TEXT, check2 TEXT, check3 TEXT, check4 TEXT, check5 TEXT, check6 TEXT, 
        check7 TEXT, check8 TEXT, check9 TEXT, check10 TEXT, FOREIGN KEY(station_id) REFERENCES stations(id) ON DELETE CASCADE
    )`);
    return db;
}

export default async function handler(req, res) {
    const db = await initDb();
    const { id } = req.query;

    if (req.method === 'GET') {
        if (!id) {
            const stations = await db.all('SELECT * FROM stations ORDER BY id DESC');
            return res.json({ success: true, data: stations });
        }
        const station = await db.get('SELECT * FROM stations WHERE id = ?', id);
        const water = await db.all('SELECT * FROM water_data WHERE station_id = ?', id);
        const soil = await db.all('SELECT * FROM soil_data WHERE station_id = ?', id);
        res.json({ success: true, data: { station, water, soil } });
    } 
    else if (req.method === 'POST') {
        // เพิ่มข้อมูลใหม่
        const { station, river, tambon, amphoe, province, location, waterData, soilData } = req.body;
        const result = await db.run(
            `INSERT INTO stations (station, river, tambon, amphoe, province, location) VALUES (?, ?, ?, ?, ?, ?)`,
            [station, river, tambon, amphoe, province, location]
        );
        const stationId = result.lastID;
        // (ใส่โค้ดบันทึกน้ำและดินเหมือนเดิม)
        res.json({ success: true, id: stationId });
    }
    else if (req.method === 'PUT') {
        // แก้ไขข้อมูล
        const { station, river, tambon, amphoe, province, location, waterData, soilData } = req.body;
        await db.run('UPDATE stations SET station=?, river=?, tambon=?, amphoe=?, province=?, location=? WHERE id=?',
            [station, river, tambon, amphoe, province, location, id]);
        await db.run('DELETE FROM water_data WHERE station_id = ?', id);
        await db.run('DELETE FROM soil_data WHERE station_id = ?', id);
        // (ใส่โค้ดบันทึกน้ำและดินใหม่เหมือนเดิม)
        res.json({ success: true });
    }
    else if (req.method === 'DELETE') {
        // === ลบข้อมูล ===
        if (!id) {
            return res.status(400).json({ success: false, message: 'ไม่พบรหัสสถานี' });
        }
        try {
            // ลบข้อมูลในตารางลูกก่อน (หรือใช้ ON DELETE CASCADE ถ้าตั้งค่าไว้)
            await db.run('DELETE FROM water_data WHERE station_id = ?', id);
            await db.run('DELETE FROM soil_data WHERE station_id = ?', id);
            // ลบสถานีหลัก
            await db.run('DELETE FROM stations WHERE id = ?', id);
            res.json({ success: true, message: 'ลบข้อมูลเรียบร้อยแล้ว' });
        } catch (error) {
            res.status(500).json({ success: false, message: error.message });
        }
    }
    else {
        res.status(405).json({ message: 'Method not allowed' });
    }
}