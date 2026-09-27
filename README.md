# Lai Yoke Yau — portfolio and owner workspace

Public portfolio, private portfolio editor and freelance bookkeeping. Public contact consists only of email, WhatsApp and LinkedIn links. There are no public pricing or enquiry pages.

## Cloud architecture

- Vercel runs `app.py` (Flask), serving the public files in `dist/` and owner UI in `private/`.
- Supabase PostgreSQL stores portfolio entries, client projects, invoices, payments, expenses, audit history and temporary owner sessions.
- Supabase Auth verifies the single owner's password. There is no public registration endpoint. `OWNER_USER_ID` must match the authenticated Supabase user.
- Supabase Storage holds uploaded images in the **private** `portfolio-images` bucket. Public image requests are allowed only for images referenced by a published project, using links that expire after 60 seconds.

## Initial setup

1. Create a free Supabase project in Singapore. Disable automatic table exposure and enable automatic RLS.
2. Run `supabase/schema.sql` in its SQL editor. App tables live in the unexposed `portfolio` schema; anonymous and authenticated API roles have no grants or policies on them.
3. Create the owner's confirmed Supabase Auth user using their email and a strong password. Disable public sign-ups in Supabase Auth.
4. Create a private `portfolio_app` database login with a generated password and run `supabase/app-role.sql`. It grants access only to the app schema and its tables. Set the variables from `.env.example` in Vercel. Use this login with the **transaction pooler** connection string and `sslmode=require`. URL-encode special characters in its password. Keep the service-role key server-side.
5. Import the local SQLite snapshot with `python tools/migrate_to_supabase.py --sqlite /path/to/portfolio.sqlite3` in an environment containing `DATABASE_URL`. This refuses to overwrite an occupied destination and excludes local credentials/sessions. Import images separately into the private bucket with unchanged filenames.
6. Push to `main` to trigger the linked Vercel project. The existing project is named `laiyokeyau`.

## Owner workflow

Use **Website content** to edit the profile, introduction, contact details, page headings, section visibility, about text, experience, education, awards, skills, certifications and photo galleries. Choose a section, edit its fields, then **Save & publish**. List entries can be added, removed, reordered or hidden. Image fields support uploads; certificate fields also accept verification links. Public contact details do not change the private owner login.

Content is stored in Supabase and rendered into the public HTML on every request, including the page title and description. Routine edits need no deployment. Conflicting edits from another tab are rejected without overwriting them. Saved edits appear in the activity log and `site_content` is included in records backups. Deploying this feature requires `supabase/migrations/20260928_site_content.sql`, which preserves any existing content.

Open `/admin` and sign in with the owner password. Add or edit portfolio entries, images (JPG/PNG/WebP up to 3 MB), sort order and published status. Each project has its own gallery of up to 20 screenshots. Add several images at once, remove them or change their order; the first is the cover. Visitors open the gallery from that project’s card. Draft images require sign-in.

Record agreed fees under Client projects, issued milestones under Invoices, and actual deposits/balances under Payments received. Record expenses with business-use percentages and original receipt references. Mark corrections void rather than deleting history. Keep original receipt files separately.

Amounts are MYR stored as integer sen. Selected-year received income uses payment dates, expenses use paid dates and invoiced totals use issue dates. Outstanding balances and credits include all active invoices/payments, regardless of year. Net cash is not taxable profit. CSV exports include void flags and escape spreadsheet-formula text.

## Security and backups

Owner sessions are random opaque tokens; only their hashes are stored. Production cookies are Secure, HTTPOnly and SameSite Strict. Writes require a trusted origin and CSRF token. Database locks protect concurrent changes. Login attempts are limited in the database, so the limit applies across Vercel instances. Changing the owner password through the workspace clears all owner sessions.

Admin and private API responses send `X-Robots-Tag: noindex, nofollow`; the admin HTML also includes the robots meta tag. These directives do not replace authentication. The public portfolio remains indexable.

**Download records JSON** exports portfolio entries, financial records and change history. It does not include account credentials or image bytes. Export the `portfolio-images` bucket separately through Supabase Storage and keep it alongside the JSON. CSV is useful for bookkeeping but is not a complete backup. Supabase Free does not include automatic backups and may pause inactive projects.

To restore a records backup into an empty database, use the same column-preserving import approach as `tools/migrate_to_supabase.py`, preserving IDs and resetting identity sequences. Restore the image bucket with the original filenames. Recreate owner access separately.

Records support tax preparation; they do not calculate tax, decide expense deductibility or submit tax returns/MyInvois documents.

## Local fallback

The original SQLite workspace is preserved separately in `../freelance-portal` on the development computer. Run its `Start-Portfolio.ps1` to use the local records. Cloud changes and local changes are separate after migration; there is no automatic two-way sync.

`backend/server.py` retains the original SQLite server for reference. To develop the cloud version, install `requirements.txt`, set the environment variables and run `flask --app app run --port 4322` with `APP_ORIGIN=http://127.0.0.1:4322`.

Private records, environment files and credentials must never be committed. This repository contains application code and already-public portfolio assets only.

## Validation

`python tools/test_cloud.py` checks HTTP access, owner identity, CSRF, rate limits, draft privacy and bookkeeping behavior using isolated fixtures. `tools/test_postgres.py` is an opt-in check for this installation using ignored local credentials: it verifies real Supabase Auth, PostgreSQL integer totals, CSV, audit and JSON backup. Its financial fixtures run inside a transaction that is always rolled back.

`tools/provision_cloud.py` is the one-time setup helper for the named deployment. It uses authenticated Supabase/Vercel CLIs and keeps generated credentials in ignored local files. It does not reset an existing owner account. `supabase/config.toml` declares only the intended Auth settings; other remote settings are preserved.
