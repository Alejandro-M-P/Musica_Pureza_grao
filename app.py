"""Flask Web Interface for School Bell System.

Proporciona una API REST y WebSocket para controlar el sistema de timbres
desde cualquier navegador en la red local.
"""

import json
import logging
import os
import shutil
import tempfile
import threading
import time
from datetime import datetime

# Cargar variables de entorno desde .env
from pathlib import Path
env_path = Path("/home/admins/colegio/.env")
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

# Cargar usuario y password desde .env
WEB_USER = os.environ.get('USER', 'admin')
WEB_PASSWORD = os.environ.get('PASSWORD', 'admin123')

# Función de autenticación
def validate_credentials(username: str, password: str) -> bool:
    """Valida usuario y contraseña contra .env"""
    return username == WEB_USER and password == WEB_PASSWORD

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# Import del sistema existente
from src.cron_helper import load_schedule, PROJECT_DIR
from src.library import MusicLibrary, MusicFolderError
from src.player import MusicPlayer
from src.state import StateManager
from src.web_utils import (
    validate_hour,
    validate_extension,
    get_audio_duration,
    MIN_DURATION_SECONDS,
    MAX_DURATION_SECONDS,
)
from werkzeug.utils import secure_filename

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración
MUSIC_BASE = "/home/admins/musica"
UPLOAD_FOLDER = MUSIC_BASE
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".mp4", ".m4a"}
MUSIC_TYPES = ["entrada", "salida", "cambio", "recreo"]

# Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = "school-bell-secret-key-change-in-production"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Habilitar CORS para todos los orígenes (accesible desde otros PCs)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Servir archivos estáticos (HTML) desde directorio público
import os
STATIC_DIR = "/home/admins/public_html/bell"
@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)

@app.route("/index.html")
def serve_index():
    """Solo accesible si está logueado."""
    if not flask_session.get("username"):
        return '''<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>Login - Sistema Timbres</title></head>
<body style="font-family: sans-serif; padding: 50px; max-width: 400px; margin: 0 auto;">
<h1>Login - Sistema de Timbres</h1>
<p style="color: red;">Debes iniciar sesión primero.</p>
<form method="post" action="/login">
<p><label>Usuario: <input name="username" required style="padding: 8px; width: 100%; font-size: 16px;"></label></p>
<p><label>Password: <input type="password" name="password" required style="padding: 8px; width: 100%; font-size: 16px;"></label></p>
<p><button type="submit" style="padding: 12px 20px; background: #007bff; color: white; border: none; font-size: 16px; cursor: pointer;">Entrar</button></p>
</form>
</body>
</html>''', 200, {"Content-Type": "text/html"}
    return send_from_directory(STATIC_DIR, "index.html")

# SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Instancias globales
state_manager = StateManager()
music_library = MusicLibrary(MUSIC_BASE)
music_player = MusicPlayer(MUSIC_BASE)

# ============================================================================
# Autenticación con credenciales Linux
# ============================================================================

import functools
from flask import session as flask_session
from werkzeug.security import check_password_hash


# Users válidos (se validan contra sistema Linux)
VALID_LINUX_USERS = frozenset({"admin", "profesor", "director"})


def get_valid_user(username: str) -> str | None:
    """Check if username exists in /etc/passwd.
    
    Returns:
        Username if valid, None otherwise.
    """
    try:
        with open("/etc/passwd", "r") as f:
            for line in f:
                if line.startswith(username + ":"):
                    return username
    except Exception:
        pass
    return None


def validate_linux_password(username: str, password: str) -> bool:
    """Validate credentials against Linux system using PAM or shadow.
    
    Uses simple method: check against shadow file if accessible,
    otherwise fallback to hardcoded for demo.
    
    Returns:
        True if credentials valid.
    """
    # Try to validate via getspnam (requires root)
    try:
        import spwd
        try:
            entry = spwd.getspnam(username)
            return check_password_hash(entry.sp_pwd, password)
        except (KeyError, PermissionError):
            # Fallback to demo users if PAM not available
            pass
    except ImportError:
        pass
    
    # Demo fallback: only allow specific users with demo passwords
    # En producción, usar PAM o LDAP
    demo_users = {
        "admin": "admin123",
        "profesor": "profesor123",
        "director": "director123",
    }
    
    return demo_users.get(username) == password


def require_auth(f):
    """Decorator require authentication for API routes."""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # Check Flask session
        username = flask_session.get("username")
        if not username:
            return jsonify({"success": False, "error": "No autenticado"}), 401
        return f(*args, **kwargs)
    return decorated_function


# Habilitar signed cookies para sesión segura
app.secret_key = "school-bell-secret-key-change-in-production"


def allowed_file(filename: str) -> bool:
    """Check if file has valid audio extension."""
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXTENSIONS


def broadcast_estado(tipo: str = None):
    """Broadcast estado actual a todos los clientes WebSocket conectados."""
    try:
        data = {
            "tipo": tipo,
            "timestamp": datetime.now().isoformat(),
        }
        
        if tipo:
            folder_state = state_manager.get_folder_state(tipo)
            data["cola"] = folder_state.get("queue", [])
            data["last_played"] = folder_state.get("last_played")
            data["last_played_time"] = folder_state.get("last_played_time")
        
        socketio.emit("estado_actualizado", data)
        logger.info(f"Broadcast estado: {tipo}")
    except Exception as e:
        logger.error(f"Error en broadcast: {e}")


# ============================================================================
# WebSocket Handlers
# ============================================================================

@socketio.on("connect")
def handle_connect():
    """Cliente WebSocket conectado."""
    logger.info(f"Cliente WS conectado: {request.sid}")
    emit("conectado", {"status": "ok", "timestamp": datetime.now().isoformat()})


@socketio.on("disconnect")
def handle_disconnect():
    """Cliente WebSocket desconectado."""
    logger.info(f"Cliente WS desconectado: {request.sid}")


# ============================================================================
# API: Horarios
# ============================================================================

@app.route("/api/horarios", methods=["GET"])
def get_horarios():
    """GET /api/horarios — Retorna todos los horarios configurados.
    
    Returns:
        JSON con estructura: {"entrada": ["08:05", "15:15"], ...}
    """
    try:
        schedule = load_schedule()
        return jsonify({"success": True, "horarios": schedule})
    except Exception as e:
        logger.error(f"Error GET /api/horarios: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/exportar", methods=["GET"])
def exportar_backup():
    """GET /api/exportar — Exporta schedule + estado como JSON descargable."""
    try:
        state = state_manager.load()
        schedule = state_manager.get_schedule()
        
        backup = {
            "exportado": datetime.now().isoformat(),
            "schedule": schedule,
            "estado": state
        }
        
        return jsonify(backup)
    except Exception as e:
        logger.error(f"Error exportar: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/horarios", methods=["PUT"])
@require_auth
def put_horarios():
    """PUT /api/horarios — Actualiza los horarios.
    
    Body JSON:
        {"entrada": ["08:05", "15:15"], "cambio": [...], ...}
    
    Returns:
        JSON con {"success": True} o error.
    """
    try:
        data = request.get_json()
        
        if not data or not isinstance(data, dict):
            return jsonify({"success": False, "error": "JSON inválido"}), 400
        
        # Validar estructura base
        for tipo in MUSIC_TYPES:
            if tipo not in data:
                return jsonify({"success": False, "error": f"Falta tipo: {tipo}"}), 400

            if not isinstance(data[tipo], list):
                return jsonify({"success": False, "error": f"Tipo {tipo} debe ser una lista"}), 400

            # Validar cada hora
            for hora in data[tipo]:
                if not validate_hour(hora):
                    return jsonify({"success": False, "error": f"Hora inválida: {hora}"}), 400

        # Guardar en StateManager (carousel.json)
        state_manager.update_schedule(data)

        # Broadcast a clientes
        broadcast_estado()
        
        logger.info(f"Horarios actualizados: {data}")
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error PUT /api/horarios: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# API: Cola de reproducción
# ============================================================================

@app.route("/api/canciones/<tipo>", methods=["GET"])
def get_canciones(tipo: str):
    """GET /api/canciones/{tipo} — Lista canciones en carpeta."""
    try:
        if tipo not in MUSIC_TYPES:
            return jsonify({"success": False, "error": f"Tipo inválido: {tipo}"}), 400
        
        folder_path = os.path.join(MUSIC_BASE, tipo)
        if not os.path.isdir(folder_path):
            return jsonify({"success": True, "canciones": []})
        
        canciones = []
        for entry in os.listdir(folder_path):
            _, ext = os.path.splitext(entry)
            if ext.lower() in ALLOWED_EXTENSIONS:
                full_path = os.path.join(folder_path, entry)
                canciones.append({
                    "nombre": entry,
                    "path": full_path
                })
        
        return jsonify({"success": True, "canciones": sorted(canciones, key=lambda x: x["nombre"].lower())})
    except Exception as e:
        logger.error(f"Error GET /api/canciones/{tipo}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cola/<tipo>", methods=["GET"])
def get_cola(tipo: str):
    """GET /api/cola/{tipo} — Obtiene la cola de canciones para un tipo.
    
    Args:
        tipo: Tipo de música (entrada, salida, cambio, recreo).
        
    Returns:
        JSON con cola, last_played, last_played_time.
    """
    try:
        if tipo not in MUSIC_TYPES:
            return jsonify({"success": False, "error": f"Tipo inválido: {tipo}"}), 400
        
        folder_state = state_manager.get_folder_state(tipo)
        
        return jsonify({
            "success": True,
            "tipo": tipo,
            "cola": folder_state.get("queue", []),
            "last_played": folder_state.get("last_played"),
            "last_played_time": folder_state.get("last_played_time")
        })
    except Exception as e:
        logger.error(f"Error GET /api/cola/{tipo}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# API: Reproducir
# ============================================================================

@app.route("/api/reproducir/<tipo>", methods=["POST"])
def post_reproducir(tipo: str):
    """POST /api/reproducir/{tipo} — Fuerza reproducción inmediata.
    
    Args:
        tipo: Tipo de música (entrada, salida, cambio, recreo).
        
    Returns:
        JSON con success y canción reproducida.
    """
    try:
        if tipo not in MUSIC_TYPES:
            return jsonify({"success": False, "error": f"Tipo inválido: {tipo}"}), 400
        
        with play_lock:
            # Reproducir
            music_player.play(tipo)
            
            # Actualizar estado
            state = state_manager.get_folder_state(tipo)
            last_played = state.get("last_played")
            last_played_time = datetime.now().isoformat()
            
            state_manager.update_folder_state(
                tipo,
                last_played=last_played,
                last_played_time=last_played_time
            )
        
        # Broadcast a clientes
        broadcast_estado(tipo)
        
        return jsonify({
            "success": True,
            "tipo": tipo,
            "last_played": last_played,
            "last_played_time": last_played_time
        })
    except Exception as e:
        logger.error(f"Error POST /api/reproducir/{tipo}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# API: Validar canción
# ============================================================================

@app.route("/api/validar-cancion", methods=["POST"])
@require_auth
def validar_cancion():
    """POST /api/validar-cancion — Valida un archivo de audio.
    
    Body JSON:
        {"path": "/path/to/song.mp3"}
    
    Returns:
        JSON con metadata de la canción.
    """
    try:
        data = request.get_json()
        file_path = data.get("path")
        
        if not file_path:
            return jsonify({"success": False, "error": "Falta path"}), 400
        
        if not os.path.exists(file_path):
            return jsonify({"success": False, "error": "Archivo no existe"}), 404
        
        if not validate_extension(file_path):
            return jsonify({"success": False, "error": "Extensión inválida"}), 400
        
        # Obtener duración
        duration = get_audio_duration(file_path)
        
        result = {
            "success": True,
            "path": file_path,
            "filename": os.path.basename(file_path),
            "duration": duration,
        }
        
        # Advertir si duración muy larga
        if duration and (duration < MIN_DURATION_SECONDS or duration > MAX_DURATION_SECONDS):
            result["warning"] = f"Duración fuera de rango recomendado ({MIN_DURATION_SECONDS}-{MAX_DURATION_SECONDS}s)"
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error POST /api/validar-cancion: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# API: Upload
# ============================================================================

@app.route("/api/upload", methods=["POST"])
@require_auth
def upload_file():
    """POST /api/upload — Sube archivo de audio.
    
    Form-data:
        - file: Archivo de audio
        - tipo: Tipo de música (entrada, salida, cambio, recreo)
    
    Returns:
        JSON con success y ruta del archivo guardado.
    """
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400
        
        file = request.files["file"]
        tipo = request.form.get("tipo", "entrada")
        
        if tipo not in MUSIC_TYPES:
            return jsonify({"success": False, "error": f"Tipo inválido: {tipo}"}), 400
        
        if file.filename == "":
            return jsonify({"success": False, "error": "Empty filename"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({"success": False, "error": "Extensión inválida"}), 400
        
        # Guardar en carpeta correcta
        target_folder = os.path.join(UPLOAD_FOLDER, tipo)
        os.makedirs(target_folder, exist_ok=True)
        
        filename = secure_filename(file.filename)
        target_path = os.path.join(target_folder, filename)
        
        file.save(target_path)
        
        logger.info(f"Archivo subido: {target_path}")
        
        # Broadcast cambio de estado
        broadcast_estado(tipo)
        
        return jsonify({
            "success": True,
            "path": target_path,
            "tipo": tipo
        })
    except Exception as e:
        logger.error(f"Error POST /api/upload: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# API: Eliminar canción
# ============================================================================

@app.route("/api/cancion", methods=["DELETE"])
@require_auth
def delete_cancion():
    """DELETE /api/cancion — Elimina archivo de audio.
    
    Body JSON:
        {"path": "/path/to/song.mp3"}
    
    Returns:
        JSON con success.
    """
    try:
        data = request.get_json()
        file_path = data.get("path")
        
        if not file_path:
            return jsonify({"success": False, "error": "Falta path"}), 400
        
        if not os.path.exists(file_path):
            return jsonify({"success": False, "error": "Archivo no existe"}), 404
        
        os.remove(file_path)
        logger.info(f"Archivo eliminado: {file_path}")
        
        return jsonify({"success": True, "path": file_path})
    except Exception as e:
        logger.error(f"Error DELETE /api/cancion: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cancion/mover", methods=["POST"])
@require_auth
def mover_cancion():
    """POST /api/cancion/mover — Mueve canción a otra carpeta.
    
    Body JSON:
        {"path": "/path/to/song.mp3", "destino": "entrada"}
    
    Returns:
        JSON con success y nueva ruta.
    """
    try:
        data = request.get_json()
        file_path = data.get("path")
        destino = data.get("destino")
        
        if not file_path or not destino:
            return jsonify({"success": False, "error": "Faltan path o destino"}), 400
        
        if destino not in MUSIC_TYPES:
            return jsonify({"success": False, "error": "Destino inválido"}), 400
        
        if not os.path.exists(file_path):
            return jsonify({"success": False, "error": "Archivo no existe"}), 404
        
        # Nueva ubicación
        filename = os.path.basename(file_path)
        target_dir = os.path.join(MUSIC_BASE, destino)
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, filename)
        
        # Mover archivo
        shutil.move(file_path, target_path)
        logger.info(f"Archivo movido: {file_path} -> {target_path}")
        
        return jsonify({"success": True, "path": target_path, "destino": destino})
    except Exception as e:
        logger.error(f"Error mover canción: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# Rutas de Autenticación
# ============================================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    """Página de login y handler."""
    if request.method == "GET":
        return '''<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>Login - Sistema Timbres</title></head>
<body style="font-family: sans-serif; padding: 50px; max-width: 400px; margin: 0 auto;">
<h1>Login - Sistema de Timbres</h1>
<form method="post">
<p><label>Usuario: <input name="username" required style="padding: 8px; width: 100%; font-size: 16px;"></label></p>
<p><label>Password: <input type="password" name="password" required style="padding: 8px; width: 100%; font-size: 16px;"></label></p>
<p><button type="submit" style="padding: 12px 20px; background: #007bff; color: white; border: none; font-size: 16px; cursor: pointer;">Entrar</button></p>
</form>
</body>
</html>''', 200, {"Content-Type": "text/html"}
    
    # POST - validar credenciales
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    
    if not username or not password:
        return jsonify({"success": False, "error": "Credenciales requeridas"}), 400
    
    # Validar contra .env
    if not validate_credentials(username, password):
        return jsonify({"success": False, "error": "Usuario o password incorrecto"}), 401
    
    # Create Flask session
    flask_session["username"] = username
    logger.info(f"User logged in: {username}")
    
    # Redirect to main page
    return jsonify({"success": True, "redirect": "/"})


@app.route("/logout", methods=["POST"])
def logout():
    """Logout handler."""
    username = flask_session.pop("username", None)
    if username:
        logger.info(f"User logged out: {username}")
    return jsonify({"success": True})


# ============================================================================
# Frontend
# ============================================================================

@app.route("/")
def index():
    """Serve login or the web interface."""
    # Si no está autenticado, mostrar login
    if not flask_session.get("username"):
        return '''<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>Login - Sistema Timbres</title></head>
<body style="font-family: sans-serif; padding: 50px; max-width: 400px; margin: 0 auto;">
<h1>Login - Sistema de Timbres</h1>
<form method="post" action="/login">
<p><label>Usuario: <input name="username" required style="padding: 8px; width: 100%; font-size: 16px;"></label></p>
<p><label>Password: <input type="password" name="password" required style="padding: 8px; width: 100%; font-size: 16px;"></label></p>
<p><button type="submit" style="padding: 12px 20px; background: #007bff; color: white; border: none; font-size: 16px; cursor: pointer;">Entrar</button></p>
</form>
</body>
</html>''', 200, {"Content-Type": "text/html"}
    
    # Si está autenticado, mostrar la interfaz
    html_path = os.path.join(STATIC_DIR, "index.html")
    try:
        with open(html_path, "r") as f:
            return f.read(), 200, {"Content-Type": "text/html"}
    except FileNotFoundError:
        return jsonify({"error": "HTML no encontrado"}), 404


def create_html_interface() -> str:
    """Genera el HTML de la interfaz web."""
    return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sistema de Timbres - Colegio</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               background: #f5f5f5; padding: 20px; }
        h1 { color: #333; margin-bottom: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        .card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; 
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .card h2 { color: #555; margin-bottom: 15px; font-size: 1.2em; }
        .tipo-section { margin-bottom: 20px; }
        .tipo-section h3 { color: #333; margin-bottom: 10px; }
        .horarios-list { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
        .horario-input { width: 80px; padding: 8px; border: 1px solid #ddd; border-radius: 4px; 
                        font-size: 14px; }
        .btn { padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; 
               font-size: 14px; margin-right: 10px; }
        .btn-primary { background: #007bff; color: white; }
        .btn-primary:hover { background: #0056b3; }
        .btn-success { background: #28a745; color: white; }
        .btn-success:hover { background: #218838; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-danger:hover { background: #c82333; }
        .btn-secondary { background: #6c757d; color: white; }
        .btn-secondary:hover { background: #5a6268; }
        .status { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
        .status-dot { width: 10px; height: 10px; border-radius: 50%; }
        .status-dot.connected { background: #28a745; }
        .status-dot.disconnected { background: #dc3545; }
        .last-played { color: #666; font-size: 0.9em; margin-top: 10px; }
        .upload-section { margin-top: 20px; }
        .upload-section input, .upload-section select { padding: 8px; border: 1px solid #ddd; 
                                                         border-radius: 4px; margin-right: 10px; }
        .error { background: #f8d7da; color: #721c24; padding: 10px; border-radius: 4px; 
                margin-bottom: 10px; }
        .success { background: #d4edda; color: #155724; padding: 10px; border-radius: 4px; 
                  margin-bottom: 10px; }
        .queue { font-size: 0.9em; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Sistema de Timbres - Colegio</h1>
        
        <div class="card">
            <h2>Estado de Conexión</h2>
            <div class="status">
                <div id="status-dot" class="status-dot disconnected"></div>
                <span id="status-text">Desconectado</span>
            </div>
        </div>
        
        <div class="card">
            <h2>Horarios</h2>
            <div id="horarios-container">Cargando...</div>
            <button class="btn btn-success" onclick="guardarHorarios()">Guardar Horarios</button>
            <div id="save-message"></div>
        </div>
        
        <div class="card">
            <h2>Control de Reproducción</h2>
            <div id="player-container">Cargando...</div>
        </div>
        
        <div class="card">
            <h2>Subir Música</h2>
            <div class="upload-section">
                <input type="file" id="upload-file" accept=".mp3,.wav,.flac,.ogg,.mp4,.m4a">
                <select id="upload-tipo">
                    <option value="entrada">Entrada</option>
                    <option value="recreo">Recreo</option>
                    <option value="cambio">Cambio</option>
                    <option value="salida">Salida</option>
                </select>
                <button class="btn btn-primary" onclick="subirArchivo()">Subir</button>
                <div id="upload-message"></div>
            </div>
        </div>
    </div>
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
    <script>
        const TIPO_LABELS = {entrada: 'Entrada', salida: 'Salida', cambio: 'Cambio', recreo: 'Recreo'};
        const TIPOS = ['entrada', 'salida', 'cambio', 'recreo'];
        let socket;
        let horariosData = {};
        
        // Conectar WebSocket
        function connectWebSocket() {
            socket = io();
            
            socket.on('connect', () => {
                document.getElementById('status-dot').className = 'status-dot connected';
                document.getElementById('status-text').textContent = 'Conectado';
            });
            
            socket.on('disconnect', () => {
                document.getElementById('status-dot').className = 'status-dot disconnected';
                document.getElementById('status-text').textContent = 'Desconectado';
            });
            
            socket.on('estado_actualizado', (data) => {
                if (data.tipo) actualizarCola(data.tipo);
            });
        }
        
        // Cargar horarios
        async function cargarHorarios() {
            try {
                const resp = await fetch('/api/horarios');
                const data = await resp.json();
                if (data.success) {
                    horariosData = data.horarios;
                    renderHorarios();
                }
            } catch (e) {
                console.error('Error cargando horarios:', e);
            }
        }
        
        // Renderizar horarios
        function renderHorarios() {
            const container = document.getElementById('horarios-container');
            container.innerHTML = TIPOS.map(tipo => `
                <div class="tipo-section">
                    <h3>${TIPO_LABELS[tipo]}</h3>
                    <div class="horarios-list" id="horarios-${tipo}">
                        ${(horariosData[tipo] || []).map(h => 
                            `<input type="text" class="horario-input" value="${h}" data-tipo="${tipo}">`
                        ).join('')}
                        <button class="btn btn-secondary" onclick="agregarHorario('${tipo}')">+</button>
                    </div>
                </div>
            `).join('');
        }
        
        // Agregar horario
        function agregarHorario(tipo) {
            const container = document.getElementById('horarios-' + tipo);
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'horario-input';
            input.value = '09:00';
            input.dataset.tipo = tipo;
            container.insertBefore(input, container.lastElementChild);
        }
        
        // Guardar horarios
        async function guardarHorarios() {
            const nuevosHorarios = {};
            TIPOS.forEach(tipo => {
                nuevosHorarios[tipo] = [];
                document.querySelectorAll('[data-tipo="' + tipo + '"]').forEach(input => {
                    if (input.value.trim()) nuevosHorarios[tipo].push(input.value.trim());
                });
            });
            
            try {
                const resp = await fetch('/api/horarios', {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(nuevosHorarios)
                });
                const data = await resp.json();
                const msg = document.getElementById('save-message');
                if (data.success) {
                    msg.className = 'success';
                    msg.textContent = 'Horarios guardados';
                    horariosData = nuevosHorarios;
                } else {
                    msg.className = 'error';
                    msg.textContent = data.error;
                }
                setTimeout(() => msg.textContent = '', 3000);
            } catch (e) {
                console.error('Error guardando:', e);
            }
        }
        
        // Cargar colas
        async function cargarColas() {
            const container = document.getElementById('player-container');
            container.innerHTML = '';
            for (const tipo of TIPOS) {
                try {
                    const resp = await fetch('/api/cola/' + tipo);
                    const data = await resp.json();
                    if (data.success) {
                        container.innerHTML += `
                            <div class="tipo-section">
                                <h3>${TIPO_LABELS[tipo]}</h3>
                                <button class="btn btn-success" onclick="reproducir('${tipo}')">▶ Reproducir</button>
                                <div class="last-played">Última: ${data.last_played || 'Ninguna'}</div>
                            </div>
                        `;
                    }
                } catch (e) {
                    console.error('Error cargando cola:', tipo, e);
                }
            }
        }
        
        // Reproducir
        async function reproducir(tipo) {
            try {
                await fetch('/api/reproducir/' + tipo, {method: 'POST'});
            } catch (e) {
                console.error('Error reproduciendo:', e);
            }
        }
        
        // Actualizar cola
        async function actualizarCola(tipo) {
            cargarColas();
        }
        
        // Subir archivo
        async function subirArchivo() {
            const fileInput = document.getElementById('upload-file');
            const tipoSelect = document.getElementById('upload-tipo');
            const msg = document.getElementById('upload-message');
            
            if (!fileInput.files[0]) {
                msg.className = 'error';
                msg.textContent = 'Selecciona un archivo';
                return;
            }
            
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            formData.append('tipo', tipoSelect.value);
            
            try {
                const resp = await fetch('/api/upload', {method: 'POST', body: formData});
                const data = await resp.json();
                if (data.success) {
                    msg.className = 'success';
                    msg.textContent = 'Archivo subido: ' + data.path;
                    cargarColas();
                } else {
                    msg.className = 'error';
                    msg.textContent = data.error;
                }
            } catch (e) {
                msg.className = 'error';
                msg.textContent = 'Error: ' + e;
            }
            setTimeout(() => msg.textContent = '', 3000);
        }
        
        // Init
        window.onload = () => {
            connectWebSocket();
            cargarHorarios();
            cargarColas();
        };
    </script>
</body>
</html>"""


# Crear directorio templates antes de escribir el HTML
import os as _os
_TEMPLATE_DIR = _os.path.join(_os.path.dirname(__file__), "templates")
_os.makedirs(_TEMPLATE_DIR, exist_ok=True)

# Escribir archivo HTML
with open(_os.path.join(_TEMPLATE_DIR, "index.html"), "w") as f:
    f.write(create_html_interface())


if __name__ == "__main__":
    logger.info("Iniciando servidor Flask...")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)