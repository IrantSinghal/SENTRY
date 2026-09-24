import os
import json
import time
from typing import List, Optional
from datetime import datetime, date, timedelta
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, desc
from sqlalchemy.orm import Session

# Internal imports
from app.db import get_db, engine
from app.models import (
    RequisitionIngestPayload,
    PurchaseRequisitionSchema,
    PurchaseRequisitionItemSchema,
    TriageResultSchema,
    HumanOverridePayload,
    QueueItem,
    SummaryAnalytics,
    VendorScreeningCacheSchema,
    LaunchpadSummary,
    SystemSettings,
    AuditLogResponse,
    AuditLogItem
)
from app.agent import run_triage_flow, run_tier2_screening
from app.auth import get_current_user
from pydantic import BaseModel

app = FastAPI(
    title="SAP PR Triage Agent API",
    description="Automated triage and review of SAP Purchase Requisitions using LangGraph and Gemini.",
    version="1.0.0"
)

# CORS middleware for Next.js frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://sentry-ochre-zeta.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/requisitions/ingest", response_model=TriageResultSchema, status_code=status.HTTP_201_CREATED)
def ingest_requisition(payload: RequisitionIngestPayload, db: Session = Depends(get_db)):
    """
    Ingests a raw purchase requisition payload, runs it through the LangGraph AI flow,
    persists the requisition, its items, and the triage outcome.
    """
    try:
        # 1. Parse/Clean raw items
        cleaned_items: List[PurchaseRequisitionItemSchema] = []
        for i, item_raw in enumerate(payload.items):
            item_no = item_raw.get("purchase_requisition_item") or f"{(i+1)*10:05d}"
            cleaned_item = PurchaseRequisitionItemSchema(
                purchase_requisition_id=payload.purchase_requisition_id,
                purchase_requisition_item=item_no,
                material=item_raw.get("material", ""),
                vendor_id=item_raw.get("vendor_id"),
                order_quantity=float(item_raw.get("order_quantity", 0)),
                net_price_amount=float(item_raw.get("net_price_amount", 0)),
                purchasing_organization=item_raw.get("purchasing_organization", "1000"),
                account_assignment_category=item_raw.get("account_assignment_category")
            )
            cleaned_items.append(cleaned_item)

        cleaned_req = PurchaseRequisitionSchema(
            purchase_requisition_id=payload.purchase_requisition_id,
            purchasing_group=payload.purchasing_group,
            created_by_user=payload.created_by_user,
            requisition_date=payload.requisition_date,
            overall_release_status="open",
            items=cleaned_items
        )

        # 2. Persist PurchaseRequisition and its Items in database first
        # (This allows the duplicate node to see it and compare it correctly)
        db.execute(
            text("""
                INSERT INTO PurchaseRequisition (purchase_requisition_id, purchasing_group, created_by_user, requisition_date, overall_release_status)
                VALUES (:id, :group, :user, :date, :status)
                ON CONFLICT (purchase_requisition_id) DO UPDATE SET
                    purchasing_group = EXCLUDED.purchasing_group,
                    created_by_user = EXCLUDED.created_by_user,
                    requisition_date = EXCLUDED.requisition_date,
                    overall_release_status = EXCLUDED.overall_release_status;
            """),
            {
                "id": cleaned_req.purchase_requisition_id,
                "group": cleaned_req.purchasing_group,
                "user": cleaned_req.created_by_user,
                "date": cleaned_req.requisition_date,
                "status": cleaned_req.overall_release_status
            }
        )

        # Delete existing items in case of update
        db.execute(
            text("DELETE FROM PurchaseRequisitionItem WHERE purchase_requisition_id = :id;"),
            {"id": cleaned_req.purchase_requisition_id}
        )

        for item in cleaned_items:
            if item.vendor_id:
                # Ensure vendor exists to prevent foreign key violation
                vendor_exists = db.execute(
                    text("SELECT 1 FROM Vendor WHERE vendor_id = :vendor_id;"),
                    {"vendor_id": item.vendor_id}
                ).fetchone()
                if not vendor_exists:
                    db.execute(
                        text("""
                            INSERT INTO Vendor (vendor_id, vendor_name, onboarded_date, compliance_flags, contract_expiry_date, tax_id, registered_address)
                            VALUES (:vendor_id, :vendor_name, :onboarded_date, :compliance_flags, :contract_expiry_date, :tax_id, :registered_address);
                        """),
                        {
                            "vendor_id": item.vendor_id,
                            "vendor_name": f"Simulated Vendor {item.vendor_id}",
                            "onboarded_date": date.today(),
                            "compliance_flags": [],
                            "contract_expiry_date": date.today() + timedelta(days=365),
                            "tax_id": f"TAX-{item.vendor_id}",
                            "registered_address": "Simulated Address"
                        }
                    )

            db.execute(
                text("""
                    INSERT INTO PurchaseRequisitionItem (
                        purchase_requisition_id, purchase_requisition_item, material, vendor_id, 
                        order_quantity, net_price_amount, purchasing_organization, account_assignment_category
                    )
                    VALUES (:req_id, :item_no, :material, :vendor_id, :qty, :price, :p_org, :acct);
                """),
                {
                    "req_id": item.purchase_requisition_id,
                    "item_no": item.purchase_requisition_item,
                    "material": item.material,
                    "vendor_id": item.vendor_id,
                    "qty": item.order_quantity,
                    "price": item.net_price_amount,
                    "p_org": item.purchasing_organization,
                    "acct": item.account_assignment_category
                }
            )

        db.commit()

        # 3. Run the LangGraph Triage Flow
        # We pass the schema serialized back to a dict for the intake node
        state_input = cleaned_req.model_dump()
        triage_result = run_triage_flow(state_input, db)

        # 4. Update the Requisition status based on agent verdict
        if triage_result.verdict == "auto_approve":
            db_status = "approved"
        elif triage_result.verdict == "reject":
            db_status = "rejected"
        else:
            db_status = "in_review"

        db.execute(
            text("UPDATE PurchaseRequisition SET overall_release_status = :status WHERE purchase_requisition_id = :id;"),
            {"status": db_status, "id": cleaned_req.purchase_requisition_id}
        )
        # 5. Persist TriageResult
        db.execute(
            text("""
                INSERT INTO TriageResult (
                    requisition_id, verdict, confidence_score, signals, rationale, 
                    required_approver_role, requires_named_authority, created_at, 
                    item_results, intra_pr_material_overlap
                )
                VALUES (
                    :id, :verdict, :confidence, CAST(:signals AS jsonb), :rationale, 
                    :required_role, :requires_named_auth, NOW(), 
                    CAST(:item_results AS jsonb), CAST(:intra_pr_material_overlap AS jsonb)
                )
                ON CONFLICT (requisition_id) DO UPDATE SET
                    verdict = EXCLUDED.verdict,
                    confidence_score = EXCLUDED.confidence_score,
                    signals = EXCLUDED.signals,
                    rationale = EXCLUDED.rationale,
                    required_approver_role = EXCLUDED.required_approver_role,
                    requires_named_authority = EXCLUDED.requires_named_authority,
                    created_at = NOW(),
                    item_results = EXCLUDED.item_results,
                    intra_pr_material_overlap = EXCLUDED.intra_pr_material_overlap;
            """),
            {
                "id": triage_result.requisition_id,
                "verdict": triage_result.verdict,
                "confidence": triage_result.confidence_score,
                "signals": triage_result.signals.model_dump_json(),
                "rationale": triage_result.rationale,
                "required_role": triage_result.required_approver_role,
                "requires_named_auth": triage_result.requires_named_authority,
                "item_results": json.dumps(triage_result.item_results or []),
                "intra_pr_material_overlap": json.dumps(triage_result.intra_pr_material_overlap) if triage_result.intra_pr_material_overlap else None
            }
        )
        db.commit()
        # Get fully populated record from DB
        return get_requisition_details(triage_result.requisition_id, db)

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Triage execution failed: {str(e)}"
        )


@app.get("/requisitions/queue", response_model=List[QueueItem])
def get_escalation_queue(
    purchasing_group: Optional[str] = Query(None, description="Filter by purchasing group"),
    search: Optional[str] = Query(None, description="Search by ID or creator"),
    sort_by: str = Query("date_desc", description="Sort criteria: date_desc, date_asc, value_desc, value_asc"),
    db: Session = Depends(get_db)
):
    """
    Returns pending requisitions escalated by the agent for manual human review.
    """
    query_str = """
        SELECT 
            pr.purchase_requisition_id,
            pr.purchasing_group,
            pr.created_by_user,
            pr.requisition_date,
            pr.overall_release_status,
            COALESCE(SUM(pri.order_quantity * pri.net_price_amount), 0) as total_value,
            tr.verdict,
            tr.confidence_score,
            tr.rationale,
            tr.created_at,
            tr.signals,
            tr.required_approver_role,
            tr.requires_named_authority,
            tr.overridden_by_user_id
        FROM PurchaseRequisition pr
        JOIN TriageResult tr ON pr.purchase_requisition_id = tr.requisition_id
        LEFT JOIN PurchaseRequisitionItem pri ON pr.purchase_requisition_id = pri.purchase_requisition_id
        WHERE tr.verdict = 'escalate' AND tr.human_override IS NULL
    """
    params = {}

    if purchasing_group:
        query_str += " AND pr.purchasing_group = :group"
        params["group"] = purchasing_group

    if search:
        query_str += " AND (pr.purchase_requisition_id ILIKE :search OR pr.created_by_user ILIKE :search)"
        params["search"] = f"%{search}%"

    query_str += " GROUP BY pr.purchase_requisition_id, tr.verdict, tr.confidence_score, tr.rationale, tr.created_at, tr.signals, tr.required_approver_role, tr.requires_named_authority, tr.overridden_by_user_id"

    # Sorting
    if sort_by == "date_desc":
        query_str += " ORDER BY pr.requisition_date DESC"
    elif sort_by == "date_asc":
        query_str += " ORDER BY pr.requisition_date ASC"
    elif sort_by == "value_desc":
        query_str += " ORDER BY total_value DESC"
    elif sort_by == "value_asc":
        query_str += " ORDER BY total_value ASC"

    results = db.execute(text(query_str), params).fetchall()

    queue_items = []
    for r in results:
        queue_items.append(QueueItem(
            requisition_id=r[0],
            purchasing_group=r[1],
            created_by_user=r[2],
            requisition_date=r[3],
            overall_release_status=r[4],
            total_value=float(r[5]),
            verdict=r[6],
            confidence_score=float(r[7]),
            rationale=r[8],
            created_at=r[9],
            signals=r[10],
            required_approver_role=r[11],
            requires_named_authority=r[12],
            overridden_by_user_id=str(r[13]) if r[13] else None
        ))

    return queue_items


@app.get("/requisitions/{requisition_id}", response_model=TriageResultSchema)
def get_requisition_details(requisition_id: str, db: Session = Depends(get_db)):
    """
    Retrieves full details of a specific purchase requisition triage result.
    """
    result = db.execute(
        text("""
            SELECT tr.requisition_id, tr.verdict, tr.confidence_score, tr.signals, tr.rationale, 
                   tr.human_override, tr.human_override_reason, tr.required_approver_role, 
                   tr.requires_named_authority, tr.overridden_by_user_id, tr.created_at, 
                   tr.item_results, tr.intra_pr_material_overlap,
                   COALESCE(SUM(pri.order_quantity * pri.net_price_amount), 0) as total_value,
                   pr.created_by_user, pr.requisition_date, pr.purchasing_group
            FROM TriageResult tr
            JOIN PurchaseRequisition pr ON tr.requisition_id = pr.purchase_requisition_id
            LEFT JOIN PurchaseRequisitionItem pri ON tr.requisition_id = pri.purchase_requisition_id
            WHERE tr.requisition_id = :id
            GROUP BY tr.requisition_id, tr.verdict, tr.confidence_score, tr.signals, tr.rationale, 
                     tr.human_override, tr.human_override_reason, tr.required_approver_role, 
                     tr.requires_named_authority, tr.overridden_by_user_id, tr.created_at, 
                     tr.item_results, tr.intra_pr_material_overlap,
                     pr.created_by_user, pr.requisition_date, pr.purchasing_group
        """),
        {"id": requisition_id}
    ).fetchone()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Requisition triage result {requisition_id} not found."
        )

    return TriageResultSchema(
        requisition_id=result[0],
        verdict=result[1],
        confidence_score=float(result[2]),
        signals=result[3],
        rationale=result[4],
        human_override=result[5],
        human_override_reason=result[6],
        required_approver_role=result[7],
        requires_named_authority=result[8],
        overridden_by_user_id=str(result[9]) if result[9] else None,
        created_at=result[10],
        item_results=result[11],
        intra_pr_material_overlap=result[12],
        total_value=float(result[13]) if len(result) > 13 and result[13] is not None else None,
        created_by_user=result[14] if len(result) > 14 else None,
        requisition_date=result[15] if len(result) > 15 else None,
        purchasing_group=result[16] if len(result) > 16 else None
    )


@app.post("/requisitions/{requisition_id}/override", response_model=TriageResultSchema)
def override_triage_decision(
    requisition_id: str,
    payload: HumanOverridePayload,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Applies a human manual override (approve / reject / escalate) to a triage result,
    enforcing role hierarchy policies.
    """
    # 1. Fetch TriageResult metadata
    triage_info = db.execute(
        text("SELECT required_approver_role, requires_named_authority FROM TriageResult WHERE requisition_id = :id"),
        {"id": requisition_id}
    ).fetchone()

    if not triage_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Triage result for requisition {requisition_id} not found."
        )

    req_role = triage_info[0]
    req_named_auth = triage_info[1]

    # 2. Check role hierarchy
    ROLE_RANK = {
        "analyst": 1,
        "approver": 2,
        "vp": 3,
        "cfo": 4,
        "admin": 5
    }

    user_role = current_user["role"].lower()
    required_role = req_role.lower()

    user_rank = ROLE_RANK.get(user_role, 0)
    req_rank = ROLE_RANK.get(required_role, 0)

    is_authorized = False
    if user_role == "admin":
        is_authorized = True
    elif req_named_auth:
        is_authorized = (user_rank >= req_rank)
    else:
        is_authorized = (user_rank >= ROLE_RANK["approver"])

    if not is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access Denied: Requisition requires '{req_role.upper()}' role or higher. Your role is '{user_role.upper()}'."
        )

    # 3. Map payload override to requisition status
    if payload.override_decision == "approved":
        new_status = "approved"
    elif payload.override_decision == "rejected":
        new_status = "rejected"
    else:
        new_status = "in_review"

    try:
        # Update PurchaseRequisition
        db.execute(
            text("UPDATE PurchaseRequisition SET overall_release_status = :status WHERE purchase_requisition_id = :id;"),
            {"status": new_status, "id": requisition_id}
        )

        # Update TriageResult
        db.execute(
            text("""
                UPDATE TriageResult 
                SET human_override = :decision,
                    human_override_reason = :reason,
                    overridden_by_user_id = :user_id
                WHERE requisition_id = :id;
            """),
            {
                "decision": payload.override_decision,
                "reason": payload.reason,
                "user_id": current_user["user_id"],
                "id": requisition_id
            }
        )
        db.commit()

        return get_requisition_details(requisition_id, db)

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record human override: {str(e)}"
        )




@app.get("/analytics/summary", response_model=SummaryAnalytics)
def get_analytics_summary(range: str = "30d", db: Session = Depends(get_db)):
    """
    Aggregates metrics: auto-approval rate, volume breakdown, and escalation reasons.
    Supports range parameter (7d, 30d, 90d).
    """
    from datetime import datetime, timedelta, timezone
    
    cutoff = None
    if range == "7d":
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    elif range == "30d":
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    elif range == "90d":
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    # 1. Total processed counts
    query_str = """
        SELECT 
            COUNT(*) as total_processed,
            COUNT(*) FILTER (WHERE verdict = 'auto_approve') as approved,
            COUNT(*) FILTER (WHERE verdict = 'reject') as rejected,
            COUNT(*) FILTER (WHERE verdict = 'escalate') as escalated
        FROM TriageResult
    """
    params = {}
    if cutoff:
        query_str += " WHERE created_at >= :cutoff"
        params["cutoff"] = cutoff

    totals = db.execute(text(query_str), params).fetchone()

    total_processed = totals[0] or 0
    approved = totals[1] or 0
    rejected = totals[2] or 0
    escalated = totals[3] or 0

    auto_approval_rate = (approved / total_processed) if total_processed > 0 else 0.0
    avg_time = 1.25

    # 3. Escalation reason breakdown
    reasons = {
        "price_anomaly": 0,
        "vendor_risk": 0,
        "duplicate_requisition": 0,
        "policy_compliance": 0
    }

    if total_processed > 0:
        query_sig = "SELECT signals FROM TriageResult WHERE verdict = 'escalate'"
        if cutoff:
            query_sig += " AND created_at >= :cutoff"
        
        escalated_signals = db.execute(text(query_sig), params).fetchall()

        for (sig_json,) in escalated_signals:
            if sig_json:
                if sig_json.get("price_anomaly", {}).get("has_anomaly"):
                    reasons["price_anomaly"] += 1
                if sig_json.get("vendor_risk", {}).get("is_risky"):
                    reasons["vendor_risk"] += 1
                if sig_json.get("duplicate_detection", {}).get("is_duplicate"):
                    reasons["duplicate_requisition"] += 1
                if sig_json.get("policy_compliance", {}).get("violates_policy"):
                    reasons["policy_compliance"] += 1

    # 4. Daily volume time-series
    query_daily = """
        SELECT 
            DATE(created_at) as day,
            COUNT(*) FILTER (WHERE verdict = 'auto_approve') as approved,
            COUNT(*) FILTER (WHERE verdict = 'escalate') as escalated,
            COUNT(*) FILTER (WHERE verdict = 'reject') as rejected
        FROM TriageResult
    """
    if cutoff:
        query_daily += " WHERE created_at >= :cutoff"
    query_daily += " GROUP BY day ORDER BY day ASC"
    
    daily_rows = db.execute(text(query_daily), params).fetchall()
    
    daily_volume = []
    for row in daily_rows:
        if row[0]:
            daily_volume.append({
                "date": str(row[0]),
                "approved": row[1] or 0,
                "escalated": row[2] or 0,
                "rejected": row[3] or 0
            })

    return SummaryAnalytics(
        auto_approval_rate=auto_approval_rate,
        avg_time_to_decision_seconds=avg_time,
        escalation_reason_breakdown=reasons,
        total_processed=total_processed,
        total_approved=approved,
        total_rejected=rejected,
        total_escalated=escalated,
        daily_volume=daily_volume
    )


class LoginPayload(BaseModel):
    email: str


@app.post("/auth/login")
def login_for_demo_token(payload: LoginPayload, db: Session = Depends(get_db)):
    email = payload.email.lower()
    
    # Check if there is an auth user with this email in auth.users joined with UserRole
    try:
        user_row = db.execute(
            text("""
                SELECT u.id, u.email, ur.role, ur.display_name 
                FROM auth.users u
                JOIN UserRole ur ON u.id = ur.user_id
                WHERE LOWER(u.email) = :email
            """),
            {"email": email}
        ).fetchone()
    except Exception:
        # Fallback if executing schema fails, or auth schema doesn't exist locally
        user_row = None
        
    if not user_row:
        # Fallback for offline running/mock credentials
        role_name = email.split("@")[0]
        if role_name in ["analyst", "approver", "vp", "cfo", "admin"]:
            db_role = db.execute(
                text("SELECT user_id, role, display_name FROM UserRole WHERE LOWER(role) = :role LIMIT 1"),
                {"role": role_name}
            ).fetchone()
            if db_role:
                user_id = str(db_role[0])
                role = db_role[1]
                display_name = db_role[2]
            else:
                user_id = "00000000-0000-0000-0000-000000000001"
                display_name = role_name.capitalize()
                role = role_name
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email address not registered or recognized."
            )
    else:
        user_id = str(user_row[0])
        email = user_row[1]
        role = user_row[2]
        display_name = user_row[3]
        
    # Generate token
    import jwt
    from app.auth import JWT_SECRET, JWT_ALGORITHM
    token = jwt.encode(
        {"sub": user_id, "email": email, "role": role},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user_id,
            "email": email,
            "role": role,
            "display_name": display_name
        }
    }


@app.get("/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user


@app.get("/vendors/{vendor_id}/screening", response_model=VendorScreeningCacheSchema)
def get_vendor_screening(vendor_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Returns the cached vendor screening results (sanctions check, open registry check, adverse media).
    """
    row = db.execute(
        text("""
            SELECT vendor_id, sanctions_match, sanctions_match_detail, adverse_media_flagged, adverse_media_evidence, registry_verified, registry_detail, checked_at 
            FROM VendorScreeningCache 
            WHERE vendor_id = :vendor_id
        """),
        {"vendor_id": vendor_id}
    ).fetchone()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening cache not found for vendor: {vendor_id}"
        )
        
    am_evidence = row[4]
    if isinstance(am_evidence, str):
        import json
        am_evidence = json.loads(am_evidence)
        
    return VendorScreeningCacheSchema(
        vendor_id=row[0],
        sanctions_match=row[1],
        sanctions_match_detail=row[2],
        adverse_media_flagged=row[3],
        adverse_media_evidence=am_evidence if am_evidence else {"evidence": [], "sources": []},
        registry_verified=row[5],
        registry_detail=row[6],
        checked_at=row[7]
    )


@app.post("/vendors/{vendor_id}/screening/refresh", response_model=VendorScreeningCacheSchema)
def refresh_vendor_screening(vendor_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Manually triggers a fresh Tier 2 background check for the specified vendor and updates the cache.
    """
    # Verify vendor exists
    vendor = db.execute(
        text("SELECT vendor_name FROM Vendor WHERE vendor_id = :vendor_id"),
        {"vendor_id": vendor_id}
    ).fetchone()
    
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor {vendor_id} not found."
        )
        
    # Trigger refresh
    screening = run_tier2_screening(vendor_id, vendor[0], db)
    
    return VendorScreeningCacheSchema(
        vendor_id=vendor_id,
        sanctions_match=screening["sanctions_match"],
        sanctions_match_detail=screening["sanctions_match_detail"],
        adverse_media_flagged=screening["adverse_media_flagged"],
        adverse_media_evidence=screening["adverse_media_evidence"],
        registry_verified=screening["registry_verified"],
        registry_detail=screening["registry_detail"],
        checked_at=screening["checked_at"]
    )


@app.get("/dashboard/launchpad-summary", response_model=LaunchpadSummary)
def get_launchpad_summary(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Returns counts for each launchpad tile in a single batched response.
    """
    from datetime import datetime, timedelta, timezone
    
    # 1. pending_queue_count
    pending_queue_count = db.execute(
        text("SELECT COUNT(*) FROM PurchaseRequisition WHERE overall_release_status = 'in_review'")
    ).scalar() or 0
    
    # 2. flagged_vendors_7d_count
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    flagged_vendors_7d_count = db.execute(
        text("""
            SELECT COUNT(DISTINCT vendor_id)
            FROM VendorScreeningCache
            WHERE checked_at >= :cutoff
              AND (sanctions_match = TRUE OR adverse_media_flagged = TRUE OR registry_verified = FALSE)
        """),
        {"cutoff": cutoff}
    ).scalar() or 0
    
    # 3. needs_authority_count
    needs_authority_count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM PurchaseRequisition pr
            JOIN TriageResult tr ON pr.purchase_requisition_id = tr.requisition_id
            WHERE pr.overall_release_status = 'in_review'
              AND tr.requires_named_authority = TRUE
        """)
    ).scalar() or 0
    
    return LaunchpadSummary(
        pending_queue_count=pending_queue_count,
        flagged_vendors_7d_count=flagged_vendors_7d_count,
        needs_authority_count=needs_authority_count
    )


@app.get("/vendors/screening", response_model=List[VendorScreeningCacheSchema])
def get_all_vendor_screenings(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Returns all vendor screening cache entries.
    """
    rows = db.execute(
        text("""
            SELECT vendor_id, sanctions_match, sanctions_match_detail, adverse_media_flagged, adverse_media_evidence, registry_verified, registry_detail, checked_at 
            FROM VendorScreeningCache
            ORDER BY checked_at DESC
        """)
    ).fetchall()
    
    results = []
    for row in rows:
        am_evidence = row[4]
        if isinstance(am_evidence, str):
            import json
            am_evidence = json.loads(am_evidence)
            
        results.append(
            VendorScreeningCacheSchema(
                vendor_id=row[0],
                sanctions_match=row[1],
                sanctions_match_detail=row[2],
                adverse_media_flagged=row[3],
                adverse_media_evidence=am_evidence if am_evidence else {"evidence": [], "sources": []},
                registry_verified=row[5],
                registry_detail=row[6],
                checked_at=row[7]
            )
        )
    return results


from app import agent as agent_module

@app.get("/settings", response_model=SystemSettings)
def get_settings(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Retrieves global triage config values from DB, falling back to defaults.
    """
    try:
        rows = db.execute(text("SELECT key, value FROM AgentSettings")).fetchall()
        settings_map = {row[0]: float(row[1]) for row in rows}
    except Exception:
        settings_map = {}
        
    return SystemSettings(
        auto_approval_ceiling=settings_map.get("auto_approval_ceiling", agent_module.AUTO_APPROVAL_CEILING),
        confidence_threshold=settings_map.get("confidence_threshold", agent_module.CONFIDENCE_THRESHOLD),
        price_deviation_threshold=settings_map.get("price_deviation_threshold", agent_module.PRICE_DEVIATION_THRESHOLD),
        new_vendor_threshold_days=settings_map.get("new_vendor_threshold_days", agent_module.NEW_VENDOR_THRESHOLD_DAYS),
        duplicate_window_days=settings_map.get("duplicate_window_days", agent_module.DUPLICATE_WINDOW_DAYS),
        contract_expiry_warning_days=settings_map.get("contract_expiry_warning_days", agent_module.CONTRACT_EXPIRY_WARNING_DAYS),
        vendor_screening_staleness_days=settings_map.get("vendor_screening_staleness_days", agent_module.VENDOR_SCREENING_STALENESS_DAYS),
        sanctions_match_threshold=settings_map.get("sanctions_match_threshold", agent_module.SANCTIONS_MATCH_THRESHOLD)
    )


@app.post("/settings", response_model=SystemSettings)
def update_settings(payload: SystemSettings, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Updates global triage config values in DB (gated to admin role).
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrator users can update system settings."
        )
    
    settings_dict = payload.model_dump()
    for key, val in settings_dict.items():
        if val is not None:
            try:
                db.execute(
                    text("""
                        INSERT INTO AgentSettings (key, value) VALUES (:key, :value)
                        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
                    """),
                    {"key": key, "value": val}
                )
            except Exception:
                pass
                
    try:
        db.commit()
    except Exception:
        db.rollback()
        
    # Sync module-level variables
    if payload.auto_approval_ceiling is not None:
        agent_module.AUTO_APPROVAL_CEILING = payload.auto_approval_ceiling
    if payload.confidence_threshold is not None:
        agent_module.CONFIDENCE_THRESHOLD = payload.confidence_threshold
    if payload.price_deviation_threshold is not None:
        agent_module.PRICE_DEVIATION_THRESHOLD = payload.price_deviation_threshold
    if payload.new_vendor_threshold_days is not None:
        agent_module.NEW_VENDOR_THRESHOLD_DAYS = int(payload.new_vendor_threshold_days)
    if payload.duplicate_window_days is not None:
        agent_module.DUPLICATE_WINDOW_DAYS = int(payload.duplicate_window_days)
    if payload.contract_expiry_warning_days is not None:
        agent_module.CONTRACT_EXPIRY_WARNING_DAYS = int(payload.contract_expiry_warning_days)
    if payload.vendor_screening_staleness_days is not None:
        agent_module.VENDOR_SCREENING_STALENESS_DAYS = int(payload.vendor_screening_staleness_days)
    if payload.sanctions_match_threshold is not None:
        agent_module.SANCTIONS_MATCH_THRESHOLD = payload.sanctions_match_threshold

    # Invalidate cache
    agent_module._settings_cache.clear()
    agent_module._settings_cache_time = 0.0

    return get_settings(db, current_user)


import io
import csv

@app.get("/audit-log", response_model=AuditLogResponse)
def get_audit_log(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    verdict: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieves a paginated list of audited requisitions with filters, date range, and search.
    """
    offset = (page - 1) * limit
    
    # 1. Base count query
    count_query = """
        SELECT COUNT(DISTINCT tr.requisition_id)
        FROM TriageResult tr
        JOIN PurchaseRequisition pr ON tr.requisition_id = pr.purchase_requisition_id
    """
    where_clauses = []
    params = {}
    
    if verdict:
        where_clauses.append("tr.verdict = :verdict")
        params["verdict"] = verdict
        
    if search:
        where_clauses.append("(tr.requisition_id ILIKE :search OR pr.created_by_user ILIKE :search OR tr.rationale ILIKE :search)")
        params["search"] = f"%{search}%"

    if start_date:
        where_clauses.append("DATE(tr.created_at) >= :start_date")
        params["start_date"] = start_date

    if end_date:
        where_clauses.append("DATE(tr.created_at) <= :end_date")
        params["end_date"] = end_date
        
    if where_clauses:
        count_query += " WHERE " + " AND ".join(where_clauses)
        
    total = db.execute(text(count_query), params).scalar() or 0
    
    # 2. Main paginated query
    query = """
        SELECT 
            tr.requisition_id,
            tr.verdict,
            tr.confidence_score,
            tr.required_approver_role,
            tr.requires_named_authority,
            tr.created_at,
            tr.human_override,
            tr.human_override_reason,
            pr.created_by_user,
            pr.purchasing_group,
            COALESCE(SUM(pri.order_quantity * pri.net_price_amount), 0) as total_value
        FROM TriageResult tr
        JOIN PurchaseRequisition pr ON tr.requisition_id = pr.purchase_requisition_id
        LEFT JOIN PurchaseRequisitionItem pri ON pr.purchase_requisition_id = pri.purchase_requisition_id
    """
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
        
    query += " GROUP BY tr.requisition_id, pr.purchase_requisition_id, tr.created_at"
    query += " ORDER BY tr.created_at DESC"
    query += " LIMIT :limit OFFSET :offset"
    
    params["limit"] = limit
    params["offset"] = offset
    
    rows = db.execute(text(query), params).fetchall()
    
    items = []
    for row in rows:
        items.append(AuditLogItem(
            requisition_id=row[0],
            verdict=row[1],
            confidence_score=float(row[2]),
            required_approver_role=row[3],
            requires_named_authority=row[4],
            created_at=row[5],
            human_override=row[6],
            human_override_reason=row[7],
            created_by_user=row[8],
            purchasing_group=row[9],
            total_value=float(row[10])
        ))
        
    return AuditLogResponse(items=items, total=total)


@app.get("/audit-log/export")
def export_audit_log(
    verdict: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Streams a CSV file containing all audit logs filtered by the same query parameters.
    """
    query = """
        SELECT 
            tr.requisition_id,
            tr.verdict,
            tr.confidence_score,
            tr.required_approver_role,
            tr.requires_named_authority,
            tr.created_at,
            tr.human_override,
            tr.human_override_reason,
            pr.created_by_user,
            pr.purchasing_group,
            COALESCE(SUM(pri.order_quantity * pri.net_price_amount), 0) as total_value
        FROM TriageResult tr
        JOIN PurchaseRequisition pr ON tr.requisition_id = pr.purchase_requisition_id
        LEFT JOIN PurchaseRequisitionItem pri ON pr.purchase_requisition_id = pri.purchase_requisition_id
    """
    where_clauses = []
    params = {}
    
    if verdict:
        where_clauses.append("tr.verdict = :verdict")
        params["verdict"] = verdict
        
    if search:
        where_clauses.append("(tr.requisition_id ILIKE :search OR pr.created_by_user ILIKE :search OR tr.rationale ILIKE :search)")
        params["search"] = f"%{search}%"

    if start_date:
        where_clauses.append("DATE(tr.created_at) >= :start_date")
        params["start_date"] = start_date

    if end_date:
        where_clauses.append("DATE(tr.created_at) <= :end_date")
        params["end_date"] = end_date
        
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
        
    query += " GROUP BY tr.requisition_id, pr.purchase_requisition_id, tr.created_at"
    query += " ORDER BY tr.created_at DESC"
    
    rows = db.execute(text(query), params).fetchall()

    
    def generate():
        output = io.StringIO()
        writer = csv.writer(output)
        # Header
        writer.writerow([
            "Requisition ID",
            "Verdict",
            "Confidence Score",
            "Required Approver Role",
            "Requires Named Authority",
            "Created At",
            "Human Override",
            "Human Override Reason",
            "Created By",
            "Purchasing Group",
            "Total Value"
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        
        for row in rows:
            writer.writerow([
                row[0],
                row[1],
                float(row[2]),
                row[3],
                row[4],
                row[5].isoformat() if row[5] else "",
                row[6] or "",
                row[7] or "",
                row[8],
                row[9],
                float(row[10])
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
            
    response_headers = {
        'Content-Disposition': 'attachment; filename="audit_log.csv"',
        'Content-Type': 'text/csv'
    }
    return StreamingResponse(generate(), headers=response_headers)


@app.get("/vendors")
def get_vendors(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Returns all vendors.
    """
    rows = db.execute(
        text("SELECT vendor_id, vendor_name, onboarded_date, compliance_flags, contract_expiry_date, tax_id, registered_address FROM Vendor ORDER BY vendor_name ASC")
    ).fetchall()
    
    results = []
    for row in rows:
        results.append({
            "vendor_id": row[0],
            "vendor_name": row[1],
            "onboarded_date": str(row[2]) if row[2] else "",
            "compliance_flags": row[3] or [],
            "contract_expiry_date": str(row[4]) if row[4] else "",
            "tax_id": row[5] or "",
            "registered_address": row[6] or ""
        })
    return results


@app.get("/vendors/screening-summary")
def get_vendors_screening_summary(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Returns aggregated counts of vendor screening statuses:
    - total_screened
    - flagged_sanctions
    - flagged_adverse_media
    - flagged_registry_invalid
    """
    row = db.execute(
        text("""
            SELECT 
                COUNT(*) as total_screened,
                COUNT(*) FILTER (WHERE sanctions_match = TRUE) as flagged_sanctions,
                COUNT(*) FILTER (WHERE adverse_media_flagged = TRUE) as flagged_adverse_media,
                COUNT(*) FILTER (WHERE registry_verified = FALSE) as flagged_registry_invalid
            FROM VendorScreeningCache
        """)
    ).fetchone()
    
    return {
        "total_screened": row[0] or 0,
        "flagged_sanctions": row[1] or 0,
        "flagged_adverse_media": row[2] or 0,
        "flagged_registry_invalid": row[3] or 0
    }
@app.get("/health")
def health():
    return {"status": "ok"}


