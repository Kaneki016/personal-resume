BEGIN;
SET LOCAL search_path TO portfolio;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS fee_known INTEGER NOT NULL DEFAULT 1 CHECK(fee_known IN (0,1));

CREATE TABLE IF NOT EXISTS invoice_settings (id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS invoice_counter (id TEXT PRIMARY KEY, value BIGINT NOT NULL CHECK(value>=0));
CREATE TABLE IF NOT EXISTS invoice_documents (
 id BIGINT PRIMARY KEY REFERENCES invoices(id), request_key TEXT NOT NULL UNIQUE,
 fingerprint TEXT NOT NULL, body TEXT NOT NULL
);

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['invoice_settings','invoice_counter','invoice_documents'] LOOP
  EXECUTE format('ALTER TABLE portfolio.%I ENABLE ROW LEVEL SECURITY', t);
  EXECUTE format('REVOKE ALL ON portfolio.%I FROM PUBLIC, anon, authenticated', t);
  EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON portfolio.%I TO portfolio_app', t);
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='portfolio' AND tablename=t AND policyname='private_app_access') THEN
   EXECUTE format('CREATE POLICY private_app_access ON portfolio.%I TO portfolio_app USING (true) WITH CHECK (true)',t);
  END IF;
 END LOOP;
END $$;
COMMIT;
