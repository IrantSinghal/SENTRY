import os
import sys
import json
from datetime import date, timedelta, datetime, timezone
from dotenv import load_dotenv

# Load environment variables FIRST before importing app.db
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(backend_dir, ".env")
load_dotenv(dotenv_path=env_path)
load_dotenv()

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import text
from app.db import engine, SessionLocal

def load_sql_file(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        return file.read()

def seed_database():
    print("Connecting to database...")
    db = SessionLocal()
    
    try:
        # 1. Initialize schema
        print("Executing schema.sql...")
        schema_sql = load_sql_file(os.path.join(os.path.dirname(__file__), "schema.sql"))
        statements = [stmt.strip() for stmt in schema_sql.split(";") if stmt.strip()]
        for stmt in statements:
            db.execute(text(stmt))
        db.commit()
        print("Schema initialized successfully.")

        # 2. Clear existing data for clean idempotent seed
        print("Clearing existing data...")
        db.execute(text("TRUNCATE TABLE AgentSettings, UserRole, TriageResult, PurchaseRequisitionItem, PurchaseRequisition, PriceHistory, VendorScreeningCache, Vendor, SanctionsList CASCADE;"))
        try:
            db.execute(text("DELETE FROM auth.users WHERE email IN ('analyst@test.com', 'approver@test.com', 'vp@test.com', 'cfo@test.com', 'admin@test.com');"))
        except Exception as auth_err:
            print(f"Warning: Could not clear auth.users table (running locally without auth schema): {auth_err}")
        db.commit()

        # 3. Seed Auth Users and User Roles
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
                print(f"Warning: auth.users management skipped for {email}: {auth_ins_err}")
                db.rollback()
                
            try:
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

        # 4. Seed AgentSettings
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

        # 5. Seed 35 Synthetic Vendors (with 5 Near-Duplicate Pairs)
        print("Seeding 35 Synthetic Vendors...")
        today = date.today()
        vendors = [
            # ID, Name, Onboarded Date, Compliance Flags, Expiry Date, Tax ID, Registered Address
            ("VEND001", "Global Office Supplies", today - timedelta(days=730), [], today + timedelta(days=365), "TAX-100001", "100 Office Parkway, Scranton, PA"),
            ("VEND002", "Apex Tech Solutions", today - timedelta(days=10), ["late_delivery_history"], today + timedelta(days=120), "TAX-200002", "200 Tech Blvd, San Jose, CA"),
            ("VEND003", "Standard Industrial Corp", today - timedelta(days=1000), ["pending_audit"], today + timedelta(days=45), "TAX-300003", "456 Factory Way, Detroit, MI"),
            ("VEND004", "Banned Electronics Ltd", today - timedelta(days=1800), ["sanctioned_entity"], today + timedelta(days=500), "TAX-400004", "789 Sanction St, London, UK"),
            ("VEND005", "Acme Logistics Corp", today - timedelta(days=500), [], today + timedelta(days=200), "TAX-500005", "500 Logistics Way, Chicago, IL"),
            ("VEND006", "Nexus Cloud Services", today - timedelta(days=300), [], today + timedelta(days=400), "TAX-600006", "600 Cloud Plaza, Seattle, WA"),
            ("VEND007", "Vanguard Software Solutions", today - timedelta(days=150), ["adverse_press"], today + timedelta(days=180), "TAX-700007", "700 Innovation Way, Austin, TX"),
            ("VEND008", "Pinnacle Paper & Office", today - timedelta(days=800), [], today + timedelta(days=300), "TAX-800008", "800 Paper St, Atlanta, GA"),
            ("VEND009", "Beacon Hardware Supplies", today - timedelta(days=600), [], today + timedelta(days=250), "TAX-900009", "900 Industrial Ave, Cleveland, OH"),
            ("VEND010", "Titan Heavy Equipment", today - timedelta(days=400), [], today + timedelta(days=150), "TAX-100010", "1000 Heavy Machinery Rd, Houston, TX"),
            ("VEND011", "Cascade IT Networking", today - timedelta(days=250), [], today + timedelta(days=320), "TAX-110011", "1100 Network Dr, Portland, OR"),
            ("VEND012", "Summit Industrial Tools", today - timedelta(days=700), [], today + timedelta(days=450), "TAX-120012", "1200 Tool Park, Pittsburgh, PA"),
            ("VEND013", "Horizon Freight & Logistics", today - timedelta(days=350), [], today + timedelta(days=210), "TAX-130013", "1300 Port Rd, Newark, NJ"),
            ("VEND014", "Sterling Office Furniture", today - timedelta(days=900), [], today + timedelta(days=600), "TAX-140014", "1400 Furniture Way, Grand Rapids, MI"),
            ("VEND015", "Crestview Cyber Security", today - timedelta(days=120), [], today + timedelta(days=280), "TAX-150015", "1500 Cyber Center, Reston, VA"),
            ("VEND016", "Quantum Data Systems", today - timedelta(days=450), [], today + timedelta(days=365), "TAX-160016", "1600 Data Way, Cambridge, MA"),
            ("VEND017", "Evergreen Cleaning Services", today - timedelta(days=650), [], today + timedelta(days=190), "TAX-170017", "1700 Green St, Denver, CO"),
            ("VEND018", "Precision Machining Corp", today - timedelta(days=850), [], today + timedelta(days=500), "TAX-180018", "1800 Precision Way, Milwaukee, WI"),
            ("VEND019", "Ironclad Security Operations", today - timedelta(days=200), [], today + timedelta(days=140), "TAX-190019", "1900 Defense Rd, Alexandria, VA"),
            ("VEND020", "Vortex Telecom Solutions", today - timedelta(days=550), [], today + timedelta(days=410), "TAX-200020", "2000 Telecom Blvd, Dallas, TX"),
            ("VEND021", "Atlas Fleet Management", today - timedelta(days=750), [], today + timedelta(days=300), "TAX-210021", "2100 Transport Way, Memphis, TN"),
            ("VEND022", "Silverline Packaging Corp", today - timedelta(days=320), [], today + timedelta(days=220), "TAX-220022", "2200 Box Lane, Louisville, KY"),
            ("VEND023", "Alpha Office Technologies", today - timedelta(days=600), [], today + timedelta(days=350), "TAX-230023", "2300 Tech Park, Phoenix, AZ"),
            ("VEND024", "Beta Electronics Components", today - timedelta(days=480), [], today + timedelta(days=180), "TAX-240024", "2400 Circuit St, San Jose, CA"),
            ("VEND025", "Gamma Chemical Distributors", today - timedelta(days=1100), [], today + timedelta(days=520), "TAX-250025", "2500 Chem Ave, Baton Rouge, LA"),
            ("VEND026", "Delta Engineering Services", today - timedelta(days=390), [], today + timedelta(days=270), "TAX-260026", "2600 Eng Plaza, San Diego, CA"),
            ("VEND027", "Epsilon Facility Management", today - timedelta(days=620), [], today + timedelta(days=310), "TAX-270027", "2700 Services Rd, Charlotte, NC"),
            ("VEND028", "Zeta Storage Systems", today - timedelta(days=810), [], today + timedelta(days=440), "TAX-280028", "2800 Logistics Dr, Indianapolis, IN"),
            ("VEND029", "Eta Research Labs", today - timedelta(days=290), [], today + timedelta(days=230), "TAX-290029", "2900 Science Park, Raleigh, NC"),
            
            # --- INTENTIONAL NEAR-DUPLICATE PAIRS ---
            # Pair 1: Near-duplicate of VEND002 (Apex Tech Solutions) -> SANC001 match
            ("VEND030", "Apex Technology Solutions LLC", today - timedelta(days=15), ["name_similarity_sanctions"], today + timedelta(days=100), "TAX-300030", "205 Tech Blvd Suite B, San Jose, CA"),
            # Pair 2: Near-duplicate of VEND001 (Global Office Supplies)
            ("VEND031", "Global Office Supplies Inc", today - timedelta(days=45), [], today + timedelta(days=300), "TAX-310031", "102 Office Parkway, Scranton, PA"),
            # Pair 3: Near-duplicate of VEND004 (Banned Electronics Ltd) -> SANC002 match
            ("VEND032", "Banned Electronics Co Ltd", today - timedelta(days=1500), ["sanctioned_entity"], today + timedelta(days=400), "TAX-320032", "791 Sanction St, London, UK"),
            # Pair 4: Near-duplicate of VEND003 (Standard Industrial Corp)
            ("VEND033", "Standard Industrial Group LLC", today - timedelta(days=80), ["pending_audit"], today + timedelta(days=90), "TAX-330033", "458 Factory Way, Detroit, MI"),
            # Pair 5: Near-duplicate of VEND005 (Acme Logistics Corp)
            ("VEND034", "Acme Logistics International", today - timedelta(days=60), [], today + timedelta(days=150), "TAX-340034", "505 Logistics Way, Chicago, IL")
        ]

        for v_id, name, onboarded, flags, expiry, tax, addr in vendors:
            db.execute(
                text("""
                    INSERT INTO Vendor (vendor_id, vendor_name, onboarded_date, compliance_flags, contract_expiry_date, tax_id, registered_address)
                    VALUES (:vendor_id, :vendor_name, :onboarded_date, :compliance_flags, :contract_expiry_date, :tax_id, :registered_address)
                    ON CONFLICT (vendor_id) DO UPDATE SET
                        vendor_name = EXCLUDED.vendor_name,
                        onboarded_date = EXCLUDED.onboarded_date,
                        compliance_flags = EXCLUDED.compliance_flags,
                        contract_expiry_date = EXCLUDED.contract_expiry_date,
                        tax_id = EXCLUDED.tax_id,
                        registered_address = EXCLUDED.registered_address;
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

        # 6. Seed SanctionsList
        print("Seeding SanctionsList...")
        sanctions = [
            ("SANC001", "Apex Technology Solutions LLC", "OFAC_SDN", today),
            ("SANC002", "Banned Electronics Co., Ltd.", "EU_CONSOLIDATED", today),
            ("SANC003", "Cyber Warfare LLC", "OFAC_SDN", today),
            ("SANC004", "North Aviation Export", "OFAC_SDN", today),
            ("SANC005", "Gold & Silver Smelters Corp", "EU_CONSOLIDATED", today),
            ("SANC006", "Global Shipments Iran", "OFAC_SDN", today),
            ("SANC007", "Kovach Arms Consortium", "EU_CONSOLIDATED", today),
            ("SANC008", "Velasquez Mercenaries Group", "OFAC_SDN", today),
            ("SANC009", "Red Star Industrial Holdings", "OFAC_SDN", today),
            ("SANC010", "Turing Hackers Syndicate", "EU_CONSOLIDATED", today),
            ("SANC011", "Far East Trade & Transport", "OFAC_SDN", today),
            ("SANC012", "Sudan Gold Mining Corp", "OFAC_SDN", today),
            ("SANC013", "Eastern Bloc Electronics", "EU_CONSOLIDATED", today),
            ("SANC014", "Orion Security Solutions Ltd", "OFAC_SDN", today),
            ("SANC015", "Minsk Heavy Machinery", "EU_CONSOLIDATED", today),
            ("SANC016", "Siberian Steel Export", "OFAC_SDN", today),
            ("SANC017", "Tehran Chemical Industries", "OFAC_SDN", today),
            ("SANC018", "Southern Maritime Logistics", "EU_CONSOLIDATED", today),
            ("SANC019", "Caspian Petroleum Trading", "OFAC_SDN", today),
            ("SANC020", "Delta Aero Parts Ltd", "OFAC_SDN", today),
            ("SANC021", "Volga River Logistics", "EU_CONSOLIDATED", today),
            ("SANC022", "Levant Trade Corporation", "OFAC_SDN", today),
            ("SANC023", "Euphrates Import Export Ltd", "EU_CONSOLIDATED", today),
            ("SANC024", "Pacific Shipping & Trade LLC", "OFAC_SDN", today),
            ("SANC025", "Atlantic Cargo Services", "EU_CONSOLIDATED", today)
        ]
        for entry_id, listed_name, source, snapshot_date in sanctions:
            db.execute(
                text("""
                    INSERT INTO SanctionsList (entry_id, listed_name, list_source, snapshot_date)
                    VALUES (:entry_id, :listed_name, :list_source, :snapshot_date)
                    ON CONFLICT (entry_id) DO UPDATE SET
                        listed_name = EXCLUDED.listed_name,
                        list_source = EXCLUDED.list_source,
                        snapshot_date = EXCLUDED.snapshot_date;
                """),
                {
                    "entry_id": entry_id,
                    "listed_name": listed_name,
                    "list_source": source,
                    "snapshot_date": snapshot_date
                }
            )
        db.commit()

        # 7. Pre-populate VendorScreeningCache
        print("Seeding VendorScreeningCache...")
        now_utc = datetime.now(timezone.utc)
        for v_id, name, onboarded, flags, expiry, tax, addr in vendors:
            is_sanctioned = (v_id in ["VEND004", "VEND030", "VEND032"])
            sanction_detail = "Matched against OFAC/EU Sanctions list" if is_sanctioned else None
            is_adverse_media = ("adverse_press" in flags or v_id == "VEND007")
            am_evidence = {
                "evidence": ["Vendor involved in ongoing regulatory inquiry regarding export compliance."] if is_adverse_media else [],
                "sources": ["https://compliance-news.example.com/audit-report"] if is_adverse_media else []
            }
            registry_verified = False if tax is None or v_id in ["VEND003", "VEND033"] else True
            registry_detail = "Tax ID missing or unverified" if not registry_verified else "Verified active business registry"

            db.execute(
                text("""
                    INSERT INTO VendorScreeningCache (vendor_id, sanctions_match, sanctions_match_detail, adverse_media_flagged, adverse_media_evidence, registry_verified, registry_detail, checked_at)
                    VALUES (:vendor_id, :sanctions_match, :sanctions_match_detail, :adverse_media_flagged, CAST(:adverse_media_evidence AS jsonb), :registry_verified, :registry_detail, :checked_at)
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
                    "vendor_id": v_id,
                    "sanctions_match": is_sanctioned,
                    "sanctions_match_detail": sanction_detail,
                    "adverse_media_flagged": is_adverse_media,
                    "adverse_media_evidence": json.dumps(am_evidence),
                    "registry_verified": registry_verified,
                    "registry_detail": registry_detail,
                    "checked_at": now_utc
                }
            )
        db.commit()

        # 8. Seed Price History
        print("Seeding Price History...")
        price_history = [
            ("MAT_LAPTOP_001", "VEND001", 1200.0, today - timedelta(days=30)),
            ("MAT_LAPTOP_001", "VEND002", 1190.0, today - timedelta(days=15)),
            ("MAT_LAPTOP_001", "VEND031", 1205.0, today - timedelta(days=20)),
            ("MAT_CHAIR_002", "VEND003", 350.0, today - timedelta(days=45)),
            ("MAT_CHAIR_002", "VEND033", 355.0, today - timedelta(days=40)),
            ("MAT_DESK_003", "VEND001", 500.0, today - timedelta(days=60)),
            ("MAT_SERVER_004", "VEND006", 4500.0, today - timedelta(days=90)),
            ("MAT_MONITOR_005", "VEND008", 250.0, today - timedelta(days=35)),
            ("MAT_SOFTWARE_006", "VEND007", 2000.0, today - timedelta(days=50)),
            ("MAT_PRINTER_008", "VEND001", 850.0, today - timedelta(days=70))
        ]
        for material, vendor_id, avg_price, last_date in price_history:
            db.execute(
                text("""
                    INSERT INTO PriceHistory (material, vendor_id, historical_avg_price, last_purchase_date)
                    VALUES (:material, :vendor_id, :historical_avg_price, :last_purchase_date)
                    ON CONFLICT (material, vendor_id) DO UPDATE SET
                        historical_avg_price = EXCLUDED.historical_avg_price,
                        last_purchase_date = EXCLUDED.last_purchase_date;
                """),
                {
                    "material": material,
                    "vendor_id": vendor_id,
                    "historical_avg_price": avg_price,
                    "last_purchase_date": last_date
                }
            )
        db.commit()

        # 9. Seed Purchase Requisitions
        print("Seeding Purchase Requisitions...")
        reqs = [
            # ID, Group, User, Date, Status
            ("REQ_001", "P01", "JSMITH", today - timedelta(days=3), "open"),
            ("REQ_002", "P01", "ALICEW", today - timedelta(days=2), "open"),
            ("REQ_003", "P02", "ALICEW", today - timedelta(days=1), "open"),
            ("REQ_004", "P01", "BOBM", today - timedelta(days=10), "open"),
            ("REQ_005", "P02", "CHARLIEK", today, "open"),
            ("REQ_006", "P01", "JSMITH", today, "open"),
            ("REQ_007", "P01", "BOBM", today, "open"),
            ("REQ_008", "P01", "JSMITH", today, "open"),
            ("REQ_009", "P02", "EXECUTIVE_VP", today - timedelta(days=4), "open"),
            ("REQ_010", "P01", "EXECUTIVE_CFO", today - timedelta(days=5), "open"),
            ("REQ_011", "P02", "IT_ADMIN", today - timedelta(days=6), "open"),
            ("REQ_012", "P03", "FACILITIES_MGR", today - timedelta(days=7), "open"),
            ("REQ_013", "P02", "DEV_LEAD", today - timedelta(days=8), "open"),
            ("REQ_014", "P01", "JSMITH", today - timedelta(days=9), "open")
        ]
        for req_id, group, user, req_date, status in reqs:
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
                    "id": req_id,
                    "group": group,
                    "user": user,
                    "date": req_date,
                    "status": status
                }
            )
        db.commit()

        # 10. Seed Requisition Line Items
        print("Seeding Requisition Line Items...")
        pr_items = [
            # REQ_001: Low risk auto-approve ($2,440)
            ("REQ_001", "00010", "MAT_LAPTOP_001", "VEND001", 2, 1220.0, "1000", "K"),
            
            # REQ_002: Price Anomaly ($1,650 vs $1,200 baseline)
            ("REQ_002", "00010", "MAT_LAPTOP_001", "VEND001", 1, 1650.0, "1000", "K"),
            
            # REQ_003: New/Risky Vendor (VEND002 onboarded 10 days ago)
            ("REQ_003", "00010", "MAT_LAPTOP_001", "VEND002", 1, 1190.0, "1000", "K"),
            
            # REQ_004: Duplicate Part A (10 days ago)
            ("REQ_004", "00010", "MAT_CHAIR_002", "VEND003", 10, 360.0, "1000", "K"),
            
            # REQ_005: Duplicate Part B (Today - same material within 30 days)
            ("REQ_005", "00010", "MAT_CHAIR_002", "VEND003", 10, 360.0, "1000", "K"),
            
            # REQ_006: Hard Policy Block (Banned Vendor VEND004)
            ("REQ_006", "00010", "MAT_BANNED_001", "VEND004", 5, 100.0, "1000", "K"),
            
            # REQ_007: Above $5,000 Ceiling ($12,000)
            ("REQ_007", "00010", "MAT_LAPTOP_001", "VEND001", 10, 1200.0, "1000", "K"),
            
            # REQ_008: Multi-item multi-vendor overlap on MAT_LAPTOP_001
            ("REQ_008", "00010", "MAT_LAPTOP_001", "VEND001", 1, 1200.0, "1000", "K"),
            ("REQ_008", "00020", "MAT_LAPTOP_001", "VEND002", 1, 1190.0, "1000", "K"),
            ("REQ_008", "00030", "MAT_CHAIR_002", "VEND003", 5, 360.0, "1000", "K"),

            # REQ_009: High-value executive VP PR ($28,500)
            ("REQ_009", "00010", "MAT_SERVER_004", "VEND006", 6, 4750.0, "1000", "K"),

            # REQ_010: Executive CFO Tier PR ($48,000)
            ("REQ_010", "00010", "MAT_SERVER_004", "VEND006", 10, 4800.0, "1000", "K"),

            # REQ_011: Clean IT Requisition ($4,500)
            ("REQ_011", "00010", "MAT_SERVER_004", "VEND006", 1, 4500.0, "1000", "K"),

            # REQ_012: Clean Facilities Requisition ($1,500)
            ("REQ_012", "00010", "MAT_DESK_003", "VEND001", 3, 500.0, "1000", "K"),

            # REQ_013: Adverse Press Vendor VEND007 ($2,000)
            ("REQ_013", "00010", "MAT_SOFTWARE_006", "VEND007", 1, 2000.0, "1000", "K"),

            # REQ_014: Clean Office Requisition ($850)
            ("REQ_014", "00010", "MAT_PRINTER_008", "VEND001", 1, 850.0, "1000", "K")
        ]

        for req_id, item_no, mat, v_id, qty, price, p_org, acct in pr_items:
            db.execute(
                text("""
                    INSERT INTO PurchaseRequisitionItem (purchase_requisition_id, purchase_requisition_item, material, vendor_id, order_quantity, net_price_amount, purchasing_organization, account_assignment_category)
                    VALUES (:req_id, :item_no, :material, :vendor_id, :qty, :price, :p_org, :acct)
                    ON CONFLICT (purchase_requisition_id, purchase_requisition_item) DO UPDATE SET
                        material = EXCLUDED.material,
                        vendor_id = EXCLUDED.vendor_id,
                        order_quantity = EXCLUDED.order_quantity,
                        net_price_amount = EXCLUDED.net_price_amount,
                        purchasing_organization = EXCLUDED.purchasing_organization,
                        account_assignment_category = EXCLUDED.account_assignment_category;
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

        # 11. Run Triage Processing on Seeded PRs via real LangGraph pipeline
        print("Triage processing seeded requisitions through LangGraph graph...")
        from app.agent import run_triage_flow

        for req_id, group, user, req_date, status in reqs:
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
            
            # Execute real LangGraph triage flow
            triage_result = run_triage_flow(state_input, db)
            
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

        print("Database seeded and triage outcomes processed successfully with real LangGraph graph!")
    except Exception as e:
        db.rollback()
        import traceback
        print("Error seeding database:")
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
