import os
import sys
import json
from datetime import date, timedelta
from sqlalchemy import text
from dotenv import load_dotenv

# Add backend directory to path so app imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import engine, SessionLocal

def load_sql_file(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        return file.read()

def seed_database():
    load_dotenv()
    print("Connecting to database...")
    db = SessionLocal()
    
    try:
        # 1. Initialize schema
        print("Executing schema.sql...")
        schema_sql = load_sql_file(os.path.join(os.path.dirname(__file__), "schema.sql"))
        # Execute the schema SQL
        statements = [stmt.strip() for stmt in schema_sql.split(";") if stmt.strip()]
        for stmt in statements:
            db.execute(text(stmt))
        db.commit()
        print("Schema initialized successfully.")

        # 2. Clear existing mock data to ensure clean seed
        print("Clearing existing data...")
        db.execute(text("TRUNCATE TABLE AgentSettings, UserRole, TriageResult, PurchaseRequisitionItem, PurchaseRequisition, PriceHistory, Vendor, SanctionsList, VendorScreeningCache CASCADE;"))
        try:
            db.execute(text("DELETE FROM auth.users WHERE email IN ('analyst@test.com', 'approver@test.com', 'vp@test.com', 'cfo@test.com', 'admin@test.com');"))
        except Exception as auth_err:
            print(f"Warning: Could not clear auth.users table (might be running locally without auth schema): {auth_err}")
        db.commit()

        # Seed Auth Users and User Roles
        print("Seeding Auth Users and Roles...")
        test_users = [
            ("a1111111-1111-1111-1111-111111111111", "analyst@test.com", "analyst", "Analyst User"),
            ("b2222222-2222-2222-2222-222222222222", "approver@test.com", "approver", "Approver User"),
            ("c3333333-3333-3333-3333-333333333333", "vp@test.com", "vp", "VP Procurement"),
            ("d4444444-4444-4444-4444-444444444444", "cfo@test.com", "cfo", "CFO User"),
            ("e5555555-5555-5555-5555-555555555555", "admin@test.com", "admin", "Administrator")
        ]
        for u_id, email, role, display_name in test_users:
            try:
                # Check if user exists in auth.users
                user_exists = db.execute(
                    text("SELECT id FROM auth.users WHERE LOWER(email) = :email"),
                    {"email": email.lower()}
                ).fetchone()
                
                if not user_exists:
                    db.execute(
                        text("""
                            INSERT INTO auth.users (id, email, encrypted_password, email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at, role, aud)
                            VALUES (
                                :id, 
                                :email, 
                                '$2a$10$wR/w6zHh9oMhFf73r74JdeNqZ5c5y1T5LzF.7758.z9b5523F465y', 
                                NOW(), 
                                '{"provider":"email","providers":["email"]}', 
                                CAST(:user_metadata AS jsonb), 
                                NOW(), 
                                NOW(), 
                                'authenticated', 
                                'authenticated'
                            );
                        """),
                        {
                            "id": u_id,
                            "email": email,
                            "user_metadata": json.dumps({"display_name": display_name})
                        }
                    )
                else:
                    db.execute(
                        text("""
                            UPDATE auth.users 
                            SET raw_user_meta_data = CAST(:user_metadata AS jsonb),
                                updated_at = NOW()
                            WHERE LOWER(email) = :email;
                        """),
                        {
                            "email": email.lower(),
                            "user_metadata": json.dumps({"display_name": display_name})
                        }
                    )
                db.commit()
            except Exception as auth_ins_err:
                print(f"Warning: auth.users management failed for {email}: {auth_ins_err}")
                db.rollback()
                
            try:
                # Insert into UserRole
                db.execute(
                    text("""
                        INSERT INTO UserRole (user_id, role, display_name)
                        VALUES (:id, :role, :display_name)
                        ON CONFLICT (user_id) DO UPDATE SET
                            role = EXCLUDED.role,
                            display_name = EXCLUDED.display_name;
                    """),
                    {
                        "id": u_id,
                        "role": role,
                        "display_name": display_name
                    }
                )
                db.commit()
            except Exception as role_ins_err:
                print(f"Warning: UserRole management failed for {email}: {role_ins_err}")
                db.rollback()
        # 2.5 Seed AgentSettings
        print("Seeding AgentSettings...")
        settings_defaults = [
            ("auto_approval_ceiling", 5000.0, "Requisition value threshold above which auto-approval is disabled and escalation is required"),
            ("price_deviation_threshold", 0.15, "Allowed percentage deviation from historical average price before flagging an anomaly"),
            ("new_vendor_threshold_days", 90.0, "Number of days since onboarding under which a vendor is considered 'new'"),
            ("duplicate_window_days", 30.0, "Number of days around the requisition date to search for potential duplicate requisitions"),
            ("confidence_threshold", 0.80, "Minimum confidence score (0.0 to 1.0) required for auto-approval"),
            ("contract_expiry_warning_days", 30.0, "Number of days prior to contract expiry to flag contract expiry warnings"),
            ("vendor_screening_staleness_days", 30.0, "Number of days before cached vendor screenings are considered stale"),
            ("sanctions_match_threshold", 90.0, "Fuzzy match similarity threshold percentage against sanctions list name entries")
        ]
        for key, val, desc in settings_defaults:
            db.execute(
                text("""
                    INSERT INTO AgentSettings (key, value, description)
                    VALUES (:key, :value, :description)
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        description = EXCLUDED.description;
                """),
                {"key": key, "value": val, "description": desc}
            )
        db.commit()

        # 3. Seed Vendors
        print("Seeding Vendors...")
        vendors = [
            # ID, Name, Onboarded Date, Compliance Flags, Expiry Date, Tax ID, Registered Address
            ("VEND001", "Global Office Supplies", date.today() - timedelta(days=730), [], date.today() + timedelta(days=365), "TAX-100001", "100 Office Parkway, Scranton, PA"),
            ("VEND002", "Apex Tech Solutions", date.today() - timedelta(days=10), ["late_delivery_history"], date.today() + timedelta(days=120), "TAX-200002", None), # Missing address
            ("VEND003", "Standard Industrial Corp", date.today() - timedelta(days=1000), ["pending_audit"], date.today() + timedelta(days=45), None, "456 Factory Way, Detroit, MI"), # Missing tax ID
            ("VEND004", "Banned Electronics Ltd", date.today() - timedelta(days=1800), ["sanctioned_entity"], date.today() + timedelta(days=500), "TAX-400004", "789 Sanction St, London, UK")
        ]
        for v_id, name, onboarded, flags, expiry, tax, addr in vendors:
            db.execute(
                text("""
                    INSERT INTO Vendor (vendor_id, vendor_name, onboarded_date, compliance_flags, contract_expiry_date, tax_id, registered_address)
                    VALUES (:vendor_id, :vendor_name, :onboarded_date, :compliance_flags, :contract_expiry_date, :tax_id, :registered_address)
                """),
                {
                    "vendor_id": v_id,
                    "vendor_name": name,
                    "onboarded_date": onboarded,
                    "compliance_flags": flags,
                    "contract_expiry_date": expiry,
                    "tax_id": tax,
                    "registered_address": addr
                }
            )
        db.commit()

        # Seed SanctionsList
        print("Seeding SanctionsList...")
        sanctions = [
            ("SANC001", "Apex Technology Solutions LLC", "OFAC_SDN", date.today()),
            ("SANC002", "Banned Electronics Co., Ltd.", "EU_CONSOLIDATED", date.today()),
            ("SANC003", "Cyber Warfare LLC", "OFAC_SDN", date.today()),
            ("SANC004", "North Aviation Export", "OFAC_SDN", date.today()),
            ("SANC005", "Gold & Silver Smelters Corp", "EU_CONSOLIDATED", date.today()),
            ("SANC006", "Global Shipments Iran", "OFAC_SDN", date.today()),
            ("SANC007", "Kovach Arms Consortium", "EU_CONSOLIDATED", date.today()),
            ("SANC008", "Velasquez Mercenaries Group", "OFAC_SDN", date.today()),
            ("SANC009", "Red Star Industrial Holdings", "OFAC_SDN", date.today()),
            ("SANC010", "Turing Hackers Syndicate", "EU_CONSOLIDATED", date.today()),
            ("SANC011", "Far East Trade & Transport", "OFAC_SDN", date.today()),
            ("SANC012", "Sudan Gold Mining Corp", "OFAC_SDN", date.today()),
            ("SANC013", "Eastern Bloc Electronics", "EU_CONSOLIDATED", date.today()),
            ("SANC014", "Orion Security Solutions Ltd", "OFAC_SDN", date.today()),
            ("SANC015", "Minsk Heavy Machinery", "EU_CONSOLIDATED", date.today()),
            ("SANC016", "Siberian Steel Export", "OFAC_SDN", date.today()),
            ("SANC017", "Tehran Chemical Industries", "OFAC_SDN", date.today()),
            ("SANC018", "Southern Maritime Logistics", "EU_CONSOLIDATED", date.today()),
            ("SANC019", "Caspian Petroleum Trading", "OFAC_SDN", date.today()),
            ("SANC020", "Delta Aero Parts Ltd", "OFAC_SDN", date.today()),
            ("SANC021", "Volga River Logistics", "EU_CONSOLIDATED", date.today()),
            ("SANC022", "Levant Trade Corporation", "OFAC_SDN", date.today()),
            ("SANC023", "Euphrates Import Export Ltd", "EU_CONSOLIDATED", date.today()),
            ("SANC024", "Pacific Shipping & Trade LLC", "OFAC_SDN", date.today()),
            ("SANC025", "Atlantic Cargo Services", "EU_CONSOLIDATED", date.today())
        ]
        for entry_id, listed_name, source, snapshot_date in sanctions:
            db.execute(
                text("""
                    INSERT INTO SanctionsList (entry_id, listed_name, list_source, snapshot_date)
                    VALUES (:entry_id, :listed_name, :list_source, :snapshot_date)
                """),
                {
                    "entry_id": entry_id,
                    "listed_name": listed_name,
                    "list_source": source,
                    "snapshot_date": snapshot_date
                }
            )
        db.commit()

        # 4. Seed Price History
        print("Seeding Price History...")
        price_history = [
            ("MAT_LAPTOP_001", "VEND001", 1200.0, date.today() - timedelta(days=30)),
            ("MAT_CHAIR_002", "VEND003", 350.0, date.today() - timedelta(days=45)),
            ("MAT_DESK_003", "VEND001", 500.0, date.today() - timedelta(days=60))
        ]
        for material, vendor_id, avg_price, last_date in price_history:
            db.execute(
                text("""
                    INSERT INTO PriceHistory (material, vendor_id, historical_avg_price, last_purchase_date)
                    VALUES (:material, :vendor_id, :historical_avg_price, :last_purchase_date)
                """),
                {
                    "material": material,
                    "vendor_id": vendor_id,
                    "historical_avg_price": avg_price,
                    "last_purchase_date": last_date
                }
            )
        db.commit()

        # 5. Seed Purchase Requisitions
        print("Seeding Purchase Requisitions...")
        reqs = [
            # ID, Group, User, Date, Status
            ("REQ_001", "P01", "JSMITH", date.today() - timedelta(days=3), "open"),
            ("REQ_002", "P01", "ALICEW", date.today() - timedelta(days=2), "open"),
            ("REQ_003", "P02", "ALICEW", date.today() - timedelta(days=1), "open"),
            ("REQ_004", "P01", "BOBM", date.today() - timedelta(days=10), "open"),
            ("REQ_005", "P02", "CHARLIEK", date.today(), "open"),
            ("REQ_006", "P01", "JSMITH", date.today(), "open"),
            ("REQ_007", "P01", "BOBM", date.today(), "open"),
            ("REQ_008", "P01", "JSMITH", date.today(), "open")
        ]
        for req_id, group, user, req_date, status in reqs:
            db.execute(
                text("""
                    INSERT INTO PurchaseRequisition (purchase_requisition_id, purchasing_group, created_by_user, requisition_date, overall_release_status)
                    VALUES (:id, :group, :user, :date, :status)
                """),
                {
                    "id": req_id,
                    "group": group,
                    "user": user,
                    "date": req_date,
                    "status": status
                }
            )
        db.commit()

        # 6. Seed Purchase Requisition Items
        print("Seeding Purchase Requisition Items...")
        items = [
            # REQ_001: Low risk (Total 2440, below 5000 ceiling, deviation = 1.6%)
            ("REQ_001", "00010", "MAT_LAPTOP_001", "VEND001", 2, 1220.0, "1000", "K"),
            # REQ_002: Price Anomaly (Deviation = 25%, above 15% threshold)
            ("REQ_002", "00010", "MAT_LAPTOP_001", "VEND001", 1, 1500.0, "1000", "K"),
            # REQ_003: New/Risky Vendor (onboarded 10 days ago, compliance flags)
            ("REQ_003", "00010", "MAT_LAPTOP_001", "VEND002", 1, 1190.0, "1000", "K"),
            # REQ_004: Duplicate Requisition Part A (10 days ago, P01, Standard chair)
            ("REQ_004", "00010", "MAT_CHAIR_002", "VEND003", 10, 360.0, "1000", "K"),
            # REQ_005: Duplicate Requisition Part B (Today, P02, Standard chair - same material, within 30 days)
            ("REQ_005", "00010", "MAT_CHAIR_002", "VEND003", 10, 360.0, "1000", "K"),
            # REQ_006: Hard Policy Block (Banned Vendor, sanctioned entity)
            ("REQ_006", "00010", "MAT_BANNED_001", "VEND004", 5, 100.0, "1000", "K"),
            # REQ_007: Value Above Ceiling (Total 12000, above 5000 ceiling)
            ("REQ_007", "00010", "MAT_LAPTOP_001", "VEND001", 10, 1200.0, "1000", "K"),
            # REQ_008: Multi-item, multi-vendor overlap on MAT_LAPTOP_001
            ("REQ_008", "00010", "MAT_LAPTOP_001", "VEND001", 1, 1200.0, "1000", "K"),
            ("REQ_008", "00020", "MAT_LAPTOP_001", "VEND002", 1, 1190.0, "1000", "K"),
            ("REQ_008", "00030", "MAT_CHAIR_002", "VEND003", 5, 360.0, "1000", "K")
        ]
        for req_id, item_no, mat, v_id, qty, price, p_org, acct in items:
            db.execute(
                text("""
                    INSERT INTO PurchaseRequisitionItem (purchase_requisition_id, purchase_requisition_item, material, vendor_id, order_quantity, net_price_amount, purchasing_organization, account_assignment_category)
                    VALUES (:req_id, :item_no, :material, :vendor_id, :qty, :price, :p_org, :acct)
                """),
                {
                    "req_id": req_id,
                    "item_no": item_no,
                    "material": mat,
                    "vendor_id": v_id,
                    "qty": qty,
                    "price": price,
                    "p_org": p_org,
                    "acct": acct
                }
            )
        db.commit()

        # 7. Triage each seeded requisition to populate TriageResult
        print("Triage processing seeded requisitions...")
        from app.agent import run_triage_flow
        
        for req_id, group, user, req_date, status in reqs:
            # Query the items we just inserted
            item_rows = db.execute(
                text("""
                    SELECT purchase_requisition_id, purchase_requisition_item, material, vendor_id, 
                           order_quantity, net_price_amount, purchasing_organization, account_assignment_category
                    FROM PurchaseRequisitionItem 
                    WHERE purchase_requisition_id = :id
                """),
                {"id": req_id}
            ).fetchall()
            
            cleaned_items = []
            for item in item_rows:
                cleaned_items.append({
                    "purchase_requisition_id": item[0],
                    "purchase_requisition_item": item[1],
                    "material": item[2],
                    "vendor_id": item[3],
                    "order_quantity": float(item[4]),
                    "net_price_amount": float(item[5]),
                    "purchasing_organization": item[6],
                    "account_assignment_category": item[7]
                })
                
            state_input = {
                "purchase_requisition_id": req_id,
                "purchasing_group": group,
                "created_by_user": user,
                "requisition_date": req_date.isoformat(),
                "overall_release_status": status,
                "items": cleaned_items
            }
            
            # Execute triage
            triage_result = run_triage_flow(state_input, db)
            
            # Update requisition release status
            if triage_result.verdict == "auto_approve":
                db_status = "approved"
            elif triage_result.verdict == "reject":
                db_status = "rejected"
            else:
                db_status = "in_review"
                
            db.execute(
                text("UPDATE PurchaseRequisition SET overall_release_status = :status WHERE purchase_requisition_id = :id;"),
                {"status": db_status, "id": req_id}
            )
            
            # Insert TriageResult
            db.execute(
                text("""
                    INSERT INTO TriageResult (
                        requisition_id, verdict, confidence_score, signals, rationale, 
                        required_approver_role, requires_named_authority, created_at,
                        item_results, intra_pr_material_overlap
                    )
                    VALUES (
                        :id, :verdict, :confidence, CAST(:signals AS jsonb), :rationale, 
                        :required_role, :requires_named, NOW(),
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
                    "requires_named": triage_result.requires_named_authority,
                    "item_results": json.dumps(triage_result.item_results or []),
                    "intra_pr_material_overlap": json.dumps(triage_result.intra_pr_material_overlap) if triage_result.intra_pr_material_overlap else None
                }
            )
        db.commit()

        print("Database seeded and triage outcomes processed successfully with all scenarios!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
