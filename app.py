from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'inventautos_secret_key_2024'
app.config['SESSION_TYPE'] = 'filesystem'

DATABASE = 'inventautos.db'

# Función para conectar a SQLite
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Inicializar base de datos
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Crear tabla usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id TEXT UNIQUE NOT NULL,
            contrasena TEXT NOT NULL,
            rol TEXT DEFAULT 'NORMAL',
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Crear tabla vehiculos
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
    
    # Insertar usuario admin si no existe
    cursor.execute("SELECT * FROM usuarios WHERE usuario_id = 'admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO usuarios (usuario_id, contrasena, rol) VALUES (?, ?, ?)",
                      ('admin', 'admin123', 'ADMIN'))
    
    # Insertar usuario normal de ejemplo
    cursor.execute("SELECT * FROM usuarios WHERE usuario_id = 'usuario1'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO usuarios (usuario_id, contrasena, rol) VALUES (?, ?, ?)",
                      ('usuario1', 'user123', 'NORMAL'))
    
    # Insertar vehículos de ejemplo
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

# Inicializar BD al iniciar
init_db()

# Decoradores
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

# Ruta login
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario_id = request.form.get('usuario_id', '').strip()
        contrasena = request.form.get('contrasena', '').strip()
        codigo = request.form.get('codigo', '').strip()
        
        CODIGO_VALIDO = '1234'
        
        if codigo != CODIGO_VALIDO:
            flash('Código de seguridad incorrecto', 'error')
            return render_template('login.html')
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE usuario_id = ? AND contrasena = ?", (usuario_id, contrasena))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            session.clear()
            session['user_id'] = user['id']
            session['usuario_id'] = user['usuario_id']
            session['rol'] = user['rol']
            flash(f'¡Bienvenido {usuario_id}!', 'success')
            return redirect(url_for('inventario'))
        else:
            flash('Usuario o contraseña incorrectos', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada correctamente', 'success')
    return redirect(url_for('login'))

@app.route('/inventario')
@login_required
def inventario():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vehiculos ORDER BY id DESC")
    vehiculos = cursor.fetchall()
    conn.close()
    return render_template('inventario.html', vehiculos=vehiculos, rol=session.get('rol'))

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
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO usuarios (usuario_id, contrasena, rol) VALUES (?, ?, ?)",
                      (usuario_id, contrasena, rol))
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
    app.run(debug=True, port=5000)