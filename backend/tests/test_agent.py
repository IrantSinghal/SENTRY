import os
os.environ["DATABASE_URL"] = "postgresql://mock_user:mock_pass@localhost:5432/mock_db"
os.environ["GEMINI_API_KEY"] = "mock_api_key"

import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
import pytest

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import (
    PurchaseRequisitionSchema,
    PurchaseRequisitionItemSchema,
    PriceAnomalySignal,
    VendorRiskSignal,
    DuplicateSignal,
    PolicyComplianceSignal,
    TriageResultSchema,
    TriageSignals
)
from app.agent import (
    intake_node,
    price_anomaly_node,
    vendor_risk_node,
    duplicate_detection_node,
    policy_compliance_node,
    decision_gate_node,
    synthesis_node,
    get_mock_synthesis_response
)

# --- Sample Data Fixtures ---

@pytest.fixture
def sample_raw_payload():
    return {
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
    }

@pytest.fixture
def sample_requisition(sample_raw_payload):
    return PurchaseRequisitionSchema.model_validate(sample_raw_payload)


# --- Node Tests ---

def test_intake_node(sample_raw_payload):
    state = {"raw_payload": sample_raw_payload}
    result = intake_node(state)
    assert result["requisition"] is not None
    assert result["requisition"].purchase_requisition_id == "REQ_TEST_001"
    assert len(result["requisition"].items) == 1
    assert result["requisition"].items[0].material == "MAT_LAPTOP_001"


def test_price_anomaly_node_no_deviation(sample_requisition):
    db_mock = MagicMock()
    # Mock database to return 1200.0 as historical average (net price is 1200.0, so 0% deviation)
    db_mock.execute.return_value.fetchone.return_value = (1200.0,)

    state = {"requisition": sample_requisition}
    result = price_anomaly_node(state, db=db_mock)
    
    assert "price_anomaly" in result
    signal: PriceAnomalySignal = result["price_anomaly"]
    assert signal.has_anomaly is False
    assert len(signal.details) == 1
    assert signal.details[0].deviation_percentage == 0.0


def test_price_anomaly_node_with_deviation(sample_requisition):
    # Change net price to 1500.0 (deviation = 25% vs 1200.0 average)
    sample_requisition.items[0].net_price_amount = 1500.0
    
    db_mock = MagicMock()
    db_mock.execute.return_value.fetchone.return_value = (1200.0,)

    state = {"requisition": sample_requisition}
    result = price_anomaly_node(state, db=db_mock)
    
    signal: PriceAnomalySignal = result["price_anomaly"]
    assert signal.has_anomaly is True
    assert signal.details[0].deviation_percentage == 0.25


def test_vendor_risk_node_new_vendor(sample_requisition):
    from datetime import datetime, timezone
    db_mock = MagicMock()
    
    mock_vendor_info = MagicMock()
    mock_vendor_info.fetchone.return_value = (
        "Apex Tech Solutions",
        date.today() - timedelta(days=10),
        [],
        date.today() + timedelta(days=365),
        "TAX-12345",
        "123 Street"
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
        "Verified", 
        datetime.now(timezone.utc)
    )
    
    db_mock.execute.side_effect = [
        mock_vendor_info,
        mock_ph_count,
        mock_cache
    ]

    state = {"requisition": sample_requisition}
    result = vendor_risk_node(state, db=db_mock)
    
    signal: VendorRiskSignal = result["vendor_risk"]
    assert signal.is_risky is True
    assert any("is new" in reason for reason in signal.reasons)


def test_vendor_risk_node_compliance_flags(sample_requisition):
    from datetime import datetime, timezone
    db_mock = MagicMock()
    
    mock_vendor_info = MagicMock()
    mock_vendor_info.fetchone.return_value = (
        "Global Office Supplies",
        date.today() - timedelta(days=730),
        ["late_delivery_history"],
        date.today() + timedelta(days=365),
        "TAX-12345",
        "123 Street"
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
        "Verified", 
        datetime.now(timezone.utc)
    )
    
    db_mock.execute.side_effect = [
        mock_vendor_info,
        mock_ph_count,
        mock_cache
    ]

    state = {"requisition": sample_requisition}
    result = vendor_risk_node(state, db=db_mock)
    
    signal: VendorRiskSignal = result["vendor_risk"]
    assert signal.is_risky is True
    assert any("compliance flags" in reason for reason in signal.reasons)


def test_duplicate_detection_node(sample_requisition):
    db_mock = MagicMock()
    # Mock other items query to return another open requisition item with the same material in a different purchasing group
    db_mock.execute.return_value.fetchall.return_value = [
        ("REQ_DUP_002", date.today() - timedelta(days=5), "P02", "00010", "MAT_LAPTOP_001")
    ]

    state = {"requisition": sample_requisition}
    result = duplicate_detection_node(state, db=db_mock)
    
    signal: DuplicateSignal = result["duplicate_detection"]
    assert signal.is_duplicate is True
    assert len(signal.details) == 1
    assert signal.details[0].matching_requisition_id == "REQ_DUP_002"
    assert signal.details[0].match_type == "exact"


def test_policy_compliance_node_value_ceiling(sample_requisition):
    # Set total value to 6000.0 (exceeds default 5000.0)
    sample_requisition.items[0].net_price_amount = 3000.0
    sample_requisition.items[0].order_quantity = 2
    
    db_mock = MagicMock()

    state = {"requisition": sample_requisition}
    result = policy_compliance_node(state, db=db_mock)
    
    signal: PolicyComplianceSignal = result["policy_compliance"]
    assert signal.violates_policy is True
    assert any("exceeds auto-approval ceiling" in reason for reason in signal.reasons)


def test_policy_compliance_node_hard_block_banned_material(sample_requisition):
    # Change material name to contain 'BANNED'
    sample_requisition.items[0].material = "MAT_BANNED_DRONES"
    
    db_mock = MagicMock()

    state = {"requisition": sample_requisition}
    result = policy_compliance_node(state, db=db_mock)
    
    signal: PolicyComplianceSignal = result["policy_compliance"]
    assert signal.violates_policy is True
    assert signal.has_hard_block is True
    assert any("contains restricted material" in reason for reason in signal.reasons)


def test_decision_gate_node_auto_approve(sample_requisition):
    # Set up clean signals
    price_sig = PriceAnomalySignal(has_anomaly=False)
    vendor_sig = VendorRiskSignal(is_risky=False)
    dup_sig = DuplicateSignal(is_duplicate=False)
    policy_sig = PolicyComplianceSignal(violates_policy=False, has_hard_block=False)
    
    triage_res = get_mock_synthesis_response(sample_requisition, price_sig, vendor_sig, dup_sig, policy_sig)
    
    state = {
        "requisition": sample_requisition,
        "price_anomaly": price_sig,
        "vendor_risk": vendor_sig,
        "duplicate_detection": dup_sig,
        "policy_compliance": policy_sig,
        "triage_result": triage_res
    }
    
    result = decision_gate_node(state)
    assert result["triage_result"].verdict == "auto_approve"


def test_decision_gate_node_escalate(sample_requisition):
    # Price anomaly triggered on Item 00010
    from app.models import PriceAnomalyItem
    price_sig = PriceAnomalySignal(
        has_anomaly=True,
        details=[
            PriceAnomalyItem(
                purchase_requisition_item="00010",
                material="MAT_LAPTOP_001",
                vendor_id="VEND001",
                current_price=1500.0,
                historical_avg_price=1200.0,
                deviation_percentage=0.25,
                is_anomaly=True
            )
        ]
    )
    vendor_sig = VendorRiskSignal(is_risky=False)
    dup_sig = DuplicateSignal(is_duplicate=False)
    policy_sig = PolicyComplianceSignal(violates_policy=False, has_hard_block=False)
    
    # We pass 'auto_approve' as the LLM's faulty verdict suggestion, and decision gate should override it to 'escalate'
    triage_res = get_mock_synthesis_response(sample_requisition, price_sig, vendor_sig, dup_sig, policy_sig)
    triage_res.verdict = "auto_approve"
    
    state = {
        "requisition": sample_requisition,
        "price_anomaly": price_sig,
        "vendor_risk": vendor_sig,
        "duplicate_detection": dup_sig,
        "policy_compliance": policy_sig,
        "triage_result": triage_res
    }
    
    result = decision_gate_node(state)
    assert result["triage_result"].verdict == "escalate"


def test_decision_gate_node_reject(sample_requisition):
    # Hard policy block triggered
    price_sig = PriceAnomalySignal(has_anomaly=False)
    vendor_sig = VendorRiskSignal(is_risky=False)
    dup_sig = DuplicateSignal(is_duplicate=False)
    
    # Set the item's material name to trigger the policy compliance node hard block logic
    sample_requisition.items[0].material = "MAT_BANNED_DRONES"
    policy_sig = PolicyComplianceSignal(
        violates_policy=True,
        has_hard_block=True,
        reasons=["Item 00010 contains restricted material: 'MAT_BANNED_DRONES'."]
    )
    
    triage_res = get_mock_synthesis_response(sample_requisition, price_sig, vendor_sig, dup_sig, policy_sig)
    
    state = {
        "requisition": sample_requisition,
        "price_anomaly": price_sig,
        "vendor_risk": vendor_sig,
        "duplicate_detection": dup_sig,
        "policy_compliance": policy_sig,
        "triage_result": triage_res
    }
    
    result = decision_gate_node(state)
    assert result["triage_result"].verdict == "reject"
