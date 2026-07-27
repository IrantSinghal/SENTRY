import os
os.environ["DATABASE_URL"] = "postgresql://mock_user:mock_pass@localhost:5432/mock_db"
os.environ["GEMINI_API_KEY"] = "mock_api_key"

import sys
from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import (
    PurchaseRequisitionSchema,
    PurchaseRequisitionItemSchema,
    PriceAnomalySignal,
    PriceAnomalyItem,
    VendorRiskSignal,
    DuplicateSignal,
    PolicyComplianceSignal,
    TriageResultSchema,
    TriageSignals
)
from app.agent import (
    intra_pr_material_overlap_node,
    vendor_risk_node,
    decision_gate_node,
    get_mock_synthesis_response,
    compute_itemized_results
)


def test_intra_pr_material_overlap_detected():
    """Test that items with the same material from different vendors trigger an overlap flag."""
    payload = {
        "purchase_requisition_id": "REQ_OVERLAP",
        "purchasing_group": "P01",
        "created_by_user": "TESTUSER",
        "requisition_date": str(date.today()),
        "items": [
            {
                "purchase_requisition_id": "REQ_OVERLAP",
                "purchase_requisition_item": "00010",
                "material": "MAT_LAPTOP_001",
                "vendor_id": "VEND001",
                "order_quantity": 1,
                "net_price_amount": 1000.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            },
            {
                "purchase_requisition_id": "REQ_OVERLAP",
                "purchase_requisition_item": "00020",
                "material": "MAT_LAPTOP_001",
                "vendor_id": "VEND002",
                "order_quantity": 1,
                "net_price_amount": 950.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            }
        ]
    }
    requisition = PurchaseRequisitionSchema.model_validate(payload)
    state = {"requisition": requisition}
    
    result = intra_pr_material_overlap_node(state)
    assert result["intra_pr_material_overlap"] is not None
    assert len(result["intra_pr_material_overlap"]) == 1
    
    overlap = result["intra_pr_material_overlap"][0]
    assert overlap["material"] == "MAT_LAPTOP_001"
    assert set(overlap["vendor_ids"]) == {"VEND001", "VEND002"}
    assert set(overlap["item_ids"]) == {"00010", "00020"}


def test_intra_pr_material_overlap_clear_different_materials():
    """Test that different materials from different vendors do not trigger overlap."""
    payload = {
        "purchase_requisition_id": "REQ_CLEAR",
        "purchasing_group": "P01",
        "created_by_user": "TESTUSER",
        "requisition_date": str(date.today()),
        "items": [
            {
                "purchase_requisition_id": "REQ_CLEAR",
                "purchase_requisition_item": "00010",
                "material": "MAT_LAPTOP_001",
                "vendor_id": "VEND001",
                "order_quantity": 1,
                "net_price_amount": 1000.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            },
            {
                "purchase_requisition_id": "REQ_CLEAR",
                "purchase_requisition_item": "00020",
                "material": "MAT_DESK_003",
                "vendor_id": "VEND002",
                "order_quantity": 1,
                "net_price_amount": 500.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            }
        ]
    }
    requisition = PurchaseRequisitionSchema.model_validate(payload)
    state = {"requisition": requisition}
    
    result = intra_pr_material_overlap_node(state)
    assert result["intra_pr_material_overlap"] is None


def test_intra_pr_material_overlap_clear_same_vendor():
    """Test that same materials from the same vendor do not trigger overlap."""
    payload = {
        "purchase_requisition_id": "REQ_SAME_VEND",
        "purchasing_group": "P01",
        "created_by_user": "TESTUSER",
        "requisition_date": str(date.today()),
        "items": [
            {
                "purchase_requisition_id": "REQ_SAME_VEND",
                "purchase_requisition_item": "00010",
                "material": "MAT_LAPTOP_001",
                "vendor_id": "VEND001",
                "order_quantity": 1,
                "net_price_amount": 1000.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            },
            {
                "purchase_requisition_id": "REQ_SAME_VEND",
                "purchase_requisition_item": "00020",
                "material": "MAT_LAPTOP_001",
                "vendor_id": "VEND001",
                "order_quantity": 2,
                "net_price_amount": 1000.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            }
        ]
    }
    requisition = PurchaseRequisitionSchema.model_validate(payload)
    state = {"requisition": requisition}
    
    result = intra_pr_material_overlap_node(state)
    assert result["intra_pr_material_overlap"] is None


@patch("app.agent.run_tier2_screening_in_new_session")
def test_vendor_risk_node_deduplication(mock_screening_run):
    """Test that vendor lookup is deduplicated if a PR has multiple items from the same vendor."""
    payload = {
        "purchase_requisition_id": "REQ_DEDUP",
        "purchasing_group": "P01",
        "created_by_user": "TESTUSER",
        "requisition_date": str(date.today()),
        "items": [
            {
                "purchase_requisition_id": "REQ_DEDUP",
                "purchase_requisition_item": "00010",
                "material": "MAT_LAPTOP_001",
                "vendor_id": "VEND_DUPLICATED",
                "order_quantity": 1,
                "net_price_amount": 1000.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            },
            {
                "purchase_requisition_id": "REQ_DEDUP",
                "purchase_requisition_item": "00020",
                "material": "MAT_DESK_003",
                "vendor_id": "VEND_DUPLICATED",
                "order_quantity": 2,
                "net_price_amount": 500.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            }
        ]
    }
    requisition = PurchaseRequisitionSchema.model_validate(payload)
    db_mock = MagicMock()
    
    # Mock return values for vendor data lookup
    mock_vendor_info = MagicMock()
    mock_vendor_info.fetchone.return_value = (
        "Duplicated Vendor Name",
        date.today() - timedelta(days=730),
        [],
        date.today() + timedelta(days=365),
        "TAX-777",
        "777 Street"
    )
    
    mock_ph_count = MagicMock()
    mock_ph_count.scalar.return_value = 10
    
    mock_cache = MagicMock()
    mock_cache.fetchone.return_value = None
    
    db_mock.execute.side_effect = [
        mock_vendor_info,
        mock_ph_count,
        mock_cache
    ]

    mock_screening_run.return_value = {
        "sanctions_match": False,
        "sanctions_match_detail": None,
        "adverse_media_flagged": False,
        "adverse_media_evidence": {"evidence": [], "sources": []},
        "registry_verified": True,
        "registry_detail": "Verified",
        "checked_at": datetime.now(timezone.utc)
    }

    state = {"requisition": requisition}
    result = vendor_risk_node(state, db=db_mock)
    
    # Assert that screening task was triggered exactly once, despite 2 items with that vendor
    mock_screening_run.assert_called_once_with("VEND_DUPLICATED", "Duplicated Vendor Name")
    
    signal = result["vendor_risk"]
    assert signal.is_risky is False
    assert len(signal.details) == 1
    assert signal.details[0].vendor_id == "VEND_DUPLICATED"


def test_decision_gate_node_worst_case_wins_reject():
    """Test that decision gate aggregates to 'reject' if any item is rejected."""
    payload = {
        "purchase_requisition_id": "REQ_W_REJECT",
        "purchasing_group": "P01",
        "created_by_user": "TESTUSER",
        "requisition_date": str(date.today()),
        "items": [
            {
                "purchase_requisition_id": "REQ_W_REJECT",
                "purchase_requisition_item": "00010",
                "material": "MAT_LAPTOP_001",
                "vendor_id": "VEND001",
                "order_quantity": 1,
                "net_price_amount": 1000.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            },
            {
                "purchase_requisition_id": "REQ_W_REJECT",
                "purchase_requisition_item": "00020",
                "material": "MAT_BANNED_ITEM", # Banned triggers reject
                "vendor_id": "VEND002",
                "order_quantity": 1,
                "net_price_amount": 200.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            }
        ]
    }
    requisition = PurchaseRequisitionSchema.model_validate(payload)
    
    price_sig = PriceAnomalySignal(has_anomaly=False)
    vendor_sig = VendorRiskSignal(is_risky=False)
    dup_sig = DuplicateSignal(is_duplicate=False)
    policy_sig = PolicyComplianceSignal(violates_policy=True, has_hard_block=True, reasons=["Item 00020 contains restricted material: 'MAT_BANNED_ITEM'."])
    
    triage_res = get_mock_synthesis_response(requisition, price_sig, vendor_sig, dup_sig, policy_sig)
    
    state = {
        "requisition": requisition,
        "price_anomaly": price_sig,
        "vendor_risk": vendor_sig,
        "duplicate_detection": dup_sig,
        "policy_compliance": policy_sig,
        "intra_pr_material_overlap": None,
        "triage_result": triage_res
    }
    
    result = decision_gate_node(state)
    assert result["triage_result"].verdict == "reject"
    # Rejection requires CFO named authority
    assert result["triage_result"].required_approver_role == "cfo"
    assert result["triage_result"].requires_named_authority is True


def test_decision_gate_node_worst_case_wins_escalate():
    """Test that decision gate aggregates to 'escalate' if one item triggers escalate and none reject."""
    payload = {
        "purchase_requisition_id": "REQ_W_ESCALATE",
        "purchasing_group": "P01",
        "created_by_user": "TESTUSER",
        "requisition_date": str(date.today()),
        "items": [
            {
                "purchase_requisition_id": "REQ_W_ESCALATE",
                "purchase_requisition_item": "00010",
                "material": "MAT_LAPTOP_001",
                "vendor_id": "VEND001",
                "order_quantity": 1,
                "net_price_amount": 1000.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            },
            {
                "purchase_requisition_id": "REQ_W_ESCALATE",
                "purchase_requisition_item": "00020",
                "material": "MAT_DESK_003",
                "vendor_id": "VEND003",
                "order_quantity": 1,
                "net_price_amount": 1500.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            }
        ]
    }
    requisition = PurchaseRequisitionSchema.model_validate(payload)
    
    # Mock a price anomaly on Item 00020
    from app.models import PriceAnomalyItem
    price_sig = PriceAnomalySignal(has_anomaly=True, details=[
        PriceAnomalyItem(
            purchase_requisition_item="00020",
            material="MAT_DESK_003",
            vendor_id="VEND003",
            current_price=1500.0,
            historical_avg_price=1200.0,
            deviation_percentage=0.25,
            is_anomaly=True
        )
    ])
    vendor_sig = VendorRiskSignal(is_risky=False)
    dup_sig = DuplicateSignal(is_duplicate=False)
    policy_sig = PolicyComplianceSignal(violates_policy=False, has_hard_block=False)
    
    triage_res = get_mock_synthesis_response(requisition, price_sig, vendor_sig, dup_sig, policy_sig)
    
    state = {
        "requisition": requisition,
        "price_anomaly": price_sig,
        "vendor_risk": vendor_sig,
        "duplicate_detection": dup_sig,
        "policy_compliance": policy_sig,
        "intra_pr_material_overlap": None,
        "triage_result": triage_res
    }
    
    result = decision_gate_node(state)
    assert result["triage_result"].verdict == "escalate"
    assert result["triage_result"].required_approver_role == "approver"
    assert result["triage_result"].requires_named_authority is False


def test_decision_gate_node_intra_pr_overlap_escalation():
    """Test that decision gate forces 'escalate' and requires named authority if there is an intra-PR overlap."""
    payload = {
        "purchase_requisition_id": "REQ_OVERLAP_DG",
        "purchasing_group": "P01",
        "created_by_user": "TESTUSER",
        "requisition_date": str(date.today()),
        "items": [
            {
                "purchase_requisition_id": "REQ_OVERLAP_DG",
                "purchase_requisition_item": "00010",
                "material": "MAT_LAPTOP_001",
                "vendor_id": "VEND001",
                "order_quantity": 1,
                "net_price_amount": 1000.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            },
            {
                "purchase_requisition_id": "REQ_OVERLAP_DG",
                "purchase_requisition_item": "00020",
                "material": "MAT_LAPTOP_001",
                "vendor_id": "VEND002",
                "order_quantity": 1,
                "net_price_amount": 1000.0,
                "purchasing_organization": "1000",
                "account_assignment_category": "K"
            }
        ]
    }
    requisition = PurchaseRequisitionSchema.model_validate(payload)
    
    price_sig = PriceAnomalySignal(has_anomaly=False)
    vendor_sig = VendorRiskSignal(is_risky=False)
    dup_sig = DuplicateSignal(is_duplicate=False)
    policy_sig = PolicyComplianceSignal(violates_policy=False, has_hard_block=False)
    
    overlap_data = [{
        "material": "MAT_LAPTOP_001",
        "item_ids": ["00010", "00020"],
        "vendor_ids": ["VEND001", "VEND002"]
    }]
    
    triage_res = get_mock_synthesis_response(requisition, price_sig, vendor_sig, dup_sig, policy_sig, intra_pr_overlap=overlap_data)
    
    state = {
        "requisition": requisition,
        "price_anomaly": price_sig,
        "vendor_risk": vendor_sig,
        "duplicate_detection": dup_sig,
        "policy_compliance": policy_sig,
        "intra_pr_material_overlap": overlap_data,
        "triage_result": triage_res
    }
    
    result = decision_gate_node(state)
    assert result["triage_result"].verdict == "escalate"
    # Overlap escalates to standard approver level
    assert result["triage_result"].required_approver_role == "approver"


def test_aggregation_worst_case_combinations():
    """Unit test the aggregation function directly with various combinations."""
    # Test combination: Clean + Escalate
    payload = {
        "purchase_requisition_id": "REQ_COMB_1",
        "purchasing_group": "P01",
        "created_by_user": "TESTUSER",
        "requisition_date": str(date.today()),
        "items": [
            {
                "purchase_requisition_id": "REQ_COMB_1",
                "purchase_requisition_item": "00010",
                "material": "MAT_1",
                "vendor_id": "V1",
                "order_quantity": 1,
                "net_price_amount": 100.0,
                "purchasing_organization": "1000"
            },
            {
                "purchase_requisition_id": "REQ_COMB_1",
                "purchase_requisition_item": "00020",
                "material": "MAT_2",
                "vendor_id": "V2",
                "order_quantity": 1,
                "net_price_amount": 20000.0, # Value > 15000 -> VP Named Auth
                "purchasing_organization": "1000"
            }
        ]
    }
    requisition = PurchaseRequisitionSchema.model_validate(payload)
    price_sig = PriceAnomalySignal(has_anomaly=True, details=[
        PriceAnomalyItem(
            purchase_requisition_item="00020",
            material="MAT_2",
            vendor_id="V2",
            current_price=20000.0,
            historical_avg_price=10000.0,
            deviation_percentage=1.0,
            is_anomaly=True
        )
    ])
    vendor_sig = VendorRiskSignal(is_risky=False)
    dup_sig = DuplicateSignal(is_duplicate=False)
    policy_sig = PolicyComplianceSignal(violates_policy=False, has_hard_block=False)
    
    triage_res = get_mock_synthesis_response(requisition, price_sig, vendor_sig, dup_sig, policy_sig)
    state = {
        "requisition": requisition,
        "price_anomaly": price_sig,
        "vendor_risk": vendor_sig,
        "duplicate_detection": dup_sig,
        "policy_compliance": policy_sig,
        "intra_pr_material_overlap": None,
        "triage_result": triage_res
    }
    result = decision_gate_node(state)
    assert result["triage_result"].verdict == "escalate"
    assert result["triage_result"].required_approver_role == "vp"
    assert result["triage_result"].requires_named_authority is True


@patch("app.agent.run_tier2_screening_in_new_session")
def test_vendor_risk_node_five_items_two_vendors(mock_screening_run):
    """Test that a 5-item PR referencing only 2 distinct vendors triggers exactly 2 screening calls."""
    payload = {
        "purchase_requisition_id": "REQ_5_ITEMS",
        "purchasing_group": "P01",
        "created_by_user": "TESTUSER",
        "requisition_date": str(date.today()),
        "items": [
            {"purchase_requisition_id": "REQ_5_ITEMS", "purchase_requisition_item": "00010", "material": "M1", "vendor_id": "V1", "order_quantity": 1, "net_price_amount": 10.0, "purchasing_organization": "1000"},
            {"purchase_requisition_id": "REQ_5_ITEMS", "purchase_requisition_item": "00020", "material": "M2", "vendor_id": "V2", "order_quantity": 1, "net_price_amount": 10.0, "purchasing_organization": "1000"},
            {"purchase_requisition_id": "REQ_5_ITEMS", "purchase_requisition_item": "00030", "material": "M3", "vendor_id": "V1", "order_quantity": 1, "net_price_amount": 10.0, "purchasing_organization": "1000"},
            {"purchase_requisition_id": "REQ_5_ITEMS", "purchase_requisition_item": "00040", "material": "M4", "vendor_id": "V2", "order_quantity": 1, "net_price_amount": 10.0, "purchasing_organization": "1000"},
            {"purchase_requisition_id": "REQ_5_ITEMS", "purchase_requisition_item": "00050", "material": "M5", "vendor_id": "V1", "order_quantity": 1, "net_price_amount": 10.0, "purchasing_organization": "1000"}
        ]
    }
    requisition = PurchaseRequisitionSchema.model_validate(payload)
    db_mock = MagicMock()
    
    # Mock return values for vendor data lookup
    def db_execute_mock(query, params=None):
        m = MagicMock()
        if "FROM VendorScreeningCache" in str(query):
            m.fetchone.return_value = None
        elif "FROM Vendor" in str(query):
            v_id = params["vendor_id"]
            m.fetchone.return_value = (
                f"Vendor Name {v_id}",
                date.today() - timedelta(days=730),
                [],
                date.today() + timedelta(days=365),
                "TAX",
                "Address"
            )
        elif "FROM PriceHistory" in str(query) or "COUNT" in str(query):
            m.scalar.return_value = 1
        return m
        
    db_mock.execute.side_effect = db_execute_mock

    mock_screening_run.return_value = {
        "sanctions_match": False,
        "sanctions_match_detail": None,
        "adverse_media_flagged": False,
        "adverse_media_evidence": {"evidence": [], "sources": []},
        "registry_verified": True,
        "registry_detail": "Verified",
        "checked_at": datetime.now(timezone.utc)
    }

    state = {"requisition": requisition}
    result = vendor_risk_node(state, db=db_mock)
    
    # Assert that screening task was triggered exactly twice
    assert mock_screening_run.call_count == 2
    called_vendors = {call[0][0] for call in mock_screening_run.call_args_list}
    assert called_vendors == {"V1", "V2"}


def test_same_vendor_consistency_guarantee():
    """Verify that items sharing a vendor_id point to the exact same vendor risk signal dictionary object."""
    payload = {
        "purchase_requisition_id": "REQ_CONSISTENCY",
        "purchasing_group": "P01",
        "created_by_user": "TESTUSER",
        "requisition_date": str(date.today()),
        "items": [
            {"purchase_requisition_id": "REQ_CONSISTENCY", "purchase_requisition_item": "00010", "material": "M1", "vendor_id": "V1", "order_quantity": 1, "net_price_amount": 100.0, "purchasing_organization": "1000"},
            {"purchase_requisition_id": "REQ_CONSISTENCY", "purchase_requisition_item": "00020", "material": "M2", "vendor_id": "V1", "order_quantity": 2, "net_price_amount": 200.0, "purchasing_organization": "1000"}
        ]
    }
    requisition = PurchaseRequisitionSchema.model_validate(payload)
    
    price_sig = PriceAnomalySignal(has_anomaly=False)
    from app.models import VendorRiskDetails
    vendor_detail = VendorRiskDetails(
        vendor_id="V1",
        vendor_name="Vendor 1",
        onboarded_days_ago=10,
        compliance_flags=[],
        contract_expires_days=100,
        is_new_vendor=True,
        has_compliance_flags=False,
        is_contract_expiring=False,
        incomplete_vendor_data=False,
        no_price_history=False,
        sanctions_match=False,
        adverse_media_flagged=False,
        registry_verified=True
    )
    vendor_sig = VendorRiskSignal(is_risky=True, details=[vendor_detail], reasons=["Vendor V1 is new."])
    dup_sig = DuplicateSignal(is_duplicate=False)
    policy_sig = PolicyComplianceSignal(violates_policy=False, has_hard_block=False)
    
    item_results = compute_itemized_results(requisition, price_sig, vendor_sig, dup_sig, policy_sig)
    
    assert len(item_results) == 2
    # Ensure they share the exact same vendor_risk dictionary object
    assert item_results[0]["signals"]["vendor_risk"] is item_results[1]["signals"]["vendor_risk"]


@patch("app.agent.run_tier2_screening_in_new_session")
def test_vendor_screening_concurrency(mock_screening_run):
    """Test that multiple vendor screenings run concurrently, taking close to a single call delay."""
    payload = {
        "purchase_requisition_id": "REQ_CONCURRENT",
        "purchasing_group": "P01",
        "created_by_user": "TESTUSER",
        "requisition_date": str(date.today()),
        "items": [
            {"purchase_requisition_id": "REQ_CONCURRENT", "purchase_requisition_item": "00010", "material": "M1", "vendor_id": "V1", "order_quantity": 1, "net_price_amount": 10.0, "purchasing_organization": "1000"},
            {"purchase_requisition_id": "REQ_CONCURRENT", "purchase_requisition_item": "00020", "material": "M2", "vendor_id": "V2", "order_quantity": 1, "net_price_amount": 10.0, "purchasing_organization": "1000"},
            {"purchase_requisition_id": "REQ_CONCURRENT", "purchase_requisition_item": "00030", "material": "M3", "vendor_id": "V3", "order_quantity": 1, "net_price_amount": 10.0, "purchasing_organization": "1000"}
        ]
    }
    requisition = PurchaseRequisitionSchema.model_validate(payload)
    db_mock = MagicMock()
    
    def db_execute_mock(query, params=None):
        m = MagicMock()
        if "FROM VendorScreeningCache" in str(query):
            m.fetchone.return_value = None
        elif "FROM Vendor" in str(query):
            v_id = params["vendor_id"]
            m.fetchone.return_value = (
                f"Vendor Name {v_id}",
                date.today() - timedelta(days=730),
                [],
                date.today() + timedelta(days=365),
                "TAX",
                "Address"
            )
        elif "FROM PriceHistory" in str(query) or "COUNT" in str(query):
            m.scalar.return_value = 1
        return m
        
    db_mock.execute.side_effect = db_execute_mock

    import time
    def screening_side_effect(*args, **kwargs):
        time.sleep(0.4)
        return {
            "sanctions_match": False,
            "sanctions_match_detail": None,
            "adverse_media_flagged": False,
            "adverse_media_evidence": {"evidence": [], "sources": []},
            "registry_verified": True,
            "registry_detail": "Verified",
            "checked_at": datetime.now(timezone.utc)
        }
    mock_screening_run.side_effect = screening_side_effect

    state = {"requisition": requisition}
    
    start_time = time.time()
    result = vendor_risk_node(state, db=db_mock)
    elapsed = time.time() - start_time
    
    # 3 sequential runs of 0.4s would take >= 1.2s.
    # Concurrent runs using thread pool / asyncio should take ~0.4s to 0.7s.
    assert elapsed < 0.9, f"Elapsed time was {elapsed}s, should be concurrent."
    assert mock_screening_run.call_count == 3


@patch("google.genai.Client")
def test_synthesis_called_once_per_pr(mock_client_class):
    """Test that synthesis node is called exactly once per PR and passes the structured list of items."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.parsed = MagicMock(
        verdict="escalate",
        confidence_score=0.85,
        rationale="Item 2 triggered VP review."
    )
    mock_client.models.generate_content.return_value = mock_response

    payload = {
        "purchase_requisition_id": "REQ_SYNTHESIS",
        "purchasing_group": "P01",
        "created_by_user": "TESTUSER",
        "requisition_date": str(date.today()),
        "items": [
            {"purchase_requisition_id": "REQ_SYNTHESIS", "purchase_requisition_item": "00010", "material": "M1", "vendor_id": "V1", "order_quantity": 1, "net_price_amount": 100.0, "purchasing_organization": "1000"},
            {"purchase_requisition_id": "REQ_SYNTHESIS", "purchase_requisition_item": "00020", "material": "M2", "vendor_id": "V2", "order_quantity": 2, "net_price_amount": 200.0, "purchasing_organization": "1000"}
        ]
    }
    requisition = PurchaseRequisitionSchema.model_validate(payload)
    
    price_sig = PriceAnomalySignal(has_anomaly=False)
    vendor_sig = VendorRiskSignal(is_risky=False)
    dup_sig = DuplicateSignal(is_duplicate=False)
    policy_sig = PolicyComplianceSignal(violates_policy=False, has_hard_block=False)
    
    state = {
        "requisition": requisition,
        "price_anomaly": price_sig,
        "vendor_risk": vendor_sig,
        "duplicate_detection": dup_sig,
        "policy_compliance": policy_sig,
        "intra_pr_material_overlap": None
    }
    
    from app.agent import synthesis_node
    res = synthesis_node(state, client=mock_client)
    
    assert mock_client.models.generate_content.call_count == 1
    
    triage_res = res["triage_result"]
    assert triage_res.requisition_id == "REQ_SYNTHESIS"
    assert len(triage_res.item_results) == 2
    assert triage_res.item_results[0]["material"] == "M1"
