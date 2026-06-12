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

app = Flask(__name__)
app.secret_key = 'inventautos_secret_key_2024'
app.config['SESSION_TYPE'] = 'filesystem'

DATABASE = 'inventautos.db'

# Configuración para uploads
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ============ FUNCIONES CAPTCHA Y CÓDIGO ============
def generar_captcha():
    """Genera un código CAPTCHA simple de 5 dígitos"""
    texto = ''.join(str(random.randint(0, 9)) for _ in range(5))
    session['captcha_texto'] = texto
    return texto

def generar_codigo_acceso(longitud=6):
    """Genera un código de acceso aleatorio de 6 dígitos"""
    return ''.join(str(random.randint(0, 9)) for _ in range(longitud))

# ============ BASE DE DATOS ============
def get_db():
    conn = sqlite3.connect(DATABASE)
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
            bl TEXT
        )
    ''')
    
    # Usuario admin
    cursor.execute("SELECT * FROM usuarios WHERE usuario_id = 'admin'")
    if not cursor.fetchone():
        hashed_password = generate_password_hash('admin123')
        cursor.execute("INSERT INTO usuarios (usuario_id, contrasena, rol) VALUES (?, ?, ?)",
                      ('admin', hashed_password, 'ADMIN'))
    
    # Usuario normal
    cursor.execute("SELECT * FROM usuarios WHERE usuario_id = 'usuario1'")
    if not cursor.fetchone():
        hashed_password = generate_password_hash('user123')
        cursor.execute("INSERT INTO usuarios (usuario_id, contrasena, rol) VALUES (?, ?, ?)",
                      ('usuario1', hashed_password, 'NORMAL'))
    
    # Vehículos de ejemplo
    cursor.execute("SELECT * FROM vehiculos LIMIT 1")
    if not cursor.fetchone():
        vehiculos_ejemplo = [
            ('MXPH10-2027887', 'DISPONIBLE', 'TOYOTA', 'YARIS', 'AUTOMOVIL', 2021, 'GRIS', 0, 0, 0, 'JAPON', 'JAPON', 'S00348455'),
            ('MXPH10-2019696', 'DISPONIBLE', 'TOYOTA', 'YARIS', 'AUTOMOVIL', 2021, 'GRIS', 0, 0, 0, 'JAPON', 'JAPON', 'S00344704'),
            ('NHP130-4023111', 'DISPONIBLE', 'TOYOTA', 'VITZ', 'AUTOMOVIL', 2021, 'BLANCO', 850000, 785000, 0, '23/03/2026 SADA', 'JAPON', 'S00336965'),
        ]
        cursor.executemany('''INSERT INTO vehiculos 
            (chassis, estatus, marca, modelo, tipo, ano, color, precio, precio_contado, precio_financiamiento, locacion, pais, bl) 
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', vehiculos_ejemplo)
    
    conn.commit()
    conn.close()

init_db()

# ============ DECORADORES ============
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor inicia sesión primero', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('rol') != 'ADMIN':
            flash('Acceso denegado. Se requieren privilegios de administrador', 'error')
            return redirect(url_for('inventario'))
        return f(*args, **kwargs)
    return decorated_function

# ============ RUTAS ============
@app.route('/captcha')
def captcha():
    """Genera un CAPTCHA de solo texto"""
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
        conn.close()
        
        if user and check_password_hash(user['contrasena'], contrasena):
            session.clear()
            session['user_id'] = user['id']
            session['usuario_id'] = user['usuario_id']
            session['rol'] = user['rol']
            session['codigo_acceso'] = generar_codigo_acceso(6)
            flash(f'¡Bienvenido {usuario_id}!', 'success')
            return redirect(url_for('inventario'))
        else:
            flash('Usuario o contraseña incorrectos', 'error')
    
    generar_captcha()
    return render_template('login.html', captcha_texto=session.get('captcha_texto', ''))

@app.route('/ver_codigo')
@login_required
@admin_required
def ver_codigo():
    codigo = session.get('codigo_acceso', generar_codigo_acceso(6))
    return render_template('ver_codigo.html', codigo=codigo)

@app.route('/regenerar_codigo')
@login_required
@admin_required
def regenerar_codigo():
    nuevo_codigo = generar_codigo_acceso(6)
    session['codigo_acceso'] = nuevo_codigo
    flash(f'Nuevo código de acceso generado: {nuevo_codigo}', 'success')
    return redirect(url_for('ver_codigo'))

@app.route('/logout')
def logout():
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
    return render_template('inventario.html', vehiculos=vehiculos, rol=session.get('rol'))

@app.route('/cambiar_estatus_ajax/<int:id>')
@login_required
@admin_required
def cambiar_estatus_ajax(id):
    """Cambia el estatus del vehículo vía AJAX"""
    nuevo_estatus = request.args.get('nuevo_estatus', '')
    
    if nuevo_estatus not in ['DISPONIBLE', 'VENDIDO', 'RESERVADO']:
        return jsonify({'success': False, 'error': 'Estado no válido'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE vehiculos SET estatus = ? WHERE id = ?", (nuevo_estatus, id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'nuevo_estatus': nuevo_estatus})

@app.route('/estadisticas')
@login_required
@admin_required
def estadisticas():
    """Devuelve las estadísticas en JSON para actualizar las tarjetas"""
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
    
    return jsonify({
        'total': total,
        'disponibles': disponibles,
        'vendidos': vendidos,
        'reservados': reservados
    })

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as total FROM vehiculos")
    total_vehiculos = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM vehiculos WHERE estatus = 'DISPONIBLE'")
    disponibles = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM vehiculos WHERE estatus = 'VENDIDO'")
    vendidos = cursor.fetchone()['total']
    
    cursor.execute("SELECT SUM(precio) as total FROM vehiculos")
    valor_total = cursor.fetchone()['total'] or 0
    
    cursor.execute("""
        SELECT marca, COUNT(*) as total 
        FROM vehiculos 
        GROUP BY marca 
        ORDER BY total DESC 
        LIMIT 5
    """)
    top_marcas = cursor.fetchall()
    
    cursor.execute("""
        SELECT chassis, marca, modelo, ano, estatus, precio 
        FROM vehiculos 
        ORDER BY id DESC 
        LIMIT 5
    """)
    ultimos_vehiculos = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard.html', 
                         total_vehiculos=total_vehiculos,
                         disponibles=disponibles,
                         vendidos=vendidos,
                         valor_total=valor_total,
                         top_marcas=top_marcas,
                         ultimos_vehiculos=ultimos_vehiculos)

@app.route('/exportar_excel')
@login_required
@admin_required
def exportar_excel():
    conn = get_db()
    df = pd.read_sql_query("SELECT * FROM vehiculos", conn)
    conn.close()
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventario')
    
    output.seek(0)
    return send_file(output, download_name='inventario.xlsx', as_attachment=True)

@app.route('/descargar_plantilla')
@login_required
@admin_required
def descargar_plantilla():
    plantilla = pd.DataFrame({
        'CHASSIS': ['ABC123-456789', 'DEF456-789012'],
        'ESTATUS': ['DISPONIBLE', 'DISPONIBLE'],
        'MARCA': ['TOYOTA', 'NISSAN'],
        'MODELO': ['COROLLA', 'VERSA'],
        'TIPO': ['SEDAN', 'SEDAN'],
        'ANO': [2022, 2021],
        'COLOR': ['ROJO', 'AZUL'],
        'PRECIO': [15000, 12000],
        'PRECIO_CONTADO': [14000, 11000],
        'PRECIO_FINANCIAMIENTO': [16000, 13000],
        'LOCACION': ['JAPON', 'JAPON'],
        'PAIS': ['JAPON', 'JAPON'],
        'BL': ['BL001', 'BL002']
    })
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        plantilla.to_excel(writer, index=False, sheet_name='Plantilla')
    
    output.seek(0)
    return send_file(output, download_name='plantilla_vehiculos.xlsx', as_attachment=True)

@app.route('/importar_vehiculos', methods=['GET', 'POST'])
@login_required
@admin_required
def importar_vehiculos():
    if request.method == 'POST':
        if 'archivo' not in request.files:
            flash('No se seleccionó ningún archivo', 'error')
            return redirect(url_for('importar_vehiculos'))
        
        archivo = request.files['archivo']
        
        if archivo.filename == '':
            flash('No se seleccionó ningún archivo', 'error')
            return redirect(url_for('importar_vehiculos'))
        
        if not allowed_file(archivo.filename):
            flash('Formato no permitido. Use .xlsx, .xls o .csv', 'error')
            return redirect(url_for('importar_vehiculos'))
        
        try:
            filename = secure_filename(archivo.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            archivo.save(filepath)
            
            if filename.endswith('.csv'):
                df = pd.read_csv(filepath, encoding='utf-8')
            else:
                df = pd.read_excel(filepath)
            
            os.remove(filepath)
            
            df.columns = df.columns.str.strip().str.upper()
            
            conn = get_db()
            cursor = conn.cursor()
            
            vehiculos_agregados = 0
            vehiculos_omitidos = 0
            errores = []
            
            for idx, row in df.iterrows():
                try:
                    chassis = str(row.get('CHASSIS', '')).strip()
                    marca = str(row.get('MARCA', '')).strip()
                    modelo = str(row.get('MODELO', '')).strip()
                    
                    if not chassis or not marca or not modelo:
                        errores.append(f"Fila {idx + 2}: Faltan campos requeridos")
                        vehiculos_omitidos += 1
                        continue
                    
                    cursor.execute("SELECT id FROM vehiculos WHERE chassis = ?", (chassis,))
                    if cursor.fetchone():
                        errores.append(f"Fila {idx + 2}: Chassis {chassis} ya existe")
                        vehiculos_omitidos += 1
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
                        (chassis, estatus, marca, modelo, tipo, ano, color, 
                         precio, precio_contado, precio_financiamiento, locacion, pais, bl) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (chassis, estatus, marca, modelo, tipo, ano, color,
                         precio, precio_contado, precio_financiamiento, locacion, pais, bl))
                    
                    vehiculos_agregados += 1
                    
                except Exception as e:
                    errores.append(f"Fila {idx + 2}: Error - {str(e)}")
                    vehiculos_omitidos += 1
            
            conn.commit()
            conn.close()
            
            flash(f'✅ Importación completada: {vehiculos_agregados} vehículos agregados, {vehiculos_omitidos} omitidos', 'success')
            
            if errores and len(errores) <= 5:
                for error in errores:
                    flash(f'⚠️ {error}', 'error')
            elif errores:
                flash(f'⚠️ {len(errores)} errores en total. Revisa el formato del archivo.', 'error')
            
            return redirect(url_for('inventario'))
            
        except Exception as e:
            flash(f'Error al leer el archivo: {str(e)}', 'error')
            return redirect(url_for('importar_vehiculos'))
    
    return render_template('importar_vehiculos.html')

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
        conn.commit()
        conn.close()
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
            precio=?, precio_contado=?, precio_financiamiento=?, locacion=?, pais=?, bl=? 
            WHERE id=?''',
            (request.form['chassis'], request.form['estatus'], request.form['marca'],
             request.form['modelo'], request.form['tipo'], request.form['ano'],
             request.form['color'], request.form['precio'], request.form['precio_contado'],
             request.form['precio_financiamiento'], request.form['locacion'],
             request.form['pais'], request.form['bl'], id))
        conn.commit()
        conn.close()
        flash('Vehículo actualizado exitosamente', 'success')
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
    cursor.execute("DELETE FROM vehiculos WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('Vehículo eliminado correctamente', 'success')
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
    return render_template('usuarios.html', usuarios=usuarios)

@app.route('/crear_usuario', methods=['POST'])
@login_required
@admin_required
def crear_usuario():
    usuario_id = request.form['usuario_id']
    contrasena = request.form['contrasena']
    rol = request.form['rol']
    
    hashed_password = generate_password_hash(contrasena)
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO usuarios (usuario_id, contrasena, rol) VALUES (?, ?, ?)",
                      (usuario_id, hashed_password, rol))
        conn.commit()
        flash(f'Usuario {usuario_id} creado exitosamente', 'success')
    except:
        flash('Error: El usuario ya existe', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('usuarios'))

@app.route('/eliminar_usuario/<int:id>')
@login_required
@admin_required
def eliminar_usuario(id):
    if id == session['user_id']:
        flash('No puedes eliminar tu propio usuario', 'error')
        return redirect(url_for('usuarios'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('Usuario eliminado correctamente', 'success')
    return redirect(url_for('usuarios'))

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