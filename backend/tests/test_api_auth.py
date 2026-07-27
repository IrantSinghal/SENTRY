import os
os.environ["DATABASE_URL"] = "postgresql://mock_user:mock_pass@localhost:5432/mock_db"
os.environ["GEMINI_API_KEY"] = "mock_api_key"

import sys
from unittest.mock import MagicMock, patch
import pytest
import jwt
from fastapi.testclient import TestClient

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.db import get_db
from app.auth import JWT_SECRET, JWT_ALGORITHM

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_db_session():
    mock_session = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_session
    yield mock_session
    app.dependency_overrides.clear()

def test_login_demo_user_success(mock_db_session):
    mock_user_row = ("a1111111-1111-1111-1111-111111111111", "analyst@test.com", "analyst", "Analyst User")
    mock_db_session.execute.return_value.fetchone.return_value = mock_user_row
    
    response = client.post("/auth/login", json={"email": "analyst@test.com"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role"] == "analyst"
    assert data["user"]["display_name"] == "Analyst User"

def test_login_demo_user_not_found(mock_db_session):
    mock_db_session.execute.return_value.fetchone.return_value = None
    
    response = client.post("/auth/login", json={"email": "invalid@test.com"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Email address not registered or recognized."

def test_get_me_unauthorized():
    response = client.get("/auth/me")
    assert response.status_code == 403  # HTTPBearer defaults to 403 if header is missing

def test_get_me_authorized(mock_db_session):
    token = jwt.encode(
        {"sub": "a1111111-1111-1111-1111-111111111111", "email": "analyst@test.com", "role": "analyst"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )
    
    mock_role_row = ("analyst", "Analyst User")
    mock_db_session.execute.return_value.fetchone.return_value = mock_role_row
    
    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "analyst"
    assert data["email"] == "analyst@test.com"

def test_override_decision_authorization(mock_db_session):
    cfo_token = jwt.encode(
        {"sub": "d4444444-4444-4444-4444-444444444444", "email": "cfo@test.com", "role": "cfo"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )
    
    analyst_token = jwt.encode(
        {"sub": "a1111111-1111-1111-1111-111111111111", "email": "analyst@test.com", "role": "analyst"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )

    mock_triage_info = ("cfo", True) # required_role = cfo, requires_named_authority = True
    
    # Test 1: Analyst attempts override (should be 403)
    mock_db_session.execute.return_value.fetchone.side_effect = [
        ("analyst", "Analyst User"), # auth.py user role lookup
        mock_triage_info # main.py override triage metadata lookup
    ]
    
    response = client.post(
        "/requisitions/REQ_001/override",
        json={"override_decision": "approved", "reason": "Analyst override test"},
        headers={"Authorization": f"Bearer {analyst_token}"}
    )
    assert response.status_code == 403
    assert "Access Denied" in response.json()["detail"]

    # Test 2: CFO attempts override (should be 200)
    mock_db_session.execute.return_value.fetchone.side_effect = [
        ("cfo", "CFO User"),
        mock_triage_info,
        (
            "REQ_001", "auto_approve", 0.95, {}, "Approved by CFO", 
            "approved", "CFO override test", "cfo", True, "d4444444-4444-4444-4444-444444444444", "2026-07-13T12:00:00Z",
            [], None
        )
    ]
    
    response = client.post(
        "/requisitions/REQ_001/override",
        json={"override_decision": "approved", "reason": "CFO override test"},
        headers={"Authorization": f"Bearer {cfo_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["human_override"] == "approved"
    assert data["overridden_by_user_id"] == "d4444444-4444-4444-4444-444444444444"
