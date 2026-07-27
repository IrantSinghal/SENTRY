from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import date, datetime

# --- Database / Entity Models ---

class VendorSchema(BaseModel):
    vendor_id: str
    vendor_name: str
    onboarded_date: date
    compliance_flags: List[str] = Field(default_factory=list)
    contract_expiry_date: date
    tax_id: Optional[str] = None
    registered_address: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class PriceHistorySchema(BaseModel):
    material: str
    vendor_id: str
    historical_avg_price: float
    last_purchase_date: date

    model_config = ConfigDict(from_attributes=True)

class PurchaseRequisitionItemSchema(BaseModel):
    purchase_requisition_id: str
    purchase_requisition_item: str
    material: str
    vendor_id: Optional[str] = None
    order_quantity: float
    net_price_amount: float
    purchasing_organization: str
    account_assignment_category: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class PurchaseRequisitionSchema(BaseModel):
    purchase_requisition_id: str
    purchasing_group: str
    created_by_user: str
    requisition_date: date
    overall_release_status: str = Field(default="open")
    items: List[PurchaseRequisitionItemSchema] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

# --- Agent Node Signals ---

class PriceAnomalyItem(BaseModel):
    purchase_requisition_item: str
    material: str
    vendor_id: str
    current_price: float
    historical_avg_price: float
    deviation_percentage: float
    is_anomaly: bool

class PriceAnomalySignal(BaseModel):
    has_anomaly: bool = False
    details: List[PriceAnomalyItem] = Field(default_factory=list)

class VendorRiskTier1Result(BaseModel):
    new_vendor: bool
    existing_compliance_issue: bool
    compliance_detail: List[str]
    contract_expiring: bool
    incomplete_vendor_data: bool
    no_price_history: bool

class AdverseMediaEvidence(BaseModel):
    evidence: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)

class AdverseMediaResult(BaseModel):
    flagged: bool
    evidence: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)

class VendorRiskDetails(BaseModel):
    vendor_id: str
    vendor_name: str
    onboarded_days_ago: int
    compliance_flags: List[str]
    contract_expires_days: int
    is_new_vendor: bool
    has_compliance_flags: bool
    is_contract_expiring: bool
    # Tier 1 additions
    tax_id: Optional[str] = None
    registered_address: Optional[str] = None
    incomplete_vendor_data: bool = False
    no_price_history: bool = False
    # Tier 2 additions
    sanctions_match: Optional[bool] = None
    sanctions_match_detail: Optional[str] = None
    adverse_media_flagged: Optional[bool] = None
    adverse_media_evidence: Optional[AdverseMediaEvidence] = None
    registry_verified: Optional[bool] = None
    registry_detail: Optional[str] = None
    checked_at: Optional[datetime] = None

class VendorRiskSignal(BaseModel):
    is_risky: bool = False
    details: List[VendorRiskDetails] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)

class DuplicateRequisitionDetails(BaseModel):
    matching_requisition_id: str
    matching_item_no: str
    material: str
    requisition_date: date
    purchasing_group: str
    match_type: str  # 'exact' | 'fuzzy'

class DuplicateSignal(BaseModel):
    is_duplicate: bool = False
    details: List[DuplicateRequisitionDetails] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)

class PolicyComplianceSignal(BaseModel):
    violates_policy: bool = False
    has_hard_block: bool = False
    reasons: List[str] = Field(default_factory=list)

class TriageSignals(BaseModel):
    price_anomaly: PriceAnomalySignal = Field(default_factory=PriceAnomalySignal)
    vendor_risk: VendorRiskSignal = Field(default_factory=VendorRiskSignal)
    duplicate_detection: DuplicateSignal = Field(default_factory=DuplicateSignal)
    policy_compliance: PolicyComplianceSignal = Field(default_factory=PolicyComplianceSignal)

# --- Final Agent Output and Database Persistence ---

class TriageResultSchema(BaseModel):
    requisition_id: str
    verdict: str = Field(description="Must be one of 'auto_approve', 'escalate', 'reject'")
    confidence_score: float = Field(description="Confidence score between 0.0 and 1.0")
    signals: TriageSignals
    rationale: str = Field(description="Structured English explanation detailing the triage decision and highlighting triggered signals")
    human_override: Optional[str] = None
    human_override_reason: Optional[str] = None
    required_approver_role: str = "approver"
    requires_named_authority: bool = False
    overridden_by_user_id: Optional[str] = None
    created_at: Optional[datetime] = None
    item_results: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    intra_pr_material_overlap: Optional[List[Dict[str, Any]]] = None

    # Added fields to prevent frontend undefined properties crashes
    total_value: Optional[float] = None
    created_by_user: Optional[str] = None
    requisition_date: Optional[date] = None
    purchasing_group: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# --- API Payloads ---

class RequisitionIngestPayload(BaseModel):
    purchase_requisition_id: str
    purchasing_group: str
    created_by_user: str
    requisition_date: date
    items: List[dict]  # Allow flexible dicts in payload for intake node to clean

class HumanOverridePayload(BaseModel):
    override_decision: str = Field(pattern="^(approved|rejected|escalated)$")
    reason: Optional[str] = None

class QueueItem(BaseModel):
    requisition_id: str
    purchasing_group: str
    created_by_user: str
    requisition_date: date
    overall_release_status: str
    total_value: float
    verdict: str
    confidence_score: float
    rationale: str
    required_approver_role: str = "approver"
    requires_named_authority: bool = False
    overridden_by_user_id: Optional[str] = None
    created_at: datetime
    signals: TriageSignals

class SummaryAnalytics(BaseModel):
    auto_approval_rate: float
    avg_time_to_decision_seconds: float
    escalation_reason_breakdown: Dict[str, int]
    total_processed: int
    total_approved: int
    total_rejected: int
    total_escalated: int
    daily_volume: Optional[List[Dict[str, Any]]] = None

class VendorScreeningCacheSchema(BaseModel):
    vendor_id: str
    sanctions_match: bool
    sanctions_match_detail: Optional[str] = None
    adverse_media_flagged: bool
    adverse_media_evidence: Optional[AdverseMediaEvidence] = None
    registry_verified: Optional[bool] = None
    registry_detail: Optional[str] = None
    checked_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LaunchpadSummary(BaseModel):
    pending_queue_count: int
    flagged_vendors_7d_count: int
    needs_authority_count: int


class SystemSettings(BaseModel):
    auto_approval_ceiling: float
    confidence_threshold: float
    price_deviation_threshold: Optional[float] = 0.15
    new_vendor_threshold_days: Optional[float] = 90.0
    duplicate_window_days: Optional[float] = 30.0
    contract_expiry_warning_days: Optional[float] = 30.0
    vendor_screening_staleness_days: Optional[float] = 30.0
    sanctions_match_threshold: Optional[float] = 90.0

class AuditLogItem(BaseModel):
    requisition_id: str
    verdict: str
    confidence_score: float
    required_approver_role: str
    requires_named_authority: bool
    created_at: datetime
    human_override: Optional[str] = None
    human_override_reason: Optional[str] = None
    created_by_user: str
    purchasing_group: str
    total_value: float

class AuditLogResponse(BaseModel):
    items: List[AuditLogItem]
    total: int
