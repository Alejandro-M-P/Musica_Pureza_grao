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
import functools
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

from flask import Flask, session as flask_session, jsonify, request, send_from_directory, redirect
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
app.config["SESSION_COOKIE_HTTPONLY"] = True  # No accesible desde JS
app.config["SESSION_COOKIE_SECURE"] = False  # True si usas HTTPS
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # Protege contra CSRF
app.config["PERMANENT_SESSION_LIFETIME"] = 0  # Muere al cerrar navegador

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
    """Solo accesible si está logueado - redirige a / si está autenticado."""
    if not flask_session.get("username"):
        return redirect("/login")
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

# Tokens activos (generados por WebSocket login)
# Form: {token: {"username": str, "created_at": float}}
# Los tokens expiran después de 4 horas (14400 segundos)
active_tokens = {}
TOKEN_EXPIRY_SECONDS = 14400  # 4 horas

import secrets
from werkzeug.security import check_password_hash
import secrets


def generate_token() -> dict:
    """Generate a token with metadata for authentication.
    
    Returns:
        dict con keys: token, created_at, expires_in
    """
    token = secrets.token_hex(16)
    created_at = time.time()
    return {
        "token": token,
        "created_at": created_at,
        "expires_in": TOKEN_EXPIRY_SECONDS
    }


def validate_token(token: str) -> bool:
    """Check if token is valid and not expired.
    
    Returns:
        True si el token existe y no ha expirado.
    """
    if token not in active_tokens:
        return False
    token_data = active_tokens[token]
    created_at = token_data.get("created_at", 0)
    expiry_time = created_at + TOKEN_EXPIRY_SECONDS
    return time.time() < expiry_time


def get_token_username(token: str) -> str | None:
    """Get username associated with token."""
    if token in active_tokens:
        return active_tokens[token].get("username")
    return None


def cleanup_expired_tokens():
    """Remove expired tokens from active_tokens dict."""
    current_time = time.time()
    expired = [
        token for token, data in active_tokens.items()
        if current_time > data.get("created_at", 0) + TOKEN_EXPIRY_SECONDS
    ]
    for token in expired:
        del active_tokens[token]
    if expired:
        logger.info(f"Cleaned up {len(expired)} expired tokens")


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
    """Decorator require authentication for API routes.
    
    Accepts either:
    - Flask session (cookie-based login from /login)
    - X-Auth-Token header (WebSocket login)
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # Check Flask session first (legacy)
        username = flask_session.get("username")
        if username:
            return f(*args, **kwargs)
        
        # Check token header (WebSocket login)
        token = request.headers.get("X-Auth-Token")
        if token and validate_token(token):
            return f(*args, **kwargs)
        
        return jsonify({"success": False, "error": "No autenticado"}), 401
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
    """Página de login y handler - genera token para autenticación."""
    # Si ya está autenticado, ir al index
    if flask_session.get("username"):
        return redirect("/")
    
    if request.method == "GET":
        return '''<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>Login - Sistema Timbres</title></head>
<body style="font-family: sans-serif; padding: 50px; max-width: 400px; margin: 0 auto;">
<h1>Login - Sistema de Timbres</h1>
<form id="login-form">
<p><label>Usuario: <input name="username" required style="padding: 8px; width: 100%; font-size: 16px;"></label></p>
<p><label>Password: <input type="password" name="password" required style="padding: 8px; width: 100%; font-size: 16px;"></label></p>
<p><button type="submit" style="padding: 12px 20px; background: #007bff; color: white; border: none; font-size: 16px; cursor: pointer;">Entrar</button></p>
</form>
<div id="error" style="color: red; margin-top: 10px;"></div>
<script>
document.getElementById('login-form').onsubmit = async (e) => {
    e.preventDefault();
    const form = e.target;
    const username = form.username.value;
    const password = form.password.value;
    try {
        const resp = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: username, password: password})
        });
        const data = await resp.json();
        if (data.success) {
            localStorage.setItem('authToken', JSON.stringify(data));
            window.location.href = '/';
        } else {
            document.getElementById('error').textContent = data.error || 'Error de autenticación';
        }
    } catch (err) {
        document.getElementById('error').textContent = 'Error de conexión';
    }
};
</script>
</body>
</html>''', 200, {"Content-Type": "text/html"}
    
    # POST - validar credenciales via API (para consistencia)
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    
    if not username or not password:
        return jsonify({"success": False, "error": "Credenciales requeridas"}), 400
    
    # Validar contra .env
    if not validate_credentials(username, password):
        return jsonify({"success": False, "error": "Usuario o password incorrecto"}), 401
    
    # Generar token (igual que api_login)
    token_data = generate_token()
    token = token_data["token"]
    
    # Guardar en active_tokens
    active_tokens[token] = {
        "username": username,
        "created_at": token_data["created_at"]
    }
    
    # Setear sesión para navegación normal
    flask_session["username"] = username
    
    logger.info(f"User logged in: {username}")
    
    # Generar HTML que guarda token y redirige
    html = f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Redirecting...</title></head>
<script>
localStorage.setItem('authToken', JSON.stringify({json.dumps(token_data)}));
window.location.href = '/';
</script>
</html>'''
    return html, 200, {"Content-Type": "text/html"}


@app.route("/logout", methods=["POST"])
def logout():
    """Logout handler."""
    username = flask_session.pop("username", None)
    if username:
        logger.info(f"User logged out: {username}")
    return jsonify({"success": True})


# ============================================================================
# API: Login con token (JSON)
# ============================================================================

@app.route("/api/login", methods=["POST"])
def api_login():
    """POST /api/login — Autenticación con token que expira en 4 horas.
    
    Body JSON:
        {"username": "...", "password": "..."}
    
    Returns:
        JSON con {success: true, token: "...", created_at: ..., expires_in: 14400, username: "..."}
        o 401 si credenciales inválidas.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"success": False, "error": "JSON requerido"}), 400
        
        username = data.get("username", "").strip()
        password = data.get("password", "")
        
        if not username or not password:
            return jsonify({"success": False, "error": "Credenciales requeridas"}), 400
        
        # Validar credenciales contra .env
        if not validate_credentials(username, password):
            return jsonify({"success": False, "error": "Credenciales inválidas"}), 401
        
        # Generar token
        token_data = generate_token()
        token = token_data["token"]
        
        # Guardar en active_tokens con metadata
        active_tokens[token] = {
            "username": username,
            "created_at": token_data["created_at"]
        }
        
        # Setear sesión para navegación normal
        flask_session["username"] = username
        
        logger.info(f"Token generado para usuario: {username}")
        
        return jsonify({
            "success": True,
            "token": token,
            "created_at": token_data["created_at"],
            "expires_in": token_data["expires_in"],
            "username": username
        })
        
    except Exception as e:
        logger.error(f"Error en /api/login: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# Frontend
# ============================================================================

@app.route("/")
def index():
    """Serve the web interface - redirect to login if not authenticated."""
    # Check 1: Flask session (cookie-based)
    if flask_session.get("username"):
        return serve_index_html()
    
    # Check 2: Token header (X-Auth-Token)
    token = request.headers.get("X-Auth-Token")
    if token and validate_token(token):
        return serve_index_html()
    
    # No autenticado - redirigir a login
    return redirect("/login")


def serve_index_html():
    """Serve the main HTML file."""
    html_path = os.path.join(STATIC_DIR, "index.html")
    try:
        with open(html_path, "r") as f:
            return f.read(), 200, {"Content-Type": "text/html"}
    except FileNotFoundError:
        return jsonify({"error": "HTML no encontrado"}), 404


if __name__ == "__main__":
    logger.info("Iniciando servidor Flask...")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)