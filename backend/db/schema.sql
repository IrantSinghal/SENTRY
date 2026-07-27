-- Drop tables if they exist to support clean schema updates
DROP TABLE IF EXISTS TriageResult CASCADE;
DROP TABLE IF EXISTS UserRole CASCADE;
DROP TABLE IF EXISTS PurchaseRequisitionItem CASCADE;
DROP TABLE IF EXISTS PriceHistory CASCADE;
DROP TABLE IF EXISTS PurchaseRequisition CASCADE;
DROP TABLE IF EXISTS VendorScreeningCache CASCADE;
DROP TABLE IF EXISTS Vendor CASCADE;
DROP TABLE IF EXISTS SanctionsList CASCADE;
DROP TABLE IF EXISTS AgentSettings CASCADE;

-- Create Vendor table first because it is referenced by other tables
CREATE TABLE IF NOT EXISTS Vendor (
    vendor_id TEXT PRIMARY KEY,
    vendor_name TEXT NOT NULL,
    onboarded_date DATE NOT NULL,
    compliance_flags TEXT[] DEFAULT '{}',
    contract_expiry_date DATE NOT NULL,
    tax_id TEXT,
    registered_address TEXT
);

-- Create SanctionsList table
CREATE TABLE IF NOT EXISTS SanctionsList (
    entry_id TEXT PRIMARY KEY,
    listed_name TEXT NOT NULL,
    list_source TEXT NOT NULL,       -- 'OFAC_SDN' | 'EU_CONSOLIDATED'
    snapshot_date DATE NOT NULL
);

-- Create VendorScreeningCache table
CREATE TABLE IF NOT EXISTS VendorScreeningCache (
    vendor_id TEXT PRIMARY KEY REFERENCES Vendor(vendor_id) ON DELETE CASCADE,
    sanctions_match BOOLEAN NOT NULL,
    sanctions_match_detail TEXT,
    adverse_media_flagged BOOLEAN NOT NULL,
    adverse_media_evidence JSONB,   -- {evidence: [...], sources: [...]}
    registry_verified BOOLEAN,      -- NULL = not determined, distinct from FALSE
    registry_detail TEXT,
    checked_at TIMESTAMPTZ NOT NULL
);

-- Create PurchaseRequisition table
CREATE TABLE IF NOT EXISTS PurchaseRequisition (
    purchase_requisition_id TEXT PRIMARY KEY,
    purchasing_group TEXT NOT NULL,
    created_by_user TEXT NOT NULL,
    requisition_date DATE NOT NULL,
    overall_release_status TEXT NOT NULL CHECK (overall_release_status IN ('open', 'approved', 'rejected', 'in_review'))
);

-- Create PurchaseRequisitionItem table
CREATE TABLE IF NOT EXISTS PurchaseRequisitionItem (
    purchase_requisition_id TEXT REFERENCES PurchaseRequisition(purchase_requisition_id) ON DELETE CASCADE,
    purchase_requisition_item TEXT NOT NULL, -- Line item number (e.g. '00010', '00020')
    material TEXT NOT NULL,
    vendor_id TEXT REFERENCES Vendor(vendor_id) ON DELETE SET NULL,
    order_quantity NUMERIC NOT NULL,
    net_price_amount NUMERIC NOT NULL,
    purchasing_organization TEXT NOT NULL,
    account_assignment_category TEXT,
    PRIMARY KEY (purchase_requisition_id, purchase_requisition_item)
);

-- Create PriceHistory table
CREATE TABLE IF NOT EXISTS PriceHistory (
    material TEXT NOT NULL,
    vendor_id TEXT REFERENCES Vendor(vendor_id) ON DELETE CASCADE,
    historical_avg_price NUMERIC NOT NULL,
    last_purchase_date DATE NOT NULL,
    PRIMARY KEY (material, vendor_id)
);

-- Create UserRole table (maps Supabase auth.users to a business role)
CREATE TABLE IF NOT EXISTS UserRole (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('analyst', 'approver', 'vp', 'cfo', 'admin')),
    display_name TEXT NOT NULL
);

-- Create TriageResult table
CREATE TABLE IF NOT EXISTS TriageResult (
    requisition_id TEXT PRIMARY KEY REFERENCES PurchaseRequisition(purchase_requisition_id) ON DELETE CASCADE,
    verdict TEXT NOT NULL CHECK (verdict IN ('auto_approve', 'escalate', 'reject')),
    confidence_score NUMERIC NOT NULL,
    signals JSONB NOT NULL,
    rationale TEXT NOT NULL,
    human_override TEXT CHECK (human_override IN ('approved', 'rejected', 'escalated')),
    human_override_reason TEXT,
    required_approver_role TEXT NOT NULL DEFAULT 'approver',
    requires_named_authority BOOLEAN NOT NULL DEFAULT false,
    overridden_by_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    item_results JSONB NOT NULL DEFAULT '[]'::jsonb,
    intra_pr_material_overlap JSONB
);

-- Create AgentSettings table
CREATE TABLE IF NOT EXISTS AgentSettings (
    key TEXT PRIMARY KEY,
    value NUMERIC NOT NULL,
    description TEXT
);

-- Create Indexes for performance
CREATE INDEX IF NOT EXISTS idx_pr_items_material ON PurchaseRequisitionItem(material);
CREATE INDEX IF NOT EXISTS idx_pr_items_vendor ON PurchaseRequisitionItem(vendor_id);
CREATE INDEX IF NOT EXISTS idx_price_history_lookup ON PriceHistory(material, vendor_id);
CREATE INDEX IF NOT EXISTS idx_pr_date ON PurchaseRequisition(requisition_date);

-- Enable RLS on UserRole and TriageResult
ALTER TABLE UserRole ENABLE ROW LEVEL SECURITY;
ALTER TABLE TriageResult ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist to prevent errors on multiple runs
DROP POLICY IF EXISTS select_user_role ON UserRole;
DROP POLICY IF EXISTS select_triage_result ON TriageResult;
DROP POLICY IF EXISTS update_triage_result ON TriageResult;

-- RLS Policies for UserRole
CREATE POLICY select_user_role ON UserRole
    FOR SELECT TO authenticated
    USING (true);

-- RLS Policies for TriageResult: Read permission for all authenticated users
CREATE POLICY select_triage_result ON TriageResult
    FOR SELECT TO authenticated
    USING (true);

-- RLS Policies for TriageResult: Update permission based on role hierarchy
CREATE POLICY update_triage_result ON TriageResult
    FOR UPDATE TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM UserRole ur
            WHERE ur.user_id = auth.uid()
            AND (
                ur.role = 'admin'
                OR (
                    NOT requires_named_authority 
                    AND ur.role IN ('approver', 'vp', 'cfo', 'admin')
                )
                OR (
                    requires_named_authority
                    AND (
                        (LOWER(required_approver_role) = 'vp' AND ur.role IN ('vp', 'cfo', 'admin'))
                        OR (LOWER(required_approver_role) = 'cfo' AND ur.role IN ('cfo', 'admin'))
                        OR (LOWER(required_approver_role) = 'approver' AND ur.role IN ('approver', 'vp', 'cfo', 'admin'))
                        OR (LOWER(required_approver_role) = 'analyst' AND ur.role IN ('analyst', 'approver', 'vp', 'cfo', 'admin'))
                    )
                )
            )
        )
    );
