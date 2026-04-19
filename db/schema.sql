CREATE TABLE IF NOT EXISTS raw_events (
    id              SERIAL PRIMARY KEY,
    source          VARCHAR(64) NOT NULL,
    category        VARCHAR(64),
    title           TEXT,
    content         TEXT,
    url             TEXT,
    scraped_at      TIMESTAMPTZ DEFAULT NOW(),
    processed       BOOLEAN DEFAULT FALSE,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ego_signals (
    id              SERIAL PRIMARY KEY,
    raw_event_id    INTEGER REFERENCES raw_events(id),
    signal_type     VARCHAR(64),
    urgency_score   NUMERIC(4,2),
    summary         TEXT,
    action_required TEXT,
    deadline        DATE,
    status          VARCHAR(32) DEFAULT 'pending',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ego_decisions (
    id              SERIAL PRIMARY KEY,
    topic           TEXT NOT NULL,
    pros            TEXT,
    cons            TEXT,
    risk_list       TEXT,
    alternatives    TEXT,
    recommendation  TEXT,
    cooling_hours   INTEGER DEFAULT 24,
    submitted_at    TIMESTAMPTZ DEFAULT NOW(),
    revisit_at      TIMESTAMPTZ,
    final_choice    TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mb_benefits (
    id              SERIAL PRIMARY KEY,
    benefit_name    VARCHAR(128) UNIQUE NOT NULL,
    program_url     TEXT,
    eligibility     TEXT,
    amount_estimate NUMERIC(10,2),
    frequency       VARCHAR(32),
    status          VARCHAR(32) DEFAULT 'unchecked',
    last_checked    TIMESTAMPTZ,
    next_review     DATE,
    notes           TEXT,
    apply_steps     TEXT,
    deadline        DATE,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mb_benefit_history (
    id              SERIAL PRIMARY KEY,
    benefit_id      INTEGER REFERENCES mb_benefits(id),
    event_type      VARCHAR(32),
    old_value       TEXT,
    new_value       TEXT,
    recorded_at     TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO mb_benefits (benefit_name, program_url, frequency, status) VALUES
('Rent Assist',             'https://www.gov.mb.ca/housing/pubs/rent_assist_fact_sheet.pdf', 'monthly',   'unchecked'),
('CAIP Carbon Rebate',      'https://www.canada.ca/en/revenue-agency/services/child-family-benefits/canada-carbon-rebate.html', 'quarterly', 'unchecked'),
('Canada Child Benefit',    'https://www.canada.ca/en/revenue-agency/services/child-family-benefits/canada-child-benefit-overview.html', 'monthly', 'unchecked'),
('MB Hydro Low Income',     'https://www.hydro.mb.ca/accounts_and_services/financial_assistance/', 'annual',    'unchecked'),
('MB Transit Pass Subsidy', 'https://winnipegtransit.com/en/fares/reduced-fare-programs', 'monthly',   'unchecked'),
('Employment Insurance',    'https://www.canada.ca/en/services/benefits/ei.html', 'bi-weekly', 'unchecked'),
('GST/HST Credit',          'https://www.canada.ca/en/revenue-agency/services/child-family-benefits/goods-services-tax-harmonized-sales-tax-gst-hst-credit.html', 'quarterly', 'unchecked'),
('MB Pharmacare',           'https://www.gov.mb.ca/health/pharmacare/', 'annual',    'unchecked'),
('MB Shelter Allowance',    'https://www.gov.mb.ca/fs/eia/index.html', 'monthly',   'unchecked'),
('Canada Dental Benefit',   'https://www.canada.ca/en/services/benefits/dental/dental-care-plan.html', 'annual',    'unchecked'),
('Winnipeg Food Bank',      'https://www.winnipegharvest.org/', 'on-demand', 'unchecked')
ON CONFLICT (benefit_name) DO NOTHING;

CREATE TABLE IF NOT EXISTS grocery_prices (
    id              SERIAL PRIMARY KEY,
    store           VARCHAR(64),
    item_name       VARCHAR(128),
    price           NUMERIC(8,2),
    unit            VARCHAR(32),
    sale            BOOLEAN DEFAULT FALSE,
    scraped_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rental_listings (
    id              SERIAL PRIMARY KEY,
    source          VARCHAR(64),
    title           TEXT,
    price           NUMERIC(8,2),
    bedrooms        SMALLINT,
    neighborhood    VARCHAR(128),
    url             TEXT,
    available_from  DATE,
    scraped_at      TIMESTAMPTZ DEFAULT NOW(),
    active          BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS happiness_tasks (
    id              SERIAL PRIMARY KEY,
    week_start      DATE,
    category        VARCHAR(32),
    task            TEXT,
    completed       BOOLEAN DEFAULT FALSE,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS push_log (
    id              SERIAL PRIMARY KEY,
    channel         VARCHAR(32),
    message_type    VARCHAR(64),
    payload         TEXT,
    sent_at         TIMESTAMPTZ DEFAULT NOW(),
    success         BOOLEAN DEFAULT TRUE
);

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_raw_events_updated    BEFORE UPDATE ON raw_events    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_ego_signals_updated   BEFORE UPDATE ON ego_signals   FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_ego_decisions_updated BEFORE UPDATE ON ego_decisions  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_mb_benefits_updated   BEFORE UPDATE ON mb_benefits   FOR EACH ROW EXECUTE FUNCTION update_updated_at();
