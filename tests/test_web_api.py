"""Tests de integración para la API Flask."""

import json
import pytest
import sys
import os

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])