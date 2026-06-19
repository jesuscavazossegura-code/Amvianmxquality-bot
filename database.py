import sqlite3
from datetime import datetime

DB_NAME = "quality.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS defectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            parte TEXT,
            descripcion TEXT,
            cantidad INTEGER,
            turno TEXT,
            reportado_por TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS acciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            defecto_id INTEGER,
            accion TEXT,
            responsable TEXT,
            fecha_limite TEXT,
            estatus TEXT DEFAULT "Abierta"
        )
    ''')
    conn.commit()
    conn.close()

def registrar_defecto(parte, descripcion, cantidad, turno, reportado_por):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO defectos (fecha, parte, descripcion, cantidad, turno, reportado_por)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (datetime.now().strftime("%Y-%m-%d %H:%M"), parte, descripcion, cantidad, turno, reportado_por))
    defecto_id = c.lastrowid
    conn.commit()
    conn.close()
    return defecto_id

def obtener_defectos():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT * FROM defectos ORDER BY fecha DESC LIMIT 20')
    rows = c.fetchall()
    conn.close()
    return rows

def registrar_accion(defecto_id, accion, responsable, fecha_limite):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO acciones (fecha, defecto_id, accion, responsable, fecha_limite)
        VALUES (?, ?, ?, ?, ?)
    ''', (datetime.now().strftime("%Y-%m-%d %H:%M"), defecto_id, accion, responsable, fecha_limite))
    conn.commit()
    conn.close()