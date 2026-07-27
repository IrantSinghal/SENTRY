import os
import json
import urllib.request
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from typing_extensions import TypedDict
from sqlalchemy import text
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from rapidfuzz import fuzz

# LangGraph imports
from langgraph.graph import StateGraph, END

# Gemini SDK imports
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Internal imports
from app.db import SessionLocal
from app.models import (
    PurchaseRequisitionSchema,
    PurchaseRequisitionItemSchema,
    PriceAnomalySignal,
    PriceAnomalyItem,
    VendorRiskSignal,
    VendorRiskDetails,
    DuplicateSignal,
    DuplicateRequisitionDetails,
    PolicyComplianceSignal,
    TriageSignals,
    TriageResultSchema,
    VendorRiskTier1Result,
    AdverseMediaEvidence,
    AdverseMediaResult
)

# Load environment variables
load_dotenv()
import time

# Cache variables for AgentSettings
_settings_cache = {}
_settings_cache_time = 0.0
SETTINGS_CACHE_TTL = 30.0

def get_setting(key: str, default: float, db: Optional[Session] = None) -> float:
    global _settings_cache, _settings_cache_time
    now = time.time()
    if now - _settings_cache_time > SETTINGS_CACHE_TTL:
        _settings_cache_time = now
        is_mock = False
        if db is not None:
            if hasattr(db, "_mock_return_value") or "Mock" in type(db).__name__:
                is_mock = True
        
        local_db = None
        close_on_exit = False
        if db is not None and not is_mock:
            local_db = db
        else:
            try:
                local_db = SessionLocal()
                close_on_exit = True
            except Exception:
                pass
        
        if local_db is not None:
            try:
                rows = local_db.execute(text("SELECT key, value FROM AgentSettings")).fetchall()
                _settings_cache = {row[0]: float(row[1]) for row in rows}
            except Exception:
                pass
            finally:
                if close_on_exit:
                    local_db.close()
                    
    if key not in _settings_cache:
        env_key = key.upper()
        env_val = os.getenv(env_key)
        if env_val is not None:
            try:
                return float(env_val)
            except ValueError:
                pass
        return default
    return _settings_cache[key]

# Configuration defaults (can be overridden at runtime via env variables or DB settings)
AUTO_APPROVAL_CEILING = float(os.getenv("AUTO_APPROVAL_CEILING", "5000.0"))
PRICE_DEVIATION_THRESHOLD = float(os.getenv("PRICE_DEVIATION_THRESHOLD", "0.15"))
NEW_VENDOR_THRESHOLD_DAYS = int(os.getenv("NEW_VENDOR_THRESHOLD_DAYS", "90"))
DUPLICATE_WINDOW_DAYS = int(os.getenv("DUPLICATE_WINDOW_DAYS", "30"))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.80"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-1.5-flash")
CONTRACT_EXPIRY_WARNING_DAYS = int(os.getenv("CONTRACT_EXPIRY_WARNING_DAYS", "30"))
VENDOR_SCREENING_STALENESS_DAYS = int(os.getenv("VENDOR_SCREENING_STALENESS_DAYS", "30"))
SANCTIONS_MATCH_THRESHOLD = float(os.getenv("SANCTIONS_MATCH_THRESHOLD", "90.0"))


# State definition
class AgentState(TypedDict):
    raw_payload: Dict[str, Any]
    requisition: Optional[PurchaseRequisitionSchema]
    price_anomaly: Optional[PriceAnomalySignal]
    vendor_risk: Optional[VendorRiskSignal]
    duplicate_detection: Optional[DuplicateSignal]
    policy_compliance: Optional[PolicyComplianceSignal]
    triage_result: Optional[TriageResultSchema]
    required_approver_role: Optional[str]
    requires_named_authority: Optional[bool]
    intra_pr_material_overlap: Optional[List[Dict[str, Any]]]

# Pydantic model for Gemini structured output
class GeminiSynthesisResponse(BaseModel):
    verdict: str = Field(description="The recommended verdict: 'auto_approve', 'escalate', or 'reject'")
    confidence_score: float = Field(description="Confidence score for this decision (between 0.0 and 1.0)")
    rationale: str = Field(description="Structured English explanation detailing the triage decision and highlighting triggered signals")


# --- 1. Intake Node ---
def intake_node(state: AgentState) -> Dict[str, Any]:
    """Validates and normalizes the incoming requisition payload."""
    raw = state.get("raw_payload")
    if not raw:
        raise ValueError("No raw payload provided in state.")
    
    # Work on a copy of the dictionary to avoid mutating the original input state
    import copy
    data = copy.deepcopy(raw)
    
    req_id = data.get("purchase_requisition_id")
    if not req_id:
        raise ValueError("purchase_requisition_id is required in raw payload.")
        
    items = data.get("items", [])
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        # Set parent ID on item
        if "purchase_requisition_id" not in item:
            item["purchase_requisition_id"] = req_id
        # Ensure item number exists
        if "purchase_requisition_item" not in item:
            item["purchase_requisition_item"] = f"{(i+1)*10:05d}"
            
    requisition = PurchaseRequisitionSchema.model_validate(data)
    return {"requisition": requisition}


# --- 2. Price Anomaly Node ---
def price_anomaly_node(state: AgentState, db: Optional[Session] = None) -> Dict[str, Any]:
    """Compares item net_price_amount to historical_avg_price for material/vendor."""
    requisition = state.get("requisition")
    if not requisition:
        raise ValueError("Requisition not found in state.")
    
    close_db_on_exit = False
    if db is None:
        db = SessionLocal()
        close_db_on_exit = True

    try:
        anomaly_items = []
        has_anomaly = False

        for item in requisition.items:
            if not item.vendor_id:
                continue

            # Query historical average price
            result = db.execute(
                text("""
                    SELECT historical_avg_price 
                    FROM PriceHistory 
                    WHERE material = :material AND vendor_id = :vendor_id
                """),
                {"material": item.material, "vendor_id": item.vendor_id}
            ).fetchone()

            if result:
                hist_avg = float(result[0])
                deviation = abs(item.net_price_amount - hist_avg) / hist_avg
                is_anomaly = deviation > get_setting("price_deviation_threshold", PRICE_DEVIATION_THRESHOLD, db)
                if is_anomaly:
                    has_anomaly = True

                anomaly_items.append(PriceAnomalyItem(
                    purchase_requisition_item=item.purchase_requisition_item,
                    material=item.material,
                    vendor_id=item.vendor_id,
                    current_price=item.net_price_amount,
                    historical_avg_price=hist_avg,
                    deviation_percentage=deviation,
                    is_anomaly=is_anomaly
                ))
            else:
                # No price history found - not flagged as anomaly but recorded
                anomaly_items.append(PriceAnomalyItem(
                    purchase_requisition_item=item.purchase_requisition_item,
                    material=item.material,
                    vendor_id=item.vendor_id,
                    current_price=item.net_price_amount,
                    historical_avg_price=0.0,
                    deviation_percentage=0.0,
                    is_anomaly=False
                ))

        signal = PriceAnomalySignal(has_anomaly=has_anomaly, details=anomaly_items)
        return {"price_anomaly": signal}

    finally:
        if close_db_on_exit:
            db.close()


# --- Helper: Tier 2 Background Screening ---
def run_tier2_screening(vendor_id: str, vendor_name: str, db: Session, client: Optional[genai.Client] = None) -> Dict[str, Any]:
    """Runs Tier 2 background checks (sanctions fuzzy match, business registry verification, adverse media search) and caches result."""
    # 1. Fuzzy match against SanctionsList
    sanctions_match = False
    sanctions_detail = None
    
    sanctions_list = db.execute(text("SELECT listed_name, list_source FROM SanctionsList")).fetchall()
    best_score = 0.0
    matched_entry = None
    matched_source = None
    
    for listed_name, source in sanctions_list:
        score = fuzz.token_sort_ratio(vendor_name.lower(), listed_name.lower())
        if score > best_score:
            best_score = score
            matched_entry = listed_name
            matched_source = source
            
    if best_score >= get_setting("sanctions_match_threshold", SANCTIONS_MATCH_THRESHOLD, db):
        sanctions_match = True
        sanctions_detail = f"Fuzzy match with '{matched_entry}' on {matched_source} list ({best_score:.1f}% similarity)"
    else:
        sanctions_detail = f"No match found. Closest: '{matched_entry}' ({best_score:.1f}% similarity)" if matched_entry else "No records in sanctions list."

    # 2. Business Registry Verification via OpenCorporates API
    registry_verified = None
    registry_detail = None
    
    try:
        encoded_name = urllib.parse.quote(vendor_name)
        url = f"https://api.opencorporates.com/v0.4/companies/search?q={encoded_name}"
        api_token = os.getenv("OPENCORPORATES_API_KEY")
        if api_token:
            url += f"&api_token={api_token}"
            
        req = urllib.request.Request(
            url, 
            headers={"User-Agent": "PRTriageAgent/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                res_data = json.loads(response.read().decode("utf-8"))
                companies = res_data.get("results", {}).get("companies", [])
                if companies:
                    registry_verified = True
                    first_company = companies[0].get("company", {})
                    company_number = first_company.get("company_number")
                    jurisdiction = first_company.get("jurisdiction_code")
                    registry_detail = f"Verified: Registered in {jurisdiction.upper()} (No: {company_number})"
                else:
                    registry_verified = False
                    registry_detail = "No matching entity found in OpenCorporates registry"
            else:
                registry_detail = f"OpenCorporates API returned HTTP status {response.status}"
    except Exception as e:
        print(f"Graceful warning: OpenCorporates API call failed for {vendor_name}: {e}")
        registry_verified = None
        registry_detail = f"Verification failed: {str(e)}"

    # 3. Adverse Media via Gemini Google Search grounding
    adverse_media_flagged = False
    adverse_evidence = []
    adverse_sources = []
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not set. Using fallback mock adverse media check.")
        if "banned" in vendor_name.lower():
            adverse_media_flagged = True
            adverse_evidence = ["Recent reports detail supply chain sanctions violations and illegal exports."]
            adverse_sources = ["https://www.financialtimes.com/example-banned-electronics-violations"]
    else:
        if client is None:
            client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Search for recent news about the vendor "{vendor_name}" in the context of fraud, sanctions violations, lawsuits, regulatory penalties, or severe financial distress.
        Identify if there are any significant adverse media mentions.
        Return a structured response in the specified schema.
        - flagged: true if there is any concerning news, false otherwise.
        - evidence: list of specific sentences or summaries describing the adverse findings.
        - sources: list of URLs or media sources where the evidence was found.
        """
        
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    response_mime_type="application/json",
                    response_schema=AdverseMediaResult,
                    temperature=0.2,
                )
            )
            parsed: AdverseMediaResult = response.parsed
            adverse_media_flagged = parsed.flagged
            adverse_evidence = parsed.evidence
            adverse_sources = parsed.sources
        except Exception as e:
            print(f"Error during Gemini Adverse Media search: {e}. Falling back to default negative result.")
            adverse_media_flagged = False
            adverse_evidence = []
            adverse_sources = []

    # 4. Upsert screening cache in the DB
    checked_at = datetime.now(timezone.utc)
    evidence_json = json.dumps({"evidence": adverse_evidence, "sources": adverse_sources})
    
    db.execute(
        text("""
            INSERT INTO VendorScreeningCache (vendor_id, sanctions_match, sanctions_match_detail, adverse_media_flagged, adverse_media_evidence, registry_verified, registry_detail, checked_at)
            VALUES (:vendor_id, :sanctions_match, :sanctions_detail, :adverse_flagged, CAST(:evidence_json AS jsonb), :registry_verified, :registry_detail, :checked_at)
            ON CONFLICT (vendor_id) DO UPDATE SET
                sanctions_match = EXCLUDED.sanctions_match,
                sanctions_match_detail = EXCLUDED.sanctions_match_detail,
                adverse_media_flagged = EXCLUDED.adverse_media_flagged,
                adverse_media_evidence = EXCLUDED.adverse_media_evidence,
                registry_verified = EXCLUDED.registry_verified,
                registry_detail = EXCLUDED.registry_detail,
                checked_at = EXCLUDED.checked_at;
        """),
        {
            "vendor_id": vendor_id,
            "sanctions_match": sanctions_match,
            "sanctions_detail": sanctions_detail,
            "adverse_flagged": adverse_media_flagged,
            "evidence_json": evidence_json,
            "registry_verified": registry_verified,
            "registry_detail": registry_detail,
            "checked_at": checked_at
        }
    )
    db.commit()
    
    return {
        "sanctions_match": sanctions_match,
        "sanctions_match_detail": sanctions_detail,
        "adverse_media_flagged": adverse_media_flagged,
        "adverse_media_evidence": {"evidence": adverse_evidence, "sources": adverse_sources},
        "registry_verified": registry_verified,
        "registry_detail": registry_detail,
        "checked_at": checked_at
    }


# --- Helper: Thread-Safe Tier 2 Background Screening ---
def run_tier2_screening_in_new_session(vendor_id: str, vendor_name: str, client: Optional[genai.Client] = None) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        return run_tier2_screening(vendor_id, vendor_name, db, client)
    finally:
        db.close()


# --- 3. Vendor Risk Node ---
def vendor_risk_node(state: AgentState, db: Optional[Session] = None) -> Dict[str, Any]:
    """Flags new vendors, compliance issues, contract expiry issues, and runs Tier 2 background checks concurrently."""
    requisition = state.get("requisition")
    if not requisition:
        raise ValueError("Requisition not found in state.")

    close_db_on_exit = False
    if db is None:
        db = SessionLocal()
        close_db_on_exit = True

    try:
        import asyncio
        import threading

        risk_details = []
        reasons = []
        is_risky = False

        # Gather unique vendor IDs
        vendor_ids = list(set(item.vendor_id for item in requisition.items if item.vendor_id))

        vendor_records = {}
        vendors_needing_screening = []

        # 1. First Pass: Read Vendor details and check cache status
        for v_id in vendor_ids:
            result = db.execute(
                text("""
                    SELECT vendor_name, onboarded_date, compliance_flags, contract_expiry_date, tax_id, registered_address 
                    FROM Vendor 
                    WHERE vendor_id = :vendor_id
                """),
                {"vendor_id": v_id}
            ).fetchone()

            if result:
                v_name, onboarded_date, compliance_flags, contract_expiry_date, tax_id, registered_address = result
                
                # --- Tier 1 Checks ---
                onboarded_days = (date.today() - onboarded_date).days
                contract_days = (contract_expiry_date - date.today()).days
                
                is_new = onboarded_days < get_setting("new_vendor_threshold_days", NEW_VENDOR_THRESHOLD_DAYS, db)
                has_compliance = len(compliance_flags) > 0
                is_expiring = contract_days <= get_setting("contract_expiry_warning_days", CONTRACT_EXPIRY_WARNING_DAYS, db)
                incomplete_vendor_data = not tax_id or not registered_address
                
                # Check price history presence
                ph_count = db.execute(
                    text("SELECT COUNT(*) FROM PriceHistory WHERE vendor_id = :vendor_id"),
                    {"vendor_id": v_id}
                ).scalar()
                no_price_history = ph_count == 0

                # --- Tier 2 Checks (Read Cache) ---
                cache = db.execute(
                    text("""
                        SELECT sanctions_match, sanctions_match_detail, adverse_media_flagged, adverse_media_evidence, registry_verified, registry_detail, checked_at 
                        FROM VendorScreeningCache 
                        WHERE vendor_id = :vendor_id
                    """),
                    {"vendor_id": v_id}
                ).fetchone()

                use_cache = False
                sanctions_match = False
                sanctions_match_detail = None
                adverse_media_flagged = False
                adverse_media_evidence = None
                registry_verified = None
                registry_detail = None
                last_checked_at = None

                if cache:
                    s_match, s_detail, am_flagged, am_evidence, reg_verified, reg_detail, checked_at = cache
                    
                    # Check staleness
                    stale_days = int(get_setting("vendor_screening_staleness_days", VENDOR_SCREENING_STALENESS_DAYS, db))
                    cache_age = datetime.now(timezone.utc) - checked_at
                    if cache_age.days < stale_days:
                        use_cache = True
                        sanctions_match = s_match
                        sanctions_match_detail = s_detail
                        adverse_media_flagged = am_flagged
                        
                        if isinstance(am_evidence, str):
                            am_evidence = json.loads(am_evidence)
                        
                        if isinstance(am_evidence, dict):
                            adverse_media_evidence = AdverseMediaEvidence(
                                evidence=am_evidence.get("evidence", []),
                                sources=am_evidence.get("sources", [])
                            )
                        
                        registry_verified = reg_verified
                        registry_detail = reg_detail
                        last_checked_at = checked_at

                vendor_records[v_id] = {
                    "v_name": v_name,
                    "onboarded_days": onboarded_days,
                    "compliance_flags": compliance_flags,
                    "contract_days": contract_days,
                    "is_new": is_new,
                    "has_compliance": has_compliance,
                    "is_expiring": is_expiring,
                    "incomplete_vendor_data": incomplete_vendor_data,
                    "no_price_history": no_price_history,
                    "tax_id": tax_id,
                    "registered_address": registered_address,
                    "use_cache": use_cache,
                    "sanctions_match": sanctions_match,
                    "sanctions_match_detail": sanctions_match_detail,
                    "adverse_media_flagged": adverse_media_flagged,
                    "adverse_media_evidence": adverse_media_evidence,
                    "registry_verified": registry_verified,
                    "registry_detail": registry_detail,
                    "last_checked_at": last_checked_at
                }

                if not use_cache:
                    vendors_needing_screening.append((v_id, v_name))

        # 2. Concurrently run live background screening for uncached/stale vendors
        if vendors_needing_screening:
            async def run_gather():
                loop = asyncio.get_running_loop()
                tasks = []
                for v_id, v_name in vendors_needing_screening:
                    task = loop.run_in_executor(None, run_tier2_screening_in_new_session, v_id, v_name)
                    tasks.append(task)
                return await asyncio.gather(*tasks)

            # Thread-safe async run
            def run_async_in_new_loop(coro):
                res_box = []
                err_box = []
                def target():
                    try:
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        res = new_loop.run_until_complete(coro)
                        res_box.append(res)
                    except Exception as e:
                        err_box.append(e)
                    finally:
                        new_loop.close()
                t = threading.Thread(target=target)
                t.start()
                t.join()
                if err_box:
                    raise err_box[0]
                return res_box[0]

            screen_results = run_async_in_new_loop(run_gather())
            
            # Map back to vendor_records
            for (v_id, _), screening in zip(vendors_needing_screening, screen_results):
                rec = vendor_records[v_id]
                rec["sanctions_match"] = screening["sanctions_match"]
                rec["sanctions_match_detail"] = screening["sanctions_match_detail"]
                rec["adverse_media_flagged"] = screening["adverse_media_flagged"]
                
                am_evidence = screening["adverse_media_evidence"]
                rec["adverse_media_evidence"] = AdverseMediaEvidence(
                    evidence=am_evidence.get("evidence", []),
                    sources=am_evidence.get("sources", [])
                )
                
                rec["registry_verified"] = screening["registry_verified"]
                rec["registry_detail"] = screening["registry_detail"]
                rec["last_checked_at"] = screening["checked_at"]

        # 3. Third Pass: Aggregate and build risk details
        for v_id, rec in vendor_records.items():
            v_name = rec["v_name"]
            is_new = rec["is_new"]
            has_compliance = rec["has_compliance"]
            is_expiring = rec["is_expiring"]
            incomplete_vendor_data = rec["incomplete_vendor_data"]
            no_price_history = rec["no_price_history"]
            sanctions_match = rec["sanctions_match"]
            sanctions_match_detail = rec["sanctions_match_detail"]
            adverse_media_flagged = rec["adverse_media_flagged"]
            adverse_media_evidence = rec["adverse_media_evidence"]
            registry_verified = rec["registry_verified"]
            registry_detail = rec["registry_detail"]
            last_checked_at = rec["last_checked_at"]
            onboarded_days = rec["onboarded_days"]
            contract_days = rec["contract_days"]
            compliance_flags = rec["compliance_flags"]
            tax_id = rec["tax_id"]
            registered_address = rec["registered_address"]

            vendor_is_risky = (
                is_new or 
                has_compliance or 
                is_expiring or 
                incomplete_vendor_data or 
                no_price_history or
                sanctions_match or
                adverse_media_flagged or
                registry_verified == False
            )

            if vendor_is_risky:
                is_risky = True
                
                # Construct specific warning reasons
                if is_new:
                    reasons.append(f"Vendor {v_name} ({v_id}) is new (onboarded {onboarded_days} days ago).")
                if has_compliance:
                    reasons.append(f"Vendor {v_name} ({v_id}) has compliance flags: {', '.join(compliance_flags)}.")
                if is_expiring:
                    reasons.append(f"Vendor {v_name} ({v_id}) contract is expiring in {contract_days} days.")
                if incomplete_vendor_data:
                    missing = []
                    if not tax_id: missing.append("Tax ID")
                    if not registered_address: missing.append("Registered Address")
                    reasons.append(f"Vendor {v_name} ({v_id}) has incomplete registry data (missing {', '.join(missing)}).")
                if no_price_history:
                    reasons.append(f"Vendor {v_name} ({v_id}) has no historical pricing records.")
                if sanctions_match:
                    reasons.append(f"Vendor {v_name} ({v_id}) sanctions match: {sanctions_match_detail}.")
                if adverse_media_flagged:
                    reasons.append(f"Vendor {v_name} ({v_id}) has flagged adverse media.")
                if registry_verified == False:
                    reasons.append(f"Vendor {v_name} ({v_id}) registry lookup failed verification.")

            risk_details.append(VendorRiskDetails(
                vendor_id=v_id,
                vendor_name=v_name,
                onboarded_days_ago=onboarded_days,
                compliance_flags=compliance_flags,
                contract_expires_days=contract_days,
                is_new_vendor=is_new,
                has_compliance_flags=has_compliance,
                is_contract_expiring=is_expiring,
                tax_id=tax_id,
                registered_address=registered_address,
                incomplete_vendor_data=incomplete_vendor_data,
                no_price_history=no_price_history,
                sanctions_match=sanctions_match,
                sanctions_match_detail=sanctions_match_detail,
                adverse_media_flagged=adverse_media_flagged,
                adverse_media_evidence=adverse_media_evidence,
                registry_verified=registry_verified,
                registry_detail=registry_detail,
                checked_at=last_checked_at
            ))

        signal = VendorRiskSignal(is_risky=is_risky, details=risk_details, reasons=reasons)
        return {"vendor_risk": signal}

    finally:
        if close_db_on_exit:
            db.close()


# --- 4. Duplicate Detection Node ---
def duplicate_detection_node(state: AgentState, db: Optional[Session] = None) -> Dict[str, Any]:
    """Searches open requisitions for same/similar material within rolling window in different purchasing groups."""
    requisition = state.get("requisition")
    if not requisition:
        raise ValueError("Requisition not found in state.")

    close_db_on_exit = False
    if db is None:
        db = SessionLocal()
        close_db_on_exit = True

    try:
        duplicate_details = []
        reasons = []
        is_duplicate = False

        dup_window = int(get_setting("duplicate_window_days", DUPLICATE_WINDOW_DAYS, db))
        # Define time window
        start_date = requisition.requisition_date - timedelta(days=dup_window)
        end_date = requisition.requisition_date + timedelta(days=dup_window)

        # Query all other open requisitions and items within the rolling window
        other_items = db.execute(
            text("""
                SELECT pr.purchase_requisition_id, pr.requisition_date, pr.purchasing_group, pri.purchase_requisition_item, pri.material
                FROM PurchaseRequisition pr
                JOIN PurchaseRequisitionItem pri ON pr.purchase_requisition_id = pri.purchase_requisition_id
                WHERE pr.overall_release_status = 'open'
                  AND pr.purchase_requisition_id != :current_req_id
                  AND pr.requisition_date BETWEEN :start_date AND :end_date
            """),
            {
                "current_req_id": requisition.purchase_requisition_id,
                "start_date": start_date,
                "end_date": end_date
            }
        ).fetchall()

        for item in requisition.items:
            for other_id, other_date, other_group, other_item_no, other_material in other_items:
                # Check purchasing groups differ
                if requisition.purchasing_group == other_group:
                    continue

                match_type = None
                # Check exact material match
                if item.material == other_material:
                    match_type = "exact"
                # Check fuzzy match
                else:
                    ratio = fuzz.ratio(item.material.lower(), other_material.lower())
                    if ratio >= 80.0:
                        match_type = "fuzzy"

                if match_type:
                    is_duplicate = True
                    details_obj = DuplicateRequisitionDetails(
                        matching_requisition_id=other_id,
                        matching_item_no=other_item_no,
                        material=other_material,
                        requisition_date=other_date,
                        purchasing_group=other_group,
                        match_type=match_type
                    )
                    duplicate_details.append(details_obj)
                    
                    reasons.append(
                        f"Item {item.purchase_requisition_item} ({item.material}) has a {match_type} match in open Requisition {other_id} "
                        f"(Item {other_item_no}, Group {other_group}) created on {other_date} (within {dup_window} days)."
                    )

        signal = DuplicateSignal(is_duplicate=is_duplicate, details=duplicate_details, reasons=reasons)
        return {"duplicate_detection": signal}

    finally:
        if close_db_on_exit:
            db.close()


# --- 5. Policy Compliance Node ---
def policy_compliance_node(state: AgentState, db: Optional[Session] = None) -> Dict[str, Any]:
    """Checks for policy limits and hard blocks (sanctioned vendors, banned materials)."""
    requisition = state.get("requisition")
    if not requisition:
        raise ValueError("Requisition not found in state.")

    close_db_on_exit = False
    if db is None:
        db = SessionLocal()
        close_db_on_exit = True

    try:
        reasons = []
        violates_policy = False
        has_hard_block = False

        # Calculate total value
        total_value = sum(item.order_quantity * item.net_price_amount for item in requisition.items)

        # Check total value ceiling
        ceiling = get_setting("auto_approval_ceiling", AUTO_APPROVAL_CEILING, db)
        if total_value > ceiling:
            violates_policy = True
            reasons.append(f"Requisition total value {total_value:.2f} exceeds auto-approval ceiling of {ceiling:.2f}.")

        # Check for banned materials
        for item in requisition.items:
            mat_upper = item.material.upper()
            if "BANNED" in mat_upper or "SANCTIONED" in mat_upper:
                violates_policy = True
                has_hard_block = True
                reasons.append(f"Item {item.purchase_requisition_item} contains restricted material: '{item.material}'.")

            # Check vendor sanctioned flag
            if item.vendor_id:
                result = db.execute(
                    text("SELECT compliance_flags FROM Vendor WHERE vendor_id = :vendor_id"),
                    {"vendor_id": item.vendor_id}
                ).fetchone()
                
                if result:
                    flags = result[0]
                    if any("sanctioned" in flag.lower() for flag in flags):
                        violates_policy = True
                        has_hard_block = True
                        reasons.append(f"Item {item.purchase_requisition_item} refers to a sanctioned vendor: {item.vendor_id}.")

        # Check for sanctions match from vendor risk node (Tier 2 fuzzy watchlists match)
        vendor_risk = state.get("vendor_risk")
        if vendor_risk and hasattr(vendor_risk, "details"):
            for detail in vendor_risk.details:
                if detail.sanctions_match:
                    violates_policy = True
                    has_hard_block = True
                    reasons.append(f"Vendor {detail.vendor_name} ({detail.vendor_id}) has a sanctions match: {detail.sanctions_match_detail}.")

        signal = PolicyComplianceSignal(
            violates_policy=violates_policy,
            has_hard_block=has_hard_block,
            reasons=reasons
        )
        return {"policy_compliance": signal}

    finally:
        if close_db_on_exit:
            db.close()


# --- 5b. Intra-PR Material Overlap Node ---
def intra_pr_material_overlap_node(state: AgentState) -> Dict[str, Any]:
    """
    Groups all line items in the PR by material.
    If any material appears more than once with different vendor_ids, flags it.
    """
    requisition = state.get("requisition")
    if not requisition:
        raise ValueError("Requisition not found in state.")

    from collections import defaultdict
    by_material = defaultdict(list)
    for item in requisition.items:
        if item.vendor_id:
            by_material[item.material].append(item)

    overlaps = []
    for material, items in by_material.items():
        unique_vendors = list(set(item.vendor_id for item in items))
        if len(unique_vendors) > 1:
            item_ids = [item.purchase_requisition_item for item in items]
            overlaps.append({
                "material": material,
                "item_ids": item_ids,
                "vendor_ids": unique_vendors
            })

    return {"intra_pr_material_overlap": overlaps if overlaps else None}




# --- Helper: Compute Itemized Results ---
def compute_itemized_results(requisition, price_anomaly, vendor_risk, duplicate_det, policy_comp) -> List[Dict[str, Any]]:
    item_results = []
    vendor_risk_cache = {}
    
    for item in requisition.items:
        # 1. Price Anomaly
        item_price_anomaly = False
        item_price_deviation = 0.0
        if price_anomaly and price_anomaly.details:
            for det in price_anomaly.details:
                if det.purchase_requisition_item == item.purchase_requisition_item:
                    item_price_anomaly = det.is_anomaly
                    item_price_deviation = det.deviation_percentage
                    break

        # 2. Vendor Risk
        v_id = item.vendor_id
        if v_id and v_id in vendor_risk_cache:
            vendor_risk_sig = vendor_risk_cache[v_id]
            item_vendor_risk = vendor_risk_sig["flagged"]
            vendor_detail = None
            if vendor_risk and vendor_risk.details:
                for det in vendor_risk.details:
                    if det.vendor_id == v_id:
                        vendor_detail = det
                        break
        else:
            item_vendor_risk = False
            item_vendor_reasons = []
            vendor_detail = None
            if vendor_risk and vendor_risk.details:
                for det in vendor_risk.details:
                    if det.vendor_id == item.vendor_id:
                        vendor_detail = det
                        is_v_risky = (
                            det.is_new_vendor or
                            det.has_compliance_flags or
                            det.is_contract_expiring or
                            det.incomplete_vendor_data or
                            det.no_price_history or
                            det.sanctions_match or
                            det.adverse_media_flagged or
                            det.registry_verified == False
                        )
                        if is_v_risky:
                            item_vendor_risk = True
                            for r in vendor_risk.reasons:
                                if det.vendor_id in r or (det.vendor_name and det.vendor_name in r):
                                   item_vendor_reasons.append(r)
                        break
            vendor_risk_sig = {
                "flagged": item_vendor_risk,
                "reasons": item_vendor_reasons
            }
            if v_id:
                vendor_risk_cache[v_id] = vendor_risk_sig

        # 3. Duplicate Detection
        item_duplicate = False
        item_duplicate_reasons = []
        if duplicate_det and duplicate_det.details:
            for det in duplicate_det.details:
                if det.material == item.material:
                    item_duplicate = True
                    for r in duplicate_det.reasons:
                        if item.purchase_requisition_item in r:
                            item_duplicate_reasons.append(r)
                    break

        # 4. Policy Compliance
        item_policy_violates = False
        item_policy_hard_block = False
        item_policy_reasons = []
        # Check banned material
        mat_upper = item.material.upper()
        if "BANNED" in mat_upper or "SANCTIONED" in mat_upper:
            item_policy_violates = True
            item_policy_hard_block = True
            item_policy_reasons.append(f"Item {item.purchase_requisition_item} contains restricted material: '{item.material}'.")
        # Check vendor sanctioned flag
        if vendor_detail and vendor_detail.sanctions_match:
            item_policy_violates = True
            item_policy_hard_block = True
            item_policy_reasons.append(f"Vendor {vendor_detail.vendor_name} ({vendor_detail.vendor_id}) has a sanctions match: {vendor_detail.sanctions_match_detail}.")
        # Other policy reasons
        if policy_comp and policy_comp.reasons:
            for r in policy_comp.reasons:
                if f"Item {item.purchase_requisition_item}" in r and r not in item_policy_reasons:
                    item_policy_violates = True
                    if "restricted material" in r or "sanctioned vendor" in r:
                         item_policy_hard_block = True
                    item_policy_reasons.append(r)

        # Compute item verdict
        if item_policy_hard_block:
            item_verdict = "reject"
        elif item_price_anomaly or item_vendor_risk or item_duplicate or item_policy_violates:
            item_verdict = "escalate"
        else:
            item_verdict = "auto_approve"

        # Item-level role and named authority
        item_val = item.order_quantity * item.net_price_amount
        item_required_approver_role = "approver"
        item_requires_named_authority = False

        if item_verdict == "reject":
            item_required_approver_role = "cfo"
            item_requires_named_authority = True
        elif item_verdict == "escalate":
            if item_val > 50000:
                item_required_approver_role = "cfo"
                item_requires_named_authority = True
            elif item_val > 15000:
                item_required_approver_role = "vp"
                item_requires_named_authority = True
            elif item_vendor_risk:
                item_required_approver_role = "vp"
                item_requires_named_authority = True
            else:
                item_required_approver_role = "approver"
                item_requires_named_authority = False
        else:
            item_required_approver_role = "analyst"
            item_requires_named_authority = False

        item_results.append({
            "item_id": item.purchase_requisition_item,
            "material": item.material,
            "vendor_id": item.vendor_id,
            "verdict": item_verdict,
            "required_approver_role": item_required_approver_role,
            "requires_named_authority": item_requires_named_authority,
            "net_price_amount": float(item.net_price_amount),
            "order_quantity": float(item.order_quantity),
            "total_value": float(item_val),
            "signals": {
                "price_anomaly": {
                    "flagged": item_price_anomaly,
                    "deviation": item_price_deviation
                },
                "vendor_risk": vendor_risk_sig,
                "duplicate_detection": {
                    "flagged": item_duplicate,
                    "reasons": item_duplicate_reasons
                },
                "policy_compliance": {
                    "violates_policy": item_policy_violates,
                    "has_hard_block": item_policy_hard_block,
                    "reasons": item_policy_reasons
                }
            }
        })
        
    return item_results



# --- 6. Synthesis Node (LLM via google-genai) ---
def synthesis_node(state: AgentState, client: Optional[genai.Client] = None) -> Dict[str, Any]:
    """Generates structured verdict, confidence score, and plain English rationale using Gemini."""
    requisition = state.get("requisition")
    price_anomaly = state.get("price_anomaly")
    vendor_risk = state.get("vendor_risk")
    duplicate_det = state.get("duplicate_detection")
    policy_comp = state.get("policy_compliance")
    intra_pr_overlap = state.get("intra_pr_material_overlap")

    if not requisition:
        raise ValueError("Requisition data is missing for synthesis.")

    # Compute item-level signals and verdicts first
    item_signals = compute_itemized_results(requisition, price_anomaly, vendor_risk, duplicate_det, policy_comp)

    # Initialize Gemini client if not provided
    if client is None:
        api_key = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("WARNING: GEMINI_API_KEY is not set. Returning a mock synthesis result.")
            mock_res = get_mock_synthesis_response(requisition, price_anomaly, vendor_risk, duplicate_det, policy_comp, intra_pr_overlap)
            return {"triage_result": mock_res}
        client = genai.Client(api_key=api_key)

    total_val = sum(item.order_quantity * item.net_price_amount for item in requisition.items)
    
    prompt = f"""
You are the SAP Purchase Requisition Triage Synthesis Agent.
Analyze the following purchase requisition and the results of our deterministic risk checks:

Requisition ID: {requisition.purchase_requisition_id}
Purchasing Group: {requisition.purchasing_group}
Created By: {requisition.created_by_user}
Total Value: {total_val:.2f}

ITEM-LEVEL SIGNALS:
{json.dumps(item_signals, indent=2)}

INTRA-PR MATERIAL OVERLAP:
{json.dumps(intra_pr_overlap, indent=2) if intra_pr_overlap else "None"}

YOUR INSTRUCTIONS:
- Review the deterministic signals above. Do NOT perform any arithmetic of your own. Trust the flags completely.
- Formulate a brief, structured, plain-English rationale summarizing the decisions and highlighting the specific items/vendors that drove the verdict.
- Recommend a verdict:
  - If any item triggers a hard policy block, recommend 'reject'.
  - If any item triggers an anomaly, vendor risk, duplicate, policy compliance violation, or if there is an intra-PR material overlap, recommend 'escalate'.
  - Otherwise, recommend 'auto_approve'.
- Provide a confidence score (between 0.0 and 1.0) indicating how certain you are of this triage alignment. Set a high confidence (e.g. 0.95+) for clean auto-approvals or clear hard blocks.
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeminiSynthesisResponse,
                temperature=0.1
            )
        )
        
        parsed: GeminiSynthesisResponse = response.parsed
        
        triage_signals = TriageSignals(
            price_anomaly=price_anomaly or PriceAnomalySignal(),
            vendor_risk=vendor_risk or VendorRiskSignal(),
            duplicate_detection=duplicate_det or DuplicateSignal(),
            policy_compliance=policy_comp or PolicyComplianceSignal()
        )
        
        result = TriageResultSchema(
            requisition_id=requisition.purchase_requisition_id,
            verdict=parsed.verdict,
            confidence_score=parsed.confidence_score,
            signals=triage_signals,
            rationale=parsed.rationale,
            item_results=item_signals,
            intra_pr_material_overlap=intra_pr_overlap
        )
        return {"triage_result": result}
        
    except Exception as e:
        print(f"Error during Gemini generation: {e}. Attempting fallback model...")
        try:
            response = client.models.generate_content(
                model=GEMINI_FALLBACK_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiSynthesisResponse,
                    temperature=0.1
                )
            )
            parsed = response.parsed
            triage_signals = TriageSignals(
                price_anomaly=price_anomaly or PriceAnomalySignal(),
                vendor_risk=vendor_risk or VendorRiskSignal(),
                duplicate_detection=duplicate_det or DuplicateSignal(),
                policy_compliance=policy_comp or PolicyComplianceSignal()
            )
            result = TriageResultSchema(
                requisition_id=requisition.purchase_requisition_id,
                verdict=parsed.verdict,
                confidence_score=parsed.confidence_score,
                signals=triage_signals,
                rationale=parsed.rationale,
                item_results=item_signals,
                intra_pr_material_overlap=intra_pr_overlap
            )
            return {"triage_result": result}
        except Exception as fallback_err:
            print(f"Fallback model also failed: {fallback_err}. Generating static fallback response.")
            mock_res = get_mock_synthesis_response(requisition, price_anomaly, vendor_risk, duplicate_det, policy_comp, intra_pr_overlap)
            return {"triage_result": mock_res}


def get_mock_synthesis_response(requisition, price_anomaly, vendor_risk, duplicate_det, policy_comp, intra_pr_overlap=None) -> TriageResultSchema:
    """Helper to generate a fallback mock response if Gemini API key is missing or fails."""
    item_signals = compute_itemized_results(requisition, price_anomaly, vendor_risk, duplicate_det, policy_comp)
    
    # Run worst-case logic programmatically
    has_hard_block = any(item["verdict"] == "reject" for item in item_signals)
    has_signals = any(item["verdict"] == "escalate" for item in item_signals) or bool(intra_pr_overlap)
    
    reasons = []
    if price_anomaly and price_anomaly.has_anomaly:
        reasons.append("price deviation anomaly detected")
    if vendor_risk and vendor_risk.is_risky:
        reasons.append("vendor risk factors triggered")
    if duplicate_det and duplicate_det.is_duplicate:
        reasons.append("potential duplicate order found")
    if policy_comp and policy_comp.violates_policy:
        reasons.append("policy compliance threshold exceeded or restriction violated")
    if intra_pr_overlap:
        reasons.append("intra-PR material overlap detected")

    if has_hard_block:
        verdict = "reject"
        rationale = f"Requisition rejected due to hard policy violations: {', '.join(policy_comp.reasons if policy_comp else ['restricted item/vendor'])}."
    elif has_signals:
        verdict = "escalate"
        rationale = f"Requisition escalated to manual queue due to flagged risk signals: {'; '.join(reasons)}."
    else:
        verdict = "auto_approve"
        rationale = "Requisition cleared all deterministic pricing, vendor, duplicate, and policy rules. Auto-approved."

    triage_signals = TriageSignals(
        price_anomaly=price_anomaly or PriceAnomalySignal(),
        vendor_risk=vendor_risk or VendorRiskSignal(),
        duplicate_detection=duplicate_det or DuplicateSignal(),
        policy_compliance=policy_comp or PolicyComplianceSignal()
    )

    return TriageResultSchema(
        requisition_id=requisition.purchase_requisition_id,
        verdict=verdict,
        confidence_score=0.95,
        signals=triage_signals,
        rationale=rationale,
        item_results=item_signals,
        intra_pr_material_overlap=intra_pr_overlap
    )


# --- 7. HITL Decision Gate Node ---
def decision_gate_node(state: AgentState) -> Dict[str, Any]:
    """Strictly enforces the final verdict logic overriding the LLM suggestion if inconsistent."""
    triage_result = state.get("triage_result")
    price_anomaly = state.get("price_anomaly")
    vendor_risk = state.get("vendor_risk")
    duplicate_det = state.get("duplicate_detection")
    policy_comp = state.get("policy_compliance")
    requisition = state.get("requisition")
    intra_pr_overlap = state.get("intra_pr_material_overlap")

    if not triage_result or not requisition:
        raise ValueError("TriageResult or Requisition is missing in the state.")

    # Re-compute itemized results to guarantee correctness and aggregate
    item_results = compute_itemized_results(requisition, price_anomaly, vendor_risk, duplicate_det, policy_comp)

    # Worst-case wins logic
    final_verdict = "auto_approve"
    for item in item_results:
        if item["verdict"] == "reject":
            final_verdict = "reject"
            break
        elif item["verdict"] == "escalate":
            final_verdict = "escalate"

    # If any intra-PR material overlap is found, it forces escalate
    if intra_pr_overlap and final_verdict != "reject":
        final_verdict = "escalate"

    # Also check if total PR value exceeds ceiling
    total_val = sum(item.order_quantity * item.net_price_amount for item in requisition.items)
    if total_val > get_setting("auto_approval_ceiling", AUTO_APPROVAL_CEILING) and final_verdict == "auto_approve":
        final_verdict = "escalate"

    # Role hierarchy: cfo > vp > approver > analyst
    role_priority = {"cfo": 4, "vp": 3, "approver": 2, "analyst": 1}
    max_role = "analyst"
    requires_named_auth = False

    for item in item_results:
        role = item["required_approver_role"]
        if role_priority[role] > role_priority[max_role]:
            max_role = role
        if item["requires_named_authority"]:
            requires_named_auth = True

    # Enforce role escalations by value or global policies
    if final_verdict == "escalate":
        if total_val > 50000:
            if role_priority["cfo"] > role_priority[max_role]:
                max_role = "cfo"
            requires_named_auth = True
        elif total_val > 15000:
            if role_priority["vp"] > role_priority[max_role]:
                max_role = "vp"
            requires_named_auth = True
        elif policy_comp and policy_comp.has_hard_block:
            if role_priority["cfo"] > role_priority[max_role]:
                max_role = "cfo"
            requires_named_auth = True
        else:
            if role_priority["approver"] > role_priority[max_role]:
                max_role = "approver"
    elif final_verdict == "reject":
        max_role = "cfo"
        requires_named_auth = True

    triage_result.verdict = final_verdict
    triage_result.required_approver_role = max_role
    triage_result.requires_named_authority = requires_named_auth
    triage_result.item_results = item_results
    triage_result.intra_pr_material_overlap = intra_pr_overlap

    # Enforce double-check logic (HIGH PRIORITY ESCALATION prefix)
    if final_verdict == "escalate":
        trigger_count = sum([
            1 if price_anomaly and price_anomaly.has_anomaly else 0,
            1 if vendor_risk and vendor_risk.is_risky else 0,
            1 if duplicate_det and duplicate_det.is_duplicate else 0,
            1 if policy_comp and policy_comp.violates_policy else 0,
            1 if intra_pr_overlap else 0
        ])
        if trigger_count >= 2:
            if "HIGH PRIORITY ESCALATION" not in triage_result.rationale.upper():
                triage_result.rationale = f"[HIGH PRIORITY ESCALATION] - {triage_result.rationale}"

    return {
        "triage_result": triage_result,
        "required_approver_role": max_role,
        "requires_named_authority": requires_named_auth
    }


# --- Wire LangGraph state graph ---

def build_workflow() -> StateGraph:
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("node_intake", intake_node)
    workflow.add_node("node_price_anomaly", price_anomaly_node)
    workflow.add_node("node_vendor_risk", vendor_risk_node)
    workflow.add_node("node_duplicate_detection", duplicate_detection_node)
    workflow.add_node("node_policy_compliance", policy_compliance_node)
    workflow.add_node("node_intra_pr_overlap", intra_pr_material_overlap_node)
    workflow.add_node("node_synthesis", synthesis_node)
    workflow.add_node("node_decision_gate", decision_gate_node)

    # Set entry point
    workflow.set_entry_point("node_intake")

    # Wire linear execution pipeline
    workflow.add_edge("node_intake", "node_price_anomaly")
    workflow.add_edge("node_price_anomaly", "node_vendor_risk")
    workflow.add_edge("node_vendor_risk", "node_duplicate_detection")
    workflow.add_edge("node_duplicate_detection", "node_policy_compliance")
    workflow.add_edge("node_policy_compliance", "node_intra_pr_overlap")
    workflow.add_edge("node_intra_pr_overlap", "node_synthesis")
    workflow.add_edge("node_synthesis", "node_decision_gate")
    workflow.add_edge("node_decision_gate", END)

    return workflow

# Compile graph
app_workflow = build_workflow().compile()

def run_triage_flow(raw_payload: Dict[str, Any], db: Optional[Session] = None) -> TriageResultSchema:
    """Executes the triage workflow for a raw requisition payload and returns the final TriageResult."""
    # Inject database session into node calls via configuration if desired,
    # but here we rely on the nodes opening/closing local db sessions,
    # or passing a database session if run_triage_flow is called within an active transaction.
    
    # We run the compiled LangGraph workflow synchronously
    initial_state = {
        "raw_payload": raw_payload,
        "requisition": None,
        "price_anomaly": None,
        "vendor_risk": None,
        "duplicate_detection": None,
        "policy_compliance": None,
        "triage_result": None,
        "required_approver_role": None,
        "requires_named_authority": None,
        "intra_pr_material_overlap": None
    }
    
    # Run the graph
    final_state = app_workflow.invoke(initial_state)
    return final_state["triage_result"]
