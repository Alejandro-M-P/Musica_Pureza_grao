"""Web utilities — validation helpers for the web interface."""

import re
import os

# Regex para validar formato HH:MM (formato 24 horas)
HOUR_PATTERN = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

# Extensiones de audio válidas
VALID_AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".flac", ".ogg", ".mp4", ".m4a"})

# Duración mínima y máxima en segundos
MIN_DURATION_SECONDS = 5
MAX_DURATION_SECONDS = 300


def validate_hour(hhmm: str) -> bool:
    """Valida que una hora esté en formato válido de 24 horas (HH:MM).
    
    Args:
        hhmm: String con la hora a validar (ej: "08:05", "23:59").
        
    Returns:
        True si el formato es válido, False en caso contrario.
    """
    if not hhmm:
        return False
    return HOUR_PATTERN.match(hhmm.strip()) is not None


def validate_extension(filename: str) -> bool:
    """Valida que un archivo tenga extensión de audio válida.
    
    Args:
        filename: Nombre del archivo a validar.
        
    Returns:
        True si la extensión es válida (.mp3, .wav, .flac, .ogg, .mp4, .m4a).
    """
    if not filename:
        return False
    _, ext = os.path.splitext(filename.lower())
    return ext in VALID_AUDIO_EXTENSIONS


def validate_duration(seconds: int) -> bool:
    """Valida que la duración de una canción esté en rango razonable.
    
    Args:
        seconds: Duración en segundos.
        
    Returns:
        True si la duración está entre MIN_DURATION_SECONDS y MAX_DURATION_SECONDS.
    """
    return MIN_DURATION_SECONDS <= seconds <= MAX_DURATION_SECONDS


def get_audio_duration(file_path: str) -> int | None:
    """Obtiene la duración de un archivo de audio en segundos.
    
    Usa ffprobe si está disponible, retorna None si no se puede determinar.
    
    Args:
        file_path: Ruta al archivo de audio.
        
    Returns:
        Duración en segundos, o None si no se pudo obtener.
    """
    try:
        import subprocess
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(float(result.stdout.strip()))
    except Exception:
        pass
    return None