import os
os.environ["DATABASE_URL"] = "postgresql://mock_user:mock_pass@localhost:5432/mock_db"
os.environ["GEMINI_API_KEY"] = "mock_api_key"

import sys
from unittest.mock import MagicMock
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

def test_get_launchpad_summary(mock_db_session):
    token = jwt.encode(
        {"sub": "a1111111-1111-1111-1111-111111111111", "email": "analyst@test.com", "role": "analyst"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )
    
    def mock_execute(query, params=None):
        mock_result = MagicMock()
        query_str = str(query)
        if "UserRole" in query_str or "display_name" in query_str:
            mock_result.fetchone.return_value = ("analyst", "Analyst User")
        elif "requires_named_authority" in query_str:
            mock_result.scalar.return_value = 2
        elif "overall_release_status" in query_str:
            mock_result.scalar.return_value = 10
        elif "VendorScreeningCache" in query_str:
            mock_result.scalar.return_value = 5
        return mock_result

    mock_db_session.execute.side_effect = mock_execute
    
    response = client.get(
        "/dashboard/launchpad-summary",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pending_queue_count"] == 10
    assert data["flagged_vendors_7d_count"] == 5
    assert data["needs_authority_count"] == 2

def test_get_settings(mock_db_session):
    token = jwt.encode(
        {"sub": "a1111111-1111-1111-1111-111111111111", "email": "analyst@test.com", "role": "analyst"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )
    mock_db_session.execute.return_value.fetchone.return_value = ("analyst", "Analyst User")
    
    response = client.get(
        "/settings",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "auto_approval_ceiling" in data
    assert "confidence_threshold" in data

def test_post_settings_non_admin_forbidden(mock_db_session):
    token = jwt.encode(
        {"sub": "a1111111-1111-1111-1111-111111111111", "email": "analyst@test.com", "role": "analyst"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )
    mock_db_session.execute.return_value.fetchone.return_value = ("analyst", "Analyst User")
    
    response = client.post(
        "/settings",
        json={"auto_approval_ceiling": 10000.0, "confidence_threshold": 0.90},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403
    assert "Only administrator users" in response.json()["detail"]

def test_post_settings_admin_success(mock_db_session):
    token = jwt.encode(
        {"sub": "admin-id", "email": "admin@test.com", "role": "admin"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )
    mock_db_session.execute.return_value.fetchone.return_value = ("admin", "Admin User")
    
    response = client.post(
        "/settings",
        json={"auto_approval_ceiling": 12500.0, "confidence_threshold": 0.92},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["auto_approval_ceiling"] == 12500.0
    assert data["confidence_threshold"] == 0.92


def test_get_analytics_summary_with_range(mock_db_session):
    token = jwt.encode(
        {"sub": "analyst-id", "email": "analyst@test.com", "role": "analyst"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )
    
    mock_totals = MagicMock()
    mock_totals.fetchone.return_value = (10, 5, 2, 3)
    
    mock_signals = MagicMock()
    mock_signals.fetchall.return_value = [
        ({"price_anomaly": {"has_anomaly": True}},),
        ({"vendor_risk": {"is_risky": True}},)
    ]
    
    mock_daily = MagicMock()
    mock_daily.fetchall.return_value = [
        ("2026-07-15", 3, 1, 0),
        ("2026-07-16", 2, 2, 2)
    ]
    
    def mock_execute(query, params=None):
        query_str = str(query)
        if "GROUP BY day" in query_str:
            return mock_daily
        elif "COUNT(*)" in query_str and "verdict =" in query_str:
            return mock_totals
        elif "signals" in query_str:
            return mock_signals
        elif "UserRole" in query_str:
            mock_role = MagicMock()
            mock_role.fetchone.return_value = ("analyst", "Analyst User")
            return mock_role
        return MagicMock()

    mock_db_session.execute.side_effect = mock_execute
    
    response = client.get(
        "/analytics/summary?range=7d",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_processed"] == 10
    assert data["total_approved"] == 5
    assert data["total_rejected"] == 2
    assert data["total_escalated"] == 3
    assert data["escalation_reason_breakdown"]["price_anomaly"] == 1
    assert data["escalation_reason_breakdown"]["vendor_risk"] == 1
    assert len(data["daily_volume"]) == 2


def test_get_audit_log(mock_db_session):
    token = jwt.encode(
        {"sub": "analyst-id", "email": "analyst@test.com", "role": "analyst"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )
    
    mock_count = MagicMock()
    mock_count.scalar.return_value = 1
    
    from datetime import datetime, timezone
    mock_rows = MagicMock()
    mock_rows.fetchall.return_value = [
        ("REQ_001", "auto_approve", 0.95, "approver", False, datetime.now(timezone.utc), None, None, "user1", "group1", 1500.0)
    ]
    
    def mock_execute(query, params=None):
        query_str = str(query)
        if "COUNT" in query_str:
            return mock_count
        elif "TriageResult" in query_str:
            return mock_rows
        elif "UserRole" in query_str:
            mock_role = MagicMock()
            mock_role.fetchone.return_value = ("analyst", "Analyst User")
            return mock_role
        return MagicMock()
        
    mock_db_session.execute.side_effect = mock_execute
    
    response = client.get(
        "/audit-log?page=1&limit=25&verdict=auto_approve&search=REQ",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["requisition_id"] == "REQ_001"
    assert data["items"][0]["total_value"] == 1500.0


def test_export_audit_log(mock_db_session):
    token = jwt.encode(
        {"sub": "analyst-id", "email": "analyst@test.com", "role": "analyst"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )
    
    from datetime import datetime, timezone
    mock_rows = MagicMock()
    mock_rows.fetchall.return_value = [
        ("REQ_001", "auto_approve", 0.95, "approver", False, datetime.now(timezone.utc), None, None, "user1", "group1", 1500.0)
    ]
    
    def mock_execute(query, params=None):
        query_str = str(query)
        if "TriageResult" in query_str:
            return mock_rows
        elif "UserRole" in query_str:
            mock_role = MagicMock()
            mock_role.fetchone.return_value = ("analyst", "Analyst User")
            return mock_role
        return MagicMock()
        
    mock_db_session.execute.side_effect = mock_execute
    
    response = client.get(
        "/audit-log/export?verdict=auto_approve",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment; filename=\"audit_log.csv\"" in response.headers["content-disposition"]
    content = response.text
    assert "Requisition ID,Verdict,Confidence Score" in content
    assert "REQ_001,auto_approve,0.95" in content


def test_get_vendors_and_screening_summary(mock_db_session):
    token = jwt.encode(
        {"sub": "analyst-id", "email": "analyst@test.com", "role": "analyst"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )
    
    mock_vendors = MagicMock()
    mock_vendors.fetchall.return_value = [
        ("V1", "Vendor 1", "2024-01-01", ["compliance"], "2027-01-01", "TAX1", "Address 1")
    ]
    
    mock_summary = MagicMock()
    mock_summary.fetchone.return_value = (5, 1, 2, 0)
    
    def mock_execute(query, params=None):
        query_str = str(query)
        if "FROM VendorScreeningCache" in query_str:
            return mock_summary
        elif "FROM Vendor" in query_str:
            return mock_vendors
        elif "UserRole" in query_str:
            mock_role = MagicMock()
            mock_role.fetchone.return_value = ("analyst", "Analyst User")
            return mock_role
        return MagicMock()
        
    mock_db_session.execute.side_effect = mock_execute
    
    # 1. /vendors
    response = client.get(
        "/vendors",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    vendors_data = response.json()
    assert len(vendors_data) == 1
    assert vendors_data[0]["vendor_id"] == "V1"
    
    # 2. /vendors/screening-summary
    response = client.get(
        "/vendors/screening-summary",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    summary_data = response.json()
    assert summary_data["total_screened"] == 5
    assert summary_data["flagged_sanctions"] == 1
