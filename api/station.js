// api/stations.js
import sqlite3 from 'sqlite3';
import { open } from 'sqlite';

// ฟังก์ชันเชื่อมต่อ Database
async function getDb() {
    return open({
        filename: './my_database.sqlite',
        driver: sqlite3.Database
    });
}

// ฟังก์ชันเริ่มต้นสร้างตาราง (ถ้ายังไม่มี)
async function initDb() {
    const db = await getDb();
    await db.exec(`
        CREATE TABLE IF NOT EXISTS stations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station TEXT, river TEXT, tambon TEXT, amphoe TEXT, province TEXT, location TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    `);
    await db.exec(`
        CREATE TABLE IF NOT EXISTS water_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_id INTEGER,
            parameter TEXT, unit TEXT,
            check1 TEXT, check2 TEXT, check3 TEXT, check4 TEXT, check5 TEXT, 
            check6 TEXT, check7 TEXT, check8 TEXT, check9 TEXT, check10 TEXT, 
            check11 TEXT, check12 TEXT, check13 TEXT, check14 TEXT,
            FOREIGN KEY(station_id) REFERENCES stations(id) ON DELETE CASCADE
        )
    `);
    await db.exec(`
        CREATE TABLE IF NOT EXISTS soil_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_id INTEGER,
            parameter TEXT,
            check1 TEXT, check2 TEXT, check3 TEXT, check4 TEXT, check5 TEXT, 
            check6 TEXT, check7 TEXT, check8 TEXT,
            FOREIGN KEY(station_id) REFERENCES stations(id) ON DELETE CASCADE
        )
    `);
    return db;
}

export default async function handler(req, res) {
    const db = await initDb();

    if (req.method === 'GET') {
        // อ่านข้อมูลทั้งหมด หรือ เฉพาะ ID
        const { id } = req.query;
        if (id) {
            const station = await db.get('SELECT * FROM stations WHERE id = ?', id);
            const water = await db.all('SELECT * FROM water_data WHERE station_id = ?', id);
            const soil = await db.all('SELECT * FROM soil_data WHERE station_id = ?', id);
            res.status(200).json({ success: true, data: { station, water, soil } });
        } else {
            const stations = await db.all('SELECT * FROM stations ORDER BY id DESC');
            res.status(200).json({ success: true, data: stations });
        }
    } 
    else if (req.method === 'POST') {
        // เพิ่มข้อมูลใหม่
        const { station, river, tambon, amphoe, province, location, waterData, soilData } = req.body;
        
        const result = await db.run(
            'INSERT INTO stations (station, river, tambon, amphoe, province, location) VALUES (?, ?, ?, ?, ?, ?)',
            [station, river, tambon, amphoe, province, location]
        );
        const stationId = result.lastID;

        // บันทึกรายการน้ำ
        if (waterData && waterData.length > 0) {
            for (let item of waterData) {
                await db.run(`INSERT INTO water_data (station_id, parameter, unit, check1, check2, check3, check4, check5, check6, check7, check8, check9, check10, check11, check12, check13, check14) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
                [stationId, item.parameter, item.unit, item.check1, item.check2, item.check3, item.check4, item.check5, item.check6, item.check7, item.check8, item.check9, item.check10, item.check11, item.check12, item.check13, item.check14]);
            }
        }

        // บันทึกรายการดิน
        if (soilData && soilData.length > 0) {
            for (let item of soilData) {
                await db.run(`INSERT INTO soil_data (station_id, parameter, check1, check2, check3, check4, check5, check6, check7, check8) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
                [stationId, item.parameter, item.check1, item.check2, item.check3, item.check4, item.check5, item.check6, item.check7, item.check8]);
            }
        }

        res.status(201).json({ success: true, message: 'บันทึกข้อมูลเรียบร้อย' });
    }
    else if (req.method === 'PUT') {
        // แก้ไขข้อมูล
        const { id, station, river, tambon, amphoe, province, location, waterData, soilData } = req.body;

        await db.run('UPDATE stations SET station=?, river=?, tambon=?, amphoe=?, province=?, location=? WHERE id=?',
            [station, river, tambon, amphoe, province, location, id]);

        // ลบข้อมูลเก่าแล้วใส่ใหม่ (วิธีง่ายสุดสำหรับการแก้ไขตาราง)
        await db.run('DELETE FROM water_data WHERE station_id = ?', id);
        await db.run('DELETE FROM soil_data WHERE station_id = ?', id);

        // บันทึกรายการน้ำใหม่
        if (waterData && waterData.length > 0) {
            for (let item of waterData) {
                await db.run(`INSERT INTO water_data (station_id, parameter, unit, check1, check2, check3, check4, check5, check6, check7, check8, check9, check10, check11, check12, check13, check14) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
                [id, item.parameter, item.unit, item.check1, item.check2, item.check3, item.check4, item.check5, item.check6, item.check7, item.check8, item.check9, item.check10, item.check11, item.check12, item.check13, item.check14]);
            }
        }
         // บันทึกรายการดินใหม่
         if (soilData && soilData.length > 0) {
            for (let item of soilData) {
                await db.run(`INSERT INTO soil_data (station_id, parameter, check1, check2, check3, check4, check5, check6, check7, check8) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
                [id, item.parameter, item.check1, item.check2, item.check3, item.check4, item.check5, item.check6, item.check7, item.check8]);
            }
        }

        res.status(200).json({ success: true, message: 'แก้ไขข้อมูลเรียบร้อย' });
    }
    else if (req.method === 'DELETE') {
        // ลบข้อมูล
        const { id } = req.query;
        await db.run('DELETE FROM stations WHERE id = ?', id);
        res.status(200).json({ success: true, message: 'ลบข้อมูลเรียบร้อย' });
    }
}