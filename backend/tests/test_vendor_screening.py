import os
import sys
from datetime import datetime, date, timedelta, timezone
from unittest.mock import MagicMock, patch
import pytest

# Ensure GEMINI_API_KEY is empty/mocked for deterministic testing
os.environ["GEMINI_API_KEY"] = ""
os.environ["SANCTIONS_MATCH_THRESHOLD"] = "80"

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import (
    PurchaseRequisitionSchema,
    VendorRiskDetails,
    VendorRiskSignal
)
from app.agent import (
    run_tier2_screening,
    vendor_risk_node
)
import app.agent
app.agent.SANCTIONS_MATCH_THRESHOLD = 80.0


@pytest.fixture
def sample_requisition():
    return PurchaseRequisitionSchema.model_validate({
        "purchase_requisition_id": "REQ_TEST_001",
        "purchasing_group": "P01",
        "created_by_user": "TESTUSER",
        "requisition_date": str(date.today()),
        "items": [
            {
                "purchase_requisition_id": "REQ_TEST_001",
                "purchase_requisition_item": "00010",
                "material": "MAT_LAPTOP_001",
                "vendor_id": "VEND001",
                "order_quantity": 2,
                "net_price_amount": 1200.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            }
        ]
    })


@patch("urllib.request.urlopen")
def test_run_tier2_screening_fuzzy_sanctions_match(mock_urlopen, sample_requisition):
    db_mock = MagicMock()
    
    mock_query_result = MagicMock()
    mock_query_result.fetchall.return_value = [("ACME CORP GROUP INC", "OFAC"), ("OTHER BANNED CO", "EU")]
    
    db_mock.execute.side_effect = [
        # First call: SELECT listed_name, list_source FROM SanctionsList
        mock_query_result,
        # Second call: INSERT INTO VendorScreeningCache (upsert)
        MagicMock()
    ]
    
    # Mock OpenCorporates HTTP call response to return no results
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"results": {"companies": []}}'
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    # Run screening with Acme Corp
    res = run_tier2_screening("VEND001", "Acme Corp Group", db_mock)
    
    # Assert fuzzy match was triggered (Acme Corp Group vs ACME CORP GROUP INC should score very high, > 80)
    assert res["sanctions_match"] is True
    assert "Fuzzy match" in res["sanctions_match_detail"]
    assert "OFAC" in res["sanctions_match_detail"]
    
    # Assert registry verification returned false (no results)
    assert res["registry_verified"] is False
    assert "No matching entity" in res["registry_detail"]


@patch("urllib.request.urlopen")
def test_run_tier2_screening_api_failure_graceful_degradation(mock_urlopen):
    db_mock = MagicMock()
    
    mock_query_result = MagicMock()
    mock_query_result.fetchall.return_value = []
    
    db_mock.execute.side_effect = [
        # Sanctions List query returning empty list
        mock_query_result,
        # Cache upsert query
        MagicMock()
    ]
    
    # Mock OpenCorporates HTTP call response to raise exception
    mock_urlopen.side_effect = Exception("API Server Timeout")

    # Run screening
    res = run_tier2_screening("VEND001", "Acme Corp", db_mock)
    
    # Assert sanctions is clear
    assert res["sanctions_match"] is False
    
    # Assert registry_verified is None (graceful warning, did not crash)
    assert res["registry_verified"] is None
    assert "failed" in res["registry_detail"]


def test_vendor_risk_node_uses_non_stale_cache(sample_requisition):
    db_mock = MagicMock()
    
    # Mock db.execute calls in vendor_risk_node
    mock_vendor_info = MagicMock()
    mock_vendor_info.fetchone.return_value = (
        "Apex Solutions", 
        date.today() - timedelta(days=200),  # Not a new vendor (> 90 days)
        [], # compliance flags
        date.today() + timedelta(days=200),  # contract expiry date (> 30 days)
        "TAX-12345", # tax_id
        "123 Office Park" # address
    )
    
    mock_ph_count = MagicMock()
    mock_ph_count.scalar.return_value = 5 # ph_count = 5 (has price history)
    
    mock_cache = MagicMock()
    mock_cache.fetchone.return_value = (
        False, # sanctions_match
        "Clear", # sanctions_match_detail
        False, # adverse_media_flagged
        '{"evidence": [], "sources": []}', # adverse_media_evidence
        True, # registry_verified
        "Verified registered", # registry_detail
        datetime.now(timezone.utc) - timedelta(days=5) # checked_at (5 days ago, not stale)
    )
    
    db_mock.execute.side_effect = [
        # 1. Fetch vendor basic data
        mock_vendor_info,
        # 2. Check PriceHistory presence
        mock_ph_count,
        # 3. Check VendorScreeningCache
        mock_cache
    ]
    
    # Patch run_tier2_screening to verify it is NOT called
    with patch("app.agent.run_tier2_screening") as mock_screening:
        state = {"requisition": sample_requisition}
        result = vendor_risk_node(state, db=db_mock)
        
        # Verify screening was NOT called
        mock_screening.assert_not_called()
        
        # Verify the vendor risk node outcome
        signal: VendorRiskSignal = result["vendor_risk"]
        assert signal.is_risky is False
        assert len(signal.details) == 1
        assert signal.details[0].sanctions_match is False
        assert signal.details[0].registry_verified is True


def test_vendor_risk_node_stale_cache_triggers_refresh(sample_requisition):
    db_mock = MagicMock()
    
    # Mock db.execute calls in vendor_risk_node
    mock_vendor_info = MagicMock()
    mock_vendor_info.fetchone.return_value = (
        "Apex Solutions", 
        date.today() - timedelta(days=200),  
        [], 
        date.today() + timedelta(days=200),  
        "TAX-12345", 
        "123 Office Park" 
    )
    
    mock_ph_count = MagicMock()
    mock_ph_count.scalar.return_value = 5
    
    mock_cache = MagicMock()
    mock_cache.fetchone.return_value = (
        False, 
        "Clear", 
        False, 
        '{"evidence": [], "sources": []}', 
        True, 
        "Verified registered", 
        datetime.now(timezone.utc) - timedelta(days=40) 
    )
    
    db_mock.execute.side_effect = [
        # 1. Fetch vendor basic data
        mock_vendor_info,
        # 2. Check PriceHistory presence
        mock_ph_count,
        # 3. Check VendorScreeningCache (returns checked_at 40 days ago, which is > 30 days default staleness)
        mock_cache
    ]
    
    # Patch run_tier2_screening to return refreshed screening results
    refreshed_time = datetime.now(timezone.utc)
    with patch("app.agent.run_tier2_screening_in_new_session") as mock_screening:
        mock_screening.return_value = {
            "sanctions_match": False,
            "sanctions_match_detail": "Refreshed and clear",
            "adverse_media_flagged": False,
            "adverse_media_evidence": {"evidence": [], "sources": []},
            "registry_verified": True,
            "registry_detail": "Refreshed verification",
            "checked_at": refreshed_time
        }
        
        state = {"requisition": sample_requisition}
        result = vendor_risk_node(state, db=db_mock)
        
        # Verify run_tier2_screening_in_new_session WAS called due to cache staleness
        mock_screening.assert_called_once_with("VEND001", "Apex Solutions")
        
        # Verify the vendor risk node contains refreshed values
        signal: VendorRiskSignal = result["vendor_risk"]
        assert len(signal.details) == 1
        assert signal.details[0].sanctions_match_detail == "Refreshed and clear"
        assert signal.details[0].registry_detail == "Refreshed verification"
        assert signal.details[0].checked_at == refreshed_time
