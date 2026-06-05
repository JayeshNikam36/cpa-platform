-- Enable required extensions (already enabled in Supabase but include for documentation)
-- vector and pg_cron are already enabled

-- =====================
-- TABLE 1: firms
-- =====================
CREATE TABLE IF NOT EXISTS firms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    qbo_realm_id TEXT,
    qbo_access_token TEXT,
    qbo_refresh_token TEXT,
    qbo_token_expires_at TIMESTAMPTZ,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE firms ENABLE ROW LEVEL SECURITY;

CREATE POLICY "firms_own_data" ON firms
    FOR ALL USING (auth.uid() = id);

-- =====================
-- TABLE 2: clients
-- =====================
CREATE TABLE IF NOT EXISTS clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firm_id UUID NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    qbo_realm_id TEXT NOT NULL,
    qbo_access_token TEXT,
    qbo_refresh_token TEXT,
    qbo_token_expires_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE clients ENABLE ROW LEVEL SECURITY;

CREATE POLICY "clients_firm_isolation" ON clients
    FOR ALL USING (
        firm_id IN (SELECT id FROM firms WHERE id = auth.uid())
    );

CREATE INDEX IF NOT EXISTS idx_clients_firm_id ON clients(firm_id);

-- =====================
-- TABLE 3: chart_of_accounts
-- =====================
CREATE TABLE IF NOT EXISTS chart_of_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firm_id UUID NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    qbo_account_id TEXT NOT NULL,
    name TEXT NOT NULL,
    account_type TEXT,
    account_sub_type TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE chart_of_accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "coa_firm_isolation" ON chart_of_accounts
    FOR ALL USING (
        firm_id IN (SELECT id FROM firms WHERE id = auth.uid())
    );

CREATE INDEX IF NOT EXISTS idx_coa_firm_id ON chart_of_accounts(firm_id);
CREATE INDEX IF NOT EXISTS idx_coa_client_id ON chart_of_accounts(client_id);

-- =====================
-- TABLE 4: transactions
-- =====================
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firm_id UUID NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    qbo_txn_id TEXT NOT NULL,
    txn_date DATE NOT NULL,
    amount NUMERIC(15,2) NOT NULL,
    description TEXT,
    vendor_name TEXT,
    raw_category TEXT,
    ai_category_id UUID REFERENCES chart_of_accounts(id) ON DELETE SET NULL,
    ai_confidence NUMERIC(4,3),
    ai_reasoning TEXT,
    reconciliation_status TEXT DEFAULT 'pending',
    is_anomaly BOOLEAN DEFAULT false,
    anomaly_note TEXT,
    accountant_approved BOOLEAN DEFAULT false,
    accountant_override_category_id UUID REFERENCES chart_of_accounts(id) ON DELETE SET NULL,
    embedding VECTOR(1536),
    period_month DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "transactions_firm_isolation" ON transactions
    FOR ALL USING (
        firm_id IN (SELECT id FROM firms WHERE id = auth.uid())
    );

CREATE INDEX IF NOT EXISTS idx_transactions_firm_id ON transactions(firm_id);
CREATE INDEX IF NOT EXISTS idx_transactions_client_id ON transactions(client_id);
CREATE INDEX IF NOT EXISTS idx_transactions_period ON transactions(period_month);
CREATE INDEX IF NOT EXISTS idx_transactions_qbo_id ON transactions(qbo_txn_id);

-- Vector similarity search index
CREATE INDEX IF NOT EXISTS idx_transactions_embedding 
    ON transactions USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- =====================
-- TABLE 5: close_packages
-- =====================
CREATE TABLE IF NOT EXISTS close_packages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firm_id UUID NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    period_month DATE NOT NULL,
    status TEXT DEFAULT 'pending',
    pdf_url TEXT,
    narrative TEXT,
    narrative_approved BOOLEAN DEFAULT false,
    approved_at TIMESTAMPTZ,
    approved_by UUID REFERENCES firms(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE close_packages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "close_packages_firm_isolation" ON close_packages
    FOR ALL USING (
        firm_id IN (SELECT id FROM firms WHERE id = auth.uid())
    );

CREATE INDEX IF NOT EXISTS idx_close_packages_firm_id ON close_packages(firm_id);
CREATE INDEX IF NOT EXISTS idx_close_packages_client_id ON close_packages(client_id);
CREATE INDEX IF NOT EXISTS idx_close_packages_period ON close_packages(period_month);

-- =====================
-- TABLE 6: document_checklist_items
-- =====================
CREATE TABLE IF NOT EXISTS document_checklist_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firm_id UUID NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    close_package_id UUID REFERENCES close_packages(id) ON DELETE CASCADE,
    document_type TEXT NOT NULL,
    required_by DATE,
    received_at TIMESTAMPTZ,
    file_url TEXT,
    reminder_count INTEGER DEFAULT 0,
    last_reminder_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE document_checklist_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "checklist_firm_isolation" ON document_checklist_items
    FOR ALL USING (
        firm_id IN (SELECT id FROM firms WHERE id = auth.uid())
    );

CREATE INDEX IF NOT EXISTS idx_checklist_firm_id ON document_checklist_items(firm_id);
CREATE INDEX IF NOT EXISTS idx_checklist_client_id ON document_checklist_items(client_id);

-- =====================
-- AUTO UPDATE updated_at
-- =====================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_firms_updated_at
    BEFORE UPDATE ON firms
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_clients_updated_at
    BEFORE UPDATE ON clients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_transactions_updated_at
    BEFORE UPDATE ON transactions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_close_packages_updated_at
    BEFORE UPDATE ON close_packages
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
