"""Tests para src/web_utils.py - Validadores de la interfaz web."""

import pytest
from src.web_utils import validate_hour, validate_extension, validate_duration


class TestValidateHour:
    """Tests para validate_hour()."""
    
    def test_hora_valida_ok(self):
        """Horas válidas deben ser aceptadas."""
        assert validate_hour("08:05") is True
        assert validate_hour("23:59") is True
        assert validate_hour("00:00") is True
        assert validate_hour("12:30") is True
    
    def test_hora_formato_invalido(self):
        """Formato inválido debe ser rechazado."""
        assert validate_hour("8:5") is False
        assert validate_hour("25:00") is False
        assert validate_hour("12:60") is False
        assert validate_hour("1:1") is False
        assert validate_hour("12-30") is False
        assert validate_hour("") is False
        assert validate_hour("1230") is False
    
    def test_hora_fuera_rango(self):
        """Horas fuera de rango deben ser rechazadas."""
        assert validate_hour("24:00") is False
        assert validate_hour("25:01") is False
        assert validate_hour("-01:00") is False


class TestValidateExtension:
    """Tests para validate_extension()."""
    
    def test_extension_valida(self):
        """Extensiones válidas deben ser aceptadas."""
        assert validate_extension("cancion.mp3") is True
        assert validate_extension("cancion.wav") is True
        assert validate_extension("cancion.flac") is True
        assert validate_extension("cancion.ogg") is True
        assert validate_extension("cancion.mp4") is True
        assert validate_extension("cancion.m4a") is True
    
    def test_extension_mayusculas(self):
        """Debe aceptar mayúsculas."""
        assert validate_extension("cancion.MP3") is True
        assert validate_extension("cancion.MP4") is True
    
    def test_extension_invalida(self):
        """Extensiones inválidas deben ser rechazadas."""
        assert validate_extension("archivo.exe") is False
        assert validate_extension("documento.pdf") is False
        assert validate_extension("imagen.jpg") is False
        assert validate_extension("") is False


class TestValidateDuration:
    """Tests para validate_duration()."""
    
    def test_duracion_valida(self):
        """Duración dentro de rango debe ser aceptada."""
        assert validate_duration(5) is True
        assert validate_duration(60) is True
        assert validate_duration(300) is True
    
    def test_duracion_fuera_rango(self):
        """Duración fuera de rango debe ser rechazada."""
        assert validate_duration(4) is False
        assert validate_duration(301) is False
        assert validate_duration(0) is False
        assert validate_duration(-1) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])