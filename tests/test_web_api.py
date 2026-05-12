"""Tests de integración para la API Flask."""

import json
import pytest
import sys
import os
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, MUSIC_TYPES


@pytest.fixture
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def authenticated_client(client):
    """Authenticated test client using Flask session."""
    # Login first to get session
    with client.session_transaction() as sess:
        sess["username"] = "admin"
    return client


class TestAPIHorarios:
    """Tests para /api/horarios."""
    
    def test_get_horarios_requires_auth(self, client):
        """GET /api/horarios debe requerir autenticación."""
        response = client.get("/api/horarios")
        assert response.status_code == 401
    
    def test_get_horarios_authenticated(self, authenticated_client):
        """GET /api/horarios con auth debe retornar schedule."""
        response = authenticated_client.get("/api/horarios")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "entrada" in data["horarios"]
        assert "salida" in data["horarios"]
    
    def test_put_horarios_requires_auth(self, client):
        """PUT /api/horarios debe requerir autenticación."""
        response = client.put(
            "/api/horarios",
            json={"entrada": ["08:00"], "salida": ["14:00"], "cambio": [], "recreo": []}
        )
        assert response.status_code == 401
    
    def test_put_horarios_invalid_format(self, authenticated_client):
        """PUT horarios debe rechazar formato inválido."""
        response = authenticated_client.put(
            "/api/horarios",
            json={"entrada": ["25:00"], "salida": ["14:00"], "cambio": [], "recreo": []}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
    
    def test_put_horarios_valid(self, authenticated_client):
        """PUT horarios debe actualizar schedule."""
        response = authenticated_client.put(
            "/api/horarios",
            json={"entrada": ["09:00"], "salida": ["15:00"], "cambio": ["10:00"], "recreo": ["12:00"]}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True


class TestAPICola:
    """Tests para /api/cola/{tipo}."""
    
    def test_get_cola_requires_auth(self, client):
        """GET /api/cola/entrada debe requerir autenticación."""
        response = client.get("/api/cola/entrada")
        assert response.status_code == 401
    
    def test_get_cola_invalid_type(self, authenticated_client):
        """GET /api/cola con tipo inválido debe fallar."""
        response = authenticated_client.get("/api/cola/invalido")
        assert response.status_code == 400
    
    def test_get_cola_valid(self, authenticated_client):
        """GET /api/cola con tipo válido debe retornar cola."""
        response = authenticated_client.get("/api/cola/entrada")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["tipo"] == "entrada"


class TestAPIUpload:
    """Tests para /api/upload."""
    
    def test_upload_requires_auth(self, client):
        """POST /api/upload debe requerir autenticación."""
        response = client.post("/api/upload")
        assert response.status_code == 401


class TestAPIDuraciones:
    """Tests para duraciones en /api/horarios."""
    
    def test_get_horarios_no_durations(self, client):
        """GET sin duraciones en state debe retornar duraciones vacío."""
        with patch("app.state_manager.get_durations", return_value={}):
            response = client.get("/api/horarios")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True
            assert "duraciones" in data
            assert data["duraciones"] == {}
    
    def test_get_horarios_with_durations(self, client):
        """GET con duraciones debe retornarlas."""
        mock_durations = {"entrada": 30, "salida": 60, "cambio": None, "recreo": 120}
        with patch("app.state_manager.get_durations", return_value=mock_durations):
            response = client.get("/api/horarios")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True
            assert data["duraciones"]["entrada"] == 30
            assert data["duraciones"]["salida"] == 60
            assert data["duraciones"]["cambio"] is None
            assert data["duraciones"]["recreo"] == 120
    
    def test_put_horarios_with_duraciones(self, authenticated_client):
        """PUT con duraciones debe guardarlas via state_manager."""
        duraciones = {"entrada": 30, "salida": 60}
        payload = {
            "entrada": ["08:00"],
            "salida": ["14:00"],
            "cambio": [],
            "recreo": [],
            "duraciones": duraciones
        }
        with patch("app.state_manager.update_durations") as mock_update:
            response = authenticated_client.put("/api/horarios", json=payload)
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True
            mock_update.assert_called_once_with(duraciones)
    
    def test_put_horarios_without_duraciones(self, authenticated_client):
        """PUT sin duraciones no debe cambiarlas (backward compat)."""
        payload = {
            "entrada": ["08:00"],
            "salida": ["14:00"],
            "cambio": [],
            "recreo": []
        }
        with patch("app.state_manager.update_durations") as mock_update:
            response = authenticated_client.put("/api/horarios", json=payload)
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True
            mock_update.assert_not_called()
    
    def test_put_horarios_duraciones_string_value(self, authenticated_client):
        """PUT con duración string debe fallar con 400."""
        response = authenticated_client.put(
            "/api/horarios",
            json={
                "entrada": ["08:00"],
                "salida": ["14:00"],
                "cambio": [],
                "recreo": [],
                "duraciones": {"entrada": "abc"}
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
    
    def test_put_horarios_duraciones_negative(self, authenticated_client):
        """PUT con duración negativa debe fallar con 400."""
        response = authenticated_client.put(
            "/api/horarios",
            json={
                "entrada": ["08:00"],
                "salida": ["14:00"],
                "cambio": [],
                "recreo": [],
                "duraciones": {"entrada": -1}
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
    
    def test_put_horarios_duraciones_too_large(self, authenticated_client):
        """PUT con duración > 600 debe fallar con 400."""
        response = authenticated_client.put(
            "/api/horarios",
            json={
                "entrada": ["08:00"],
                "salida": ["14:00"],
                "cambio": [],
                "recreo": [],
                "duraciones": {"entrada": 601}
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
    
    def test_put_horarios_duraciones_null(self, authenticated_client):
        """PUT con duración null debe ser válido (canción completa)."""
        payload = {
            "entrada": ["08:00"],
            "salida": ["14:00"],
            "cambio": [],
            "recreo": [],
            "duraciones": {"entrada": None}
        }
        with patch("app.state_manager.update_durations") as mock_update:
            response = authenticated_client.put("/api/horarios", json=payload)
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True
            mock_update.assert_called_once_with({"entrada": None})
    
    def test_put_horarios_duraciones_bool_value(self, authenticated_client):
        """PUT con duración booleana debe fallar (bool != int)."""
        response = authenticated_client.put(
            "/api/horarios",
            json={
                "entrada": ["08:00"],
                "salida": ["14:00"],
                "cambio": [],
                "recreo": [],
                "duraciones": {"entrada": True}
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
    
    def test_put_horarios_duraciones_float_value(self, authenticated_client):
        """PUT con duración float debe fallar (no es entero)."""
        response = authenticated_client.put(
            "/api/horarios",
            json={
                "entrada": ["08:00"],
                "salida": ["14:00"],
                "cambio": [],
                "recreo": [],
                "duraciones": {"entrada": 30.5}
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
    
    def test_put_horarios_duraciones_zero(self, authenticated_client):
        """PUT con duración 0 debe fallar (menor a 5)."""
        response = authenticated_client.put(
            "/api/horarios",
            json={
                "entrada": ["08:00"],
                "salida": ["14:00"],
                "cambio": [],
                "recreo": [],
                "duraciones": {"entrada": 0}
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
    
    def test_put_horarios_duraciones_empty_dict(self, authenticated_client):
        """PUT con duraciones vacío debe ser válido."""
        payload = {
            "entrada": ["08:00"],
            "salida": ["14:00"],
            "cambio": [],
            "recreo": [],
            "duraciones": {}
        }
        with patch("app.state_manager.update_durations") as mock_update:
            response = authenticated_client.put("/api/horarios", json=payload)
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True
            mock_update.assert_called_once_with({})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])