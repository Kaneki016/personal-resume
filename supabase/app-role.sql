-- Run after creating the private portfolio_app login with a generated password.
GRANT USAGE ON SCHEMA portfolio TO portfolio_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA portfolio TO portfolio_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA portfolio TO portfolio_app;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['projects','jobs','invoices','payments','expenses','audit','sessions','login_attempts'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='portfolio' AND tablename=t AND policyname='private_app_access') THEN
      EXECUTE format('CREATE POLICY private_app_access ON portfolio.%I TO portfolio_app USING (true) WITH CHECK (true)', t);
    END IF;
  END LOOP;
END $$;
