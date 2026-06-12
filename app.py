from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from functools import wraps
import sqlite3
import os
import pandas as pd
from io import BytesIO
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string
import secrets
from datetime import datetime, timedelta
import json
import zipfile
import shutil
import time

app = Flask(__name__)
app.secret_key = 'inventautos_secret_key_2024'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

DATABASE = 'inventautos.db'
BACKUP_FOLDER = 'backups'
UPLOAD_FOLDER_FOTOS = 'static/uploads'

os.makedirs(BACKUP_FOLDER, exist_ok=True)
os.makedirs('uploads', exist_ok=True)
os.makedirs(UPLOAD_FOLDER_FOTOS, exist_ok=True)

ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def generar_captcha():
    texto = ''.join(str(random.randint(0, 9)) for _ in range(5))
    session['captcha_texto'] = texto
    return texto

def generar_codigo_acceso(longitud=6):
    return ''.join(str(random.randint(0, 9)) for _ in range(longitud))

def generar_token_sesion():
    return secrets.token_urlsafe(32)

# ============ FUNCIÓN REGISTRAR LOG CORREGIDA ============
def registrar_log(usuario_id, accion, tabla=None, registro_id=None, detalles=None, ip=None):
    try:
        conn = sqlite3.connect(DATABASE, timeout=10)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if ip is None:
            try:
                ip = request.remote_addr
            except:
                ip = 'Sistema'
        cursor.execute('''
            INSERT INTO logs_actividad (usuario_id, accion, tabla, registro_id, detalles, ip)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (usuario_id, accion, tabla, registro_id, detalles, ip))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error al registrar log: {e}")

# ============ FUNCIONES DE BACKUP ============
def crear_backup():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'backup_{timestamp}'
    backup_path = os.path.join(BACKUP_FOLDER, backup_name)
    os.makedirs(backup_path, exist_ok=True)
    shutil.copy2(DATABASE, os.path.join(backup_path, 'inventautos.db'))
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vehiculos")
    vehiculos = [dict(v) for v in cursor.fetchall()]
    with open(os.path.join(backup_path, 'vehiculos.json'), 'w', encoding='utf-8') as f:
        json.dump(vehiculos, f, ensure_ascii=False, indent=2, default=str)
    cursor.execute("SELECT id, usuario_id, rol, fecha_creacion FROM usuarios")
    usuarios = [dict(u) for u in cursor.fetchall()]
    with open(os.path.join(backup_path, 'usuarios.json'), 'w', encoding='utf-8') as f:
        json.dump(usuarios, f, ensure_ascii=False, indent=2, default=str)
    cursor.execute("SELECT * FROM logs_actividad ORDER BY fecha DESC LIMIT 1000")
    logs = [dict(l) for l in cursor.fetchall()]
    with open(os.path.join(backup_path, 'logs.json'), 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2, default=str)
    stats = {'fecha_backup': datetime.now().isoformat(), 'total_vehiculos': len(vehiculos), 'total_usuarios': len(usuarios), 'total_logs': len(logs)}
    with open(os.path.join(backup_path, 'reporte.json'), 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    conn.close()
    zip_path = os.path.join(BACKUP_FOLDER, f'{backup_name}.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(backup_path):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, backup_path))
    shutil.rmtree(backup_path)
    return zip_path, stats

def get_db():
    conn = sqlite3.connect(DATABASE, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id TEXT UNIQUE NOT NULL,
            contrasena TEXT NOT NULL,
            rol TEXT DEFAULT 'NORMAL',
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vehiculos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chassis TEXT UNIQUE NOT NULL,
            estatus TEXT DEFAULT 'DISPONIBLE',
            marca TEXT NOT NULL,
            modelo TEXT NOT NULL,
            tipo TEXT,
            ano INTEGER,
            color TEXT,
            precio REAL DEFAULT 0,
            precio_contado REAL DEFAULT 0,
            precio_financiamiento REAL DEFAULT 0,
            locacion TEXT,
            pais TEXT DEFAULT 'JAPON',
            bl TEXT,
            foto TEXT DEFAULT NULL
        )
    ''')
    try:
        cursor.execute("ALTER TABLE vehiculos ADD COLUMN foto TEXT DEFAULT NULL")
    except:
        pass
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sesiones_activas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            ip TEXT,
            user_agent TEXT,
            fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha_ultima_actividad TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha_cierre TIMESTAMP,
            activo INTEGER DEFAULT 1,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs_actividad (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            accion TEXT NOT NULL,
            tabla TEXT,
            registro_id INTEGER,
            detalles TEXT,
            ip TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    ''')
    cursor.execute("DELETE FROM sesiones_activas WHERE fecha_ultima_actividad < datetime('now', '-1 day')")
    cursor.execute("DELETE FROM logs_actividad WHERE fecha < datetime('now', '-30 days')")
    cursor.execute("SELECT * FROM usuarios WHERE usuario_id = 'admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO usuarios (usuario_id, contrasena, rol) VALUES (?, ?, ?)",
                      ('admin', generate_password_hash('admin123'), 'ADMIN'))
    cursor.execute("SELECT * FROM usuarios WHERE usuario_id = 'usuario1'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO usuarios (usuario_id, contrasena, rol) VALUES (?, ?, ?)",
                      ('usuario1', generate_password_hash('user123'), 'NORMAL'))
    cursor.execute("SELECT * FROM vehiculos LIMIT 1")
    if not cursor.fetchone():
        vehiculos_ejemplo = [
            ('MXPH10-2027887', 'DISPONIBLE', 'TOYOTA', 'YARIS', 'AUTOMOVIL', 2021, 'GRIS', 0, 0, 0, 'JAPON', 'JAPON', 'S00348455', None),
            ('MXPH10-2019696', 'DISPONIBLE', 'TOYOTA', 'YARIS', 'AUTOMOVIL', 2021, 'GRIS', 0, 0, 0, 'JAPON', 'JAPON', 'S00344704', None),
            ('NHP130-4023111', 'DISPONIBLE', 'TOYOTA', 'VITZ', 'AUTOMOVIL', 2021, 'BLANCO', 850000, 785000, 0, '23/03/2026 SADA', 'JAPON', 'S00336965', None),
        ]
        cursor.executemany('''INSERT INTO vehiculos 
            (chassis, estatus, marca, modelo, tipo, ano, color, precio, precio_contado, precio_financiamiento, locacion, pais, bl, foto) 
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', vehiculos_ejemplo)
    conn.commit()
    conn.close()

init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor inicia sesión primero', 'error')
            return redirect(url_for('login'))
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT activo FROM sesiones_activas WHERE token = ? AND usuario_id = ? AND activo = 1',
                          (session.get('token_sesion', ''), session['user_id']))
            sesion_valida = cursor.fetchone()
            conn.close()
            if not sesion_valida:
                session.clear()
                flash('Tu sesión ha sido cerrada desde otro dispositivo', 'error')
                return redirect(url_for('login'))
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('UPDATE sesiones_activas SET fecha_ultima_actividad = CURRENT_TIMESTAMP WHERE token = ?',
                          (session.get('token_sesion', ''),))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error en login_required: {e}")
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('rol') != 'ADMIN':
            flash('Acceso denegado', 'error')
            return redirect(url_for('inventario'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/captcha')
def captcha():
    texto = generar_captcha()
    return texto

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'codigo_acceso' not in session:
        session['codigo_acceso'] = generar_codigo_acceso(6)
    if request.method == 'POST':
        usuario_id = request.form.get('usuario_id', '').strip()
        contrasena = request.form.get('contrasena', '').strip()
        captcha_usuario = request.form.get('captcha', '').strip()
        captcha_guardado = session.get('captcha_texto', '')
        if captcha_usuario != captcha_guardado:
            flash('Código de verificación incorrecto', 'error')
            return render_template('login.html', captcha_texto=session.get('captcha_texto', ''))
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE usuario_id = ?", (usuario_id,))
        user = cursor.fetchone()
        if user and check_password_hash(user['contrasena'], contrasena):
            cursor.execute('SELECT * FROM sesiones_activas WHERE usuario_id = ? AND activo = 1', (user['id'],))
            sesion_activa = cursor.fetchone()
            if sesion_activa:
                cursor.execute('UPDATE sesiones_activas SET activo = 0, fecha_cierre = CURRENT_TIMESTAMP WHERE usuario_id = ? AND activo = 1', (user['id'],))
                registrar_log(user['id'], 'SESION_CERRADA_OTRO', 'sesiones', sesion_activa['id'], 'Sesión cerrada por nuevo inicio', request.remote_addr)
            token = generar_token_sesion()
            cursor.execute('INSERT INTO sesiones_activas (usuario_id, token, ip, user_agent) VALUES (?, ?, ?, ?)',
                          (user['id'], token, request.remote_addr, request.headers.get('User-Agent', '')[:200]))
            conn.commit()
            registrar_log(user['id'], 'LOGIN_EXITOSO', 'usuarios', user['id'], f'Inicio de sesión desde {request.remote_addr}', request.remote_addr)
            session.clear()
            session['user_id'] = user['id']
            session['usuario_id'] = user['usuario_id']
            session['rol'] = user['rol']
            session['token_sesion'] = token
            session['codigo_acceso'] = generar_codigo_acceso(6)
            flash(f'¡Bienvenido {usuario_id}!', 'success')
            conn.close()
            return redirect(url_for('inventario'))
        else:
            if user:
                registrar_log(user['id'], 'LOGIN_FALLIDO', 'usuarios', user['id'], 'Contraseña incorrecta', request.remote_addr)
            conn.close()
            flash('Usuario o contraseña incorrectos', 'error')
    generar_captcha()
    return render_template('login.html', captcha_texto=session.get('captcha_texto', ''))

@app.route('/logout')
def logout():
    try:
        if 'user_id' in session and 'token_sesion' in session:
            registrar_log(session['user_id'], 'LOGOUT', 'sesiones', None, 'Cierre de sesión', request.remote_addr)
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('UPDATE sesiones_activas SET activo = 0, fecha_cierre = CURRENT_TIMESTAMP WHERE token = ?', (session['token_sesion'],))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"Error en logout: {e}")
    session.clear()
    flash('Sesión cerrada correctamente', 'success')
    return redirect(url_for('login'))

@app.route('/inventario')
@login_required
def inventario():
    buscar = request.args.get('buscar', '')
    marca = request.args.get('marca', '')
    estatus = request.args.get('estatus', '')
    query = "SELECT * FROM vehiculos WHERE 1=1"
    params = []
    if buscar:
        query += " AND (chassis LIKE ? OR marca LIKE ? OR modelo LIKE ?)"
        params.extend([f'%{buscar}%', f'%{buscar}%', f'%{buscar}%'])
    if marca:
        query += " AND marca = ?"
        params.append(marca)
    if estatus:
        query += " AND estatus = ?"
        params.append(estatus)
    query += " ORDER BY id DESC"
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    vehiculos = cursor.fetchall()
    conn.close()
    registrar_log(session['user_id'], 'VER_INVENTARIO', 'vehiculos', None, f'Visualizó inventario', request.remote_addr)
    return render_template('inventario.html', vehiculos=vehiculos, rol=session.get('rol'))

@app.route('/cambiar_estatus_ajax/<int:id>')
@login_required
@admin_required
def cambiar_estatus_ajax(id):
    nuevo_estatus = request.args.get('nuevo_estatus', '')
    if nuevo_estatus not in ['DISPONIBLE', 'VENDIDO', 'RESERVADO']:
        return jsonify({'success': False})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT estatus, chassis, marca, modelo FROM vehiculos WHERE id = ?", (id,))
    vehiculo = cursor.fetchone()
    if vehiculo:
        cursor.execute("UPDATE vehiculos SET estatus = ? WHERE id = ?", (nuevo_estatus, id))
        conn.commit()
        registrar_log(session['user_id'], 'CAMBIAR_ESTATUS', 'vehiculos', id, f'{vehiculo["chassis"]}: {vehiculo["estatus"]} → {nuevo_estatus}', request.remote_addr)
    conn.close()
    return jsonify({'success': True, 'nuevo_estatus': nuevo_estatus})

@app.route('/estadisticas')
@login_required
def estadisticas():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM vehiculos")
    total = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(*) as total FROM vehiculos WHERE estatus = 'DISPONIBLE'")
    disponibles = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(*) as total FROM vehiculos WHERE estatus = 'VENDIDO'")
    vendidos = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(*) as total FROM vehiculos WHERE estatus = 'RESERVADO'")
    reservados = cursor.fetchone()['total']
    conn.close()
    return jsonify({'total': total, 'disponibles': disponibles, 'vendidos': vendidos, 'reservados': reservados})

@app.route('/subir_foto/<int:id>', methods=['POST'])
@login_required
@admin_required
def subir_foto(id):
    if 'foto' not in request.files:
        flash('No se seleccionó ningún archivo', 'error')
        return redirect(url_for('editar_vehiculo', id=id))
    archivo = request.files['foto']
    if archivo.filename == '':
        flash('No se seleccionó ningún archivo', 'error')
        return redirect(url_for('editar_vehiculo', id=id))
    if not allowed_image(archivo.filename):
        flash('Formato no permitido. Use: png, jpg, jpeg, gif, webp', 'error')
        return redirect(url_for('editar_vehiculo', id=id))
    try:
        extension = archivo.filename.rsplit('.', 1)[1].lower()
        nombre_archivo = f"vehiculo_{id}_{random.randint(1000, 9999)}.{extension}"
        nombre_archivo = secure_filename(nombre_archivo)
        ruta_archivo = os.path.join(UPLOAD_FOLDER_FOTOS, nombre_archivo)
        archivo.save(ruta_archivo)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT foto FROM vehiculos WHERE id = ?", (id,))
        foto_anterior = cursor.fetchone()
        if foto_anterior and foto_anterior['foto']:
            ruta_anterior = os.path.join(UPLOAD_FOLDER_FOTOS, foto_anterior['foto'])
            if os.path.exists(ruta_anterior):
                os.remove(ruta_anterior)
        cursor.execute("UPDATE vehiculos SET foto = ? WHERE id = ?", (nombre_archivo, id))
        conn.commit()
        conn.close()
        registrar_log(session['user_id'], 'SUBIR_FOTO', 'vehiculos', id, f'Subió foto: {nombre_archivo}', request.remote_addr)
        flash('✅ Foto subida exitosamente', 'success')
    except Exception as e:
        flash(f'❌ Error al subir foto: {str(e)}', 'error')
    return redirect(url_for('editar_vehiculo', id=id))

@app.route('/eliminar_foto/<int:id>')
@login_required
@admin_required
def eliminar_foto(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT foto FROM vehiculos WHERE id = ?", (id,))
    vehiculo = cursor.fetchone()
    if vehiculo and vehiculo['foto']:
        ruta_archivo = os.path.join(UPLOAD_FOLDER_FOTOS, vehiculo['foto'])
        if os.path.exists(ruta_archivo):
            os.remove(ruta_archivo)
        cursor.execute("UPDATE vehiculos SET foto = NULL WHERE id = ?", (id,))
        conn.commit()
        registrar_log(session['user_id'], 'ELIMINAR_FOTO', 'vehiculos', id, f'Eliminó foto: {vehiculo["foto"]}', request.remote_addr)
        flash('✅ Foto eliminada exitosamente', 'success')
    else:
        flash('❌ El vehículo no tiene foto', 'error')
    conn.close()
    return redirect(url_for('editar_vehiculo', id=id))

@app.route('/backup')
@login_required
@admin_required
def backup():
    try:
        zip_path, stats = crear_backup()
        registrar_log(session['user_id'], 'BACKUP_MANUAL', 'sistema', None, f'Backup creado: {os.path.basename(zip_path)} - {stats["total_vehiculos"]} vehículos', request.remote_addr)
        flash(f'✅ Backup creado exitosamente', 'success')
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'error')
    return redirect(url_for('lista_backups'))

@app.route('/lista_backups')
@login_required
@admin_required
def lista_backups():
    backups = []
    if os.path.exists(BACKUP_FOLDER):
        for archivo in os.listdir(BACKUP_FOLDER):
            if archivo.endswith('.zip'):
                ruta = os.path.join(BACKUP_FOLDER, archivo)
                tamanio = os.path.getsize(ruta)
                fecha = datetime.fromtimestamp(os.path.getmtime(ruta))
                backups.append({'nombre': archivo, 'ruta': ruta, 'tamanio': tamanio, 'fecha': fecha})
    backups.sort(key=lambda x: x['fecha'], reverse=True)
    registrar_log(session['user_id'], 'VER_BACKUPS', 'sistema', None, f'Visualizó {len(backups)} backups', request.remote_addr)
    return render_template('lista_backups.html', backups=backups)

@app.route('/descargar_backup/<nombre>')
@login_required
@admin_required
def descargar_backup(nombre):
    ruta = os.path.join(BACKUP_FOLDER, nombre)
    if not os.path.exists(ruta):
        flash('Backup no encontrado', 'error')
        return redirect(url_for('lista_backups'))
    registrar_log(session['user_id'], 'DESCARGAR_BACKUP', 'sistema', None, f'Descargó backup: {nombre}', request.remote_addr)
    return send_file(ruta, as_attachment=True, download_name=nombre)

@app.route('/eliminar_backup/<nombre>')
@login_required
@admin_required
def eliminar_backup(nombre):
    ruta = os.path.join(BACKUP_FOLDER, nombre)
    if os.path.exists(ruta):
        os.remove(ruta)
        registrar_log(session['user_id'], 'ELIMINAR_BACKUP', 'sistema', None, f'Eliminó backup: {nombre}', request.remote_addr)
        flash('Backup eliminado', 'success')
    return redirect(url_for('lista_backups'))

@app.route('/sesiones_activas')
@login_required
@admin_required
def sesiones_activas():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.*, u.usuario_id, u.rol FROM sesiones_activas s
        JOIN usuarios u ON s.usuario_id = u.id WHERE s.activo = 1 ORDER BY s.fecha_inicio DESC
    ''')
    sesiones = cursor.fetchall()
    conn.close()
    registrar_log(session['user_id'], 'VER_SESIONES', 'sesiones', None, 'Visualizó sesiones activas', request.remote_addr)
    return render_template('sesiones_activas.html', sesiones=sesiones)

@app.route('/cerrar_sesion_usuario/<int:sesion_id>')
@login_required
@admin_required
def cerrar_sesion_usuario(sesion_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT s.*, u.usuario_id FROM sesiones_activas s JOIN usuarios u ON s.usuario_id = u.id WHERE s.id = ?', (sesion_id,))
    sesion = cursor.fetchone()
    if sesion:
        registrar_log(session['user_id'], 'CERRAR_SESION_REMOTA', 'sesiones', sesion_id, f'Sesión cerrada del usuario {sesion["usuario_id"]}', request.remote_addr)
        cursor.execute('UPDATE sesiones_activas SET activo = 0, fecha_cierre = CURRENT_TIMESTAMP WHERE id = ?', (sesion_id,))
        conn.commit()
        flash('Sesión cerrada', 'success')
    conn.close()
    return redirect(url_for('sesiones_activas'))

@app.route('/logs_actividad')
@login_required
@admin_required
def logs_actividad():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT l.*, u.usuario_id, u.rol FROM logs_actividad l
        JOIN usuarios u ON l.usuario_id = u.id ORDER BY l.fecha DESC LIMIT 500
    ''')
    logs = cursor.fetchall()
    cursor.execute("SELECT DISTINCT accion FROM logs_actividad ORDER BY accion")
    acciones = cursor.fetchall()
    conn.close()
    registrar_log(session['user_id'], 'VER_LOGS', 'logs', None, 'Visualizó logs', request.remote_addr)
    return render_template('logs_actividad.html', logs=logs, acciones=acciones)

@app.route('/agregar_vehiculo', methods=['GET', 'POST'])
@login_required
@admin_required
def agregar_vehiculo():
    if request.method == 'POST':
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO vehiculos 
            (chassis, estatus, marca, modelo, tipo, ano, color, precio, precio_contado, precio_financiamiento, locacion, pais, bl) 
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (request.form['chassis'], request.form['estatus'], request.form['marca'],
             request.form['modelo'], request.form['tipo'], request.form['ano'],
             request.form['color'], request.form['precio'], request.form['precio_contado'],
             request.form['precio_financiamiento'], request.form['locacion'],
             request.form['pais'], request.form['bl']))
        vehiculo_id = cursor.lastrowid
        if 'foto' in request.files:
            archivo = request.files['foto']
            if archivo and archivo.filename != '' and allowed_image(archivo.filename):
                try:
                    extension = archivo.filename.rsplit('.', 1)[1].lower()
                    nombre_archivo = f"vehiculo_{vehiculo_id}_{random.randint(1000, 9999)}.{extension}"
                    nombre_archivo = secure_filename(nombre_archivo)
                    ruta_archivo = os.path.join(UPLOAD_FOLDER_FOTOS, nombre_archivo)
                    archivo.save(ruta_archivo)
                    cursor.execute("UPDATE vehiculos SET foto = ? WHERE id = ?", (nombre_archivo, vehiculo_id))
                except Exception as e:
                    print(f"Error al guardar foto: {e}")
        conn.commit()
        conn.close()
        registrar_log(session['user_id'], 'AGREGAR_VEHICULO', 'vehiculos', vehiculo_id, f'Agregó: {request.form["chassis"]} - {request.form["marca"]} {request.form["modelo"]}', request.remote_addr)
        flash('Vehículo agregado exitosamente', 'success')
        return redirect(url_for('inventario'))
    return render_template('agregar_vehiculo.html')

@app.route('/editar_vehiculo/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_vehiculo(id):
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        cursor.execute('''UPDATE vehiculos SET 
            chassis=?, estatus=?, marca=?, modelo=?, tipo=?, ano=?, color=?, 
            precio=?, precio_contado=?, precio_financiamiento=?, locacion=?, pais=?, bl=? WHERE id=?''',
            (request.form['chassis'], request.form['estatus'], request.form['marca'],
             request.form['modelo'], request.form['tipo'], request.form['ano'],
             request.form['color'], request.form['precio'], request.form['precio_contado'],
             request.form['precio_financiamiento'], request.form['locacion'],
             request.form['pais'], request.form['bl'], id))
        conn.commit()
        registrar_log(session['user_id'], 'EDITAR_VEHICULO', 'vehiculos', id, f'Editó vehículo ID {id}', request.remote_addr)
        conn.close()
        flash('Vehículo actualizado', 'success')
        return redirect(url_for('inventario'))
    cursor.execute("SELECT * FROM vehiculos WHERE id = ?", (id,))
    vehiculo = cursor.fetchone()
    conn.close()
    return render_template('editar_vehiculo.html', vehiculo=vehiculo)

@app.route('/eliminar_vehiculo/<int:id>')
@login_required
@admin_required
def eliminar_vehiculo(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT chassis, marca, modelo, foto FROM vehiculos WHERE id = ?", (id,))
    vehiculo = cursor.fetchone()
    if vehiculo and vehiculo['foto']:
        ruta_foto = os.path.join(UPLOAD_FOLDER_FOTOS, vehiculo['foto'])
        if os.path.exists(ruta_foto):
            os.remove(ruta_foto)
    cursor.execute("DELETE FROM vehiculos WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    registrar_log(session['user_id'], 'ELIMINAR_VEHICULO', 'vehiculos', id, f'Eliminó: {vehiculo["chassis"]} - {vehiculo["marca"]} {vehiculo["modelo"]}', request.remote_addr)
    flash('Vehículo eliminado', 'success')
    return redirect(url_for('inventario'))

@app.route('/usuarios')
@login_required
@admin_required
def usuarios():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, usuario_id, rol, fecha_creacion FROM usuarios")
    usuarios = cursor.fetchall()
    conn.close()
    registrar_log(session['user_id'], 'VER_USUARIOS', 'usuarios', None, 'Visualizó usuarios', request.remote_addr)
    return render_template('usuarios.html', usuarios=usuarios)

@app.route('/crear_usuario', methods=['POST'])
@login_required
@admin_required
def crear_usuario():
    usuario_id = request.form['usuario_id']
    contrasena = request.form['contrasena']
    rol = request.form['rol']
    hashed = generate_password_hash(contrasena)
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO usuarios (usuario_id, contrasena, rol) VALUES (?, ?, ?)", (usuario_id, hashed, rol))
        conn.commit()
        registrar_log(session['user_id'], 'CREAR_USUARIO', 'usuarios', cursor.lastrowid, f'Creó usuario: {usuario_id} ({rol})', request.remote_addr)
        flash(f'Usuario {usuario_id} creado', 'success')
    except:
        flash('Error: Usuario existe', 'error')
    finally:
        conn.close()
    return redirect(url_for('usuarios'))

@app.route('/eliminar_usuario/<int:id>')
@login_required
@admin_required
def eliminar_usuario(id):
    if id == session['user_id']:
        flash('No puedes eliminarte', 'error')
        return redirect(url_for('usuarios'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT usuario_id FROM usuarios WHERE id = ?", (id,))
    usuario = cursor.fetchone()
    cursor.execute("DELETE FROM usuarios WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    registrar_log(session['user_id'], 'ELIMINAR_USUARIO', 'usuarios', id, f'Eliminó usuario: {usuario["usuario_id"]}', request.remote_addr)
    flash('Usuario eliminado', 'success')
    return redirect(url_for('usuarios'))

@app.route('/editar_usuario/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_usuario(id):
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        usuario_id = request.form.get('usuario_id')
        rol = request.form.get('rol')
        nueva_contrasena = request.form.get('nueva_contrasena', '').strip()
        if nueva_contrasena:
            hashed_password = generate_password_hash(nueva_contrasena)
            cursor.execute("UPDATE usuarios SET usuario_id = ?, contrasena = ?, rol = ? WHERE id = ?",
                          (usuario_id, hashed_password, rol, id))
            registrar_log(session['user_id'], 'CAMBIAR_CONTRASENA_USUARIO', 'usuarios', id, f'Contraseña cambiada para usuario {usuario_id}', request.remote_addr)
        else:
            cursor.execute("UPDATE usuarios SET usuario_id = ?, rol = ? WHERE id = ?",
                          (usuario_id, rol, id))
        conn.commit()
        registrar_log(session['user_id'], 'EDITAR_USUARIO', 'usuarios', id, f'Editó usuario: {usuario_id} (Rol: {rol})', request.remote_addr)
        conn.close()
        flash('✅ Usuario actualizado correctamente', 'success')
        return redirect(url_for('usuarios'))
    cursor.execute("SELECT id, usuario_id, rol FROM usuarios WHERE id = ?", (id,))
    usuario = cursor.fetchone()
    conn.close()
    if not usuario:
        flash('❌ Usuario no encontrado', 'error')
        return redirect(url_for('usuarios'))
    return render_template('editar_usuario.html', usuario=usuario)

@app.route('/cambiar_mi_contraseña', methods=['GET', 'POST'])
@login_required
def cambiar_mi_contraseña():
    if request.method == 'POST':
        contrasena_actual = request.form.get('contrasena_actual', '').strip()
        nueva_contrasena = request.form.get('nueva_contrasena', '').strip()
        confirmar_contrasena = request.form.get('confirmar_contrasena', '').strip()
        if nueva_contrasena != confirmar_contrasena:
            flash('❌ Las contraseñas nuevas no coinciden', 'error')
            return redirect(url_for('cambiar_mi_contraseña'))
        if len(nueva_contrasena) < 4:
            flash('❌ La contraseña debe tener al menos 4 caracteres', 'error')
            return redirect(url_for('cambiar_mi_contraseña'))
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT contrasena FROM usuarios WHERE id = ?", (session['user_id'],))
        usuario = cursor.fetchone()
        if not check_password_hash(usuario['contrasena'], contrasena_actual):
            flash('❌ Contraseña actual incorrecta', 'error')
            conn.close()
            return redirect(url_for('cambiar_mi_contraseña'))
        nueva_hashed = generate_password_hash(nueva_contrasena)
        cursor.execute("UPDATE usuarios SET contrasena = ? WHERE id = ?", (nueva_hashed, session['user_id']))
        conn.commit()
        registrar_log(session['user_id'], 'CAMBIAR_MI_CONTRASENA', 'usuarios', session['user_id'], 'Cambió su propia contraseña', request.remote_addr)
        conn.close()
        flash('✅ Contraseña actualizada correctamente', 'success')
        return redirect(url_for('inventario'))
    return render_template('cambiar_contraseña.html')

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM vehiculos")
    total = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(*) as total FROM vehiculos WHERE estatus = 'DISPONIBLE'")
    disponibles = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(*) as total FROM vehiculos WHERE estatus = 'VENDIDO'")
    vendidos = cursor.fetchone()['total']
    cursor.execute("SELECT SUM(precio) as total FROM vehiculos")
    valor_total = cursor.fetchone()['total'] or 0
    cursor.execute("SELECT marca, COUNT(*) as total FROM vehiculos GROUP BY marca ORDER BY total DESC LIMIT 5")
    top_marcas = cursor.fetchall()
    cursor.execute("SELECT chassis, marca, modelo, ano, estatus, precio FROM vehiculos ORDER BY id DESC LIMIT 5")
    ultimos = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) as total_logs FROM logs_actividad")
    total_logs = cursor.fetchone()['total_logs']
    cursor.execute("SELECT COUNT(*) as logs_hoy FROM logs_actividad WHERE DATE(fecha) = DATE('now')")
    logs_hoy = cursor.fetchone()['logs_hoy']
    conn.close()
    registrar_log(session['user_id'], 'VER_DASHBOARD', 'dashboard', None, 'Visualizó dashboard', request.remote_addr)
    return render_template('dashboard.html', total_vehiculos=total, disponibles=disponibles, vendidos=vendidos, valor_total=valor_total, top_marcas=top_marcas, ultimos_vehiculos=ultimos, total_logs=total_logs, logs_hoy=logs_hoy)

@app.route('/ver_codigo')
@login_required
@admin_required
def ver_codigo():
    codigo = session.get('codigo_acceso', generar_codigo_acceso(6))
    registrar_log(session['user_id'], 'VER_CODIGO', 'configuracion', None, 'Visualizó código', request.remote_addr)
    return render_template('ver_codigo.html', codigo=codigo)

@app.route('/regenerar_codigo')
@login_required
@admin_required
def regenerar_codigo():
    nuevo = generar_codigo_acceso(6)
    session['codigo_acceso'] = nuevo
    registrar_log(session['user_id'], 'REGENERAR_CODIGO', 'configuracion', None, f'Nuevo código: {nuevo}', request.remote_addr)
    flash(f'Nuevo código: {nuevo}', 'success')
    return redirect(url_for('ver_codigo'))

@app.route('/exportar_excel')
@login_required
@admin_required
def exportar_excel():
    conn = get_db()
    df = pd.read_sql_query("SELECT * FROM vehiculos", conn)
    conn.close()
    registrar_log(session['user_id'], 'EXPORTAR_EXCEL', 'vehiculos', None, 'Exportó a Excel', request.remote_addr)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventario')
    output.seek(0)
    return send_file(output, download_name='inventario.xlsx', as_attachment=True)

@app.route('/importar_vehiculos', methods=['GET', 'POST'])
@login_required
@admin_required
def importar_vehiculos():
    if request.method == 'POST':
        if 'archivo' not in request.files:
            flash('No hay archivo', 'error')
            return redirect(url_for('importar_vehiculos'))
        archivo = request.files['archivo']
        if archivo.filename == '':
            flash('No se seleccionó archivo', 'error')
            return redirect(url_for('importar_vehiculos'))
        if not allowed_file(archivo.filename):
            flash('Formato no permitido', 'error')
            return redirect(url_for('importar_vehiculos'))
        try:
            filename = secure_filename(archivo.filename)
            filepath = os.path.join('uploads', filename)
            archivo.save(filepath)
            if filename.endswith('.csv'):
                df = pd.read_csv(filepath, encoding='utf-8')
            else:
                df = pd.read_excel(filepath)
            os.remove(filepath)
            df.columns = df.columns.str.strip().str.upper()
            conn = get_db()
            cursor = conn.cursor()
            agregados = 0
            for idx, row in df.iterrows():
                try:
                    chassis = str(row.get('CHASSIS', '')).strip()
                    marca = str(row.get('MARCA', '')).strip()
                    modelo = str(row.get('MODELO', '')).strip()
                    if not chassis or not marca or not modelo:
                        continue
                    cursor.execute("SELECT id FROM vehiculos WHERE chassis = ?", (chassis,))
                    if cursor.fetchone():
                        continue
                    estatus = str(row.get('ESTATUS', 'DISPONIBLE')).upper()
                    tipo = str(row.get('TIPO', '')) if pd.notna(row.get('TIPO')) else None
                    ano = int(row.get('ANO', 0)) if pd.notna(row.get('ANO')) else None
                    color = str(row.get('COLOR', '')) if pd.notna(row.get('COLOR')) else None
                    precio = float(row.get('PRECIO', 0)) if pd.notna(row.get('PRECIO')) else 0
                    precio_contado = float(row.get('PRECIO_CONTADO', 0)) if pd.notna(row.get('PRECIO_CONTADO')) else 0
                    precio_financiamiento = float(row.get('PRECIO_FINANCIAMIENTO', 0)) if pd.notna(row.get('PRECIO_FINANCIAMIENTO')) else 0
                    locacion = str(row.get('LOCACION', '')) if pd.notna(row.get('LOCACION')) else None
                    pais = str(row.get('PAIS', 'JAPON')) if pd.notna(row.get('PAIS')) else 'JAPON'
                    bl = str(row.get('BL', '')) if pd.notna(row.get('BL')) else None
                    cursor.execute('''INSERT INTO vehiculos 
                        (chassis, estatus, marca, modelo, tipo, ano, color, precio, precio_contado, precio_financiamiento, locacion, pais, bl) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (chassis, estatus, marca, modelo, tipo, ano, color, precio, precio_contado, precio_financiamiento, locacion, pais, bl))
                    agregados += 1
                except:
                    pass
            conn.commit()
            conn.close()
            registrar_log(session['user_id'], 'IMPORTAR_VEHICULOS', 'vehiculos', None, f'Importados {agregados} vehículos', request.remote_addr)
            flash(f'Importados {agregados} vehículos', 'success')
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('inventario'))
    return render_template('importar_vehiculos.html')

@app.route('/descargar_plantilla')
@login_required
@admin_required
def descargar_plantilla():
    plantilla = pd.DataFrame({'CHASSIS': ['ABC123'], 'MARCA': ['TOYOTA'], 'MODELO': ['COROLLA']})
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        plantilla.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, download_name='plantilla.xlsx', as_attachment=True)

if __name__ == '__main__':
    import socket
    print("\n" + "="*50)
    print("🚗 INVENTAUTOS - Servidor iniciado")
    print("="*50)
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"📍 Local:   http://localhost:5000")
        print(f"📍 Red:     http://{local_ip}:5000")
        print("\n📱 PARA ACCEDER DESDE CELULAR:")
        print(f"   1. Conecta tu celular al mismo WiFi")
        print(f"   2. Abre el navegador en: http://{local_ip}:5000")
    except:
        print("📍 Servidor: http://localhost:5000")
    print("="*50 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)