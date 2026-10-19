CREATE TABLE IF NOT EXISTS clients (
  id text PRIMARY KEY, name text NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id text PRIMARY KEY, name text NOT NULL, email text UNIQUE NOT NULL,
  password_hash text NOT NULL, role text NOT NULL CHECK (role IN ('PIC','FINANCE_REVIEWER','AMIGA_DIRECTOR'))
);
CREATE TABLE IF NOT EXISTS assignments (
  user_id text NOT NULL REFERENCES users(id), client_id text NOT NULL REFERENCES clients(id),
  PRIMARY KEY(user_id, client_id)
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash text PRIMARY KEY, user_id text NOT NULL REFERENCES users(id),
  csrf text NOT NULL, expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS requests (
  id uuid PRIMARY KEY, client_id text NOT NULL REFERENCES clients(id),
  uploaded_by text NOT NULL REFERENCES users(id), filename text NOT NULL,
  document_key text NOT NULL, pdf_sha256 text NOT NULL, page_count integer NOT NULL,
  pages jsonb NOT NULL, mode text NOT NULL CHECK (mode IN ('REPLAY','OPENAI')),
  sample_name text, status text NOT NULL,
  current_version integer NOT NULL DEFAULT 0, error_code text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  idempotency_key text NOT NULL, UNIQUE (client_id, uploaded_by, idempotency_key)
);
CREATE TABLE IF NOT EXISTS invoice_versions (
  request_id uuid NOT NULL REFERENCES requests(id), version integer NOT NULL,
  snapshot jsonb NOT NULL, actor_id text NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(request_id, version)
);
CREATE TABLE IF NOT EXISTS jobs (
  request_id uuid PRIMARY KEY REFERENCES requests(id), status text NOT NULL,
  started_at timestamptz, finished_at timestamptz
);
CREATE TABLE IF NOT EXISTS audit_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  request_id uuid NOT NULL REFERENCES requests(id), actor_id text NOT NULL REFERENCES users(id),
  action text NOT NULL, reason text NOT NULL, changes jsonb NOT NULL,
  version integer NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS vendors (
  client_id text NOT NULL REFERENCES clients(id), id text NOT NULL, name text NOT NULL,
  verified_accounts jsonb NOT NULL, PRIMARY KEY(client_id,id)
);
CREATE INDEX IF NOT EXISTS request_client_created ON requests(client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_request_created ON audit_events(request_id, created_at DESC);
CREATE OR REPLACE FUNCTION deny_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'History is append-only'; END;
$$;
CREATE OR REPLACE TRIGGER immutable_versions BEFORE UPDATE OR DELETE ON invoice_versions
FOR EACH ROW EXECUTE FUNCTION deny_history_mutation();
CREATE OR REPLACE TRIGGER immutable_audit BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION deny_history_mutation();

-- Additive local migration: existing requests, credentials and history remain intact.
ALTER TABLE requests ADD COLUMN IF NOT EXISTS approved_version integer;
CREATE TABLE IF NOT EXISTS review_decisions (
  id uuid PRIMARY KEY, request_id uuid NOT NULL, invoice_version integer NOT NULL,
  actor_id text NOT NULL REFERENCES users(id), reason text NOT NULL,
  source_review jsonb NOT NULL, validation jsonb NOT NULL,
  approved_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(request_id, invoice_version),
  FOREIGN KEY(request_id, invoice_version) REFERENCES invoice_versions(request_id, version)
);
CREATE TABLE IF NOT EXISTS voucher_counters (
  client_id text NOT NULL REFERENCES clients(id), year integer NOT NULL,
  last_number integer NOT NULL, PRIMARY KEY(client_id, year)
);
CREATE TABLE IF NOT EXISTS vouchers (
  id uuid PRIMARY KEY, request_id uuid NOT NULL, invoice_version integer NOT NULL,
  decision_id uuid NOT NULL UNIQUE REFERENCES review_decisions(id),
  number text NOT NULL UNIQUE, template_version text NOT NULL, payload jsonb NOT NULL,
  render_status text NOT NULL CHECK(render_status IN ('PENDING','RENDERING','READY','FAILED')),
  attempt_count integer NOT NULL DEFAULT 0, error_code text,
  document_key text, pdf_sha256 text, superseded_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(), rendered_at timestamptz,
  UNIQUE(request_id, invoice_version),
  FOREIGN KEY(request_id, invoice_version) REFERENCES invoice_versions(request_id, version)
);
CREATE OR REPLACE TRIGGER immutable_decisions BEFORE UPDATE OR DELETE ON review_decisions
FOR EACH ROW EXECUTE FUNCTION deny_history_mutation();
CREATE OR REPLACE TRIGGER retain_vouchers BEFORE DELETE ON vouchers
FOR EACH ROW EXECUTE FUNCTION deny_history_mutation();
CREATE OR REPLACE FUNCTION protect_voucher_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.id,NEW.request_id,NEW.invoice_version,NEW.decision_id,NEW.number,NEW.template_version,NEW.payload)
     IS DISTINCT FROM
     (OLD.id,OLD.request_id,OLD.invoice_version,OLD.decision_id,OLD.number,OLD.template_version,OLD.payload) THEN
    RAISE EXCEPTION 'Voucher approval snapshot is immutable';
  END IF;
  IF OLD.render_status='READY' AND (NEW.document_key,NEW.pdf_sha256,NEW.render_status)
     IS DISTINCT FROM (OLD.document_key,OLD.pdf_sha256,OLD.render_status) THEN
    RAISE EXCEPTION 'Rendered voucher is immutable';
  END IF;
  IF OLD.superseded_at IS NOT NULL AND NEW.superseded_at IS DISTINCT FROM OLD.superseded_at THEN
    RAISE EXCEPTION 'Superseded voucher cannot be reactivated';
  END IF;
  RETURN NEW;
END;
$$;
CREATE OR REPLACE TRIGGER immutable_voucher_payload BEFORE UPDATE ON vouchers
FOR EACH ROW EXECUTE FUNCTION protect_voucher_snapshot();

CREATE TABLE IF NOT EXISTS upload_batches (
  id uuid PRIMARY KEY, client_id text NOT NULL REFERENCES clients(id),
  uploaded_by text NOT NULL REFERENCES users(id), idempotency_key text NOT NULL,
  manifest_sha256 text NOT NULL, mode text NOT NULL CHECK(mode IN ('OPENAI','REPLAY')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(uploaded_by,idempotency_key)
);
CREATE TABLE IF NOT EXISTS upload_batch_items (
  batch_id uuid NOT NULL REFERENCES upload_batches(id), position integer NOT NULL,
  filename text NOT NULL, byte_size bigint NOT NULL, pdf_sha256 text NOT NULL,
  sample_name text, status text NOT NULL CHECK(status IN ('PENDING','ACCEPTED','REJECTED')),
  request_id uuid REFERENCES requests(id), request_created boolean,
  error_code text, error_message text, received_at timestamptz,
  PRIMARY KEY(batch_id,position),
  CHECK((status='ACCEPTED')=(request_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS batch_client_created ON upload_batches(client_id,created_at DESC);
-- Tahap 5 pajak: pilihan potongan sebelum submit. NULL = belum dipilih; approval ditahan sampai Finance memilih.
ALTER TABLE requests ADD COLUMN IF NOT EXISTS tax_selection jsonb;
ALTER TABLE upload_batch_items ADD COLUMN IF NOT EXISTS tax_selection jsonb;
-- Tahap 6: file asli dan hasil baca mentah disimpan di database sebagai pembanding permanen.
ALTER TABLE vendors ADD COLUMN IF NOT EXISTS npwp text;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS media_type text NOT NULL DEFAULT 'application/pdf'
  CHECK (media_type IN ('application/pdf','image/jpeg','image/png'));
CREATE TABLE IF NOT EXISTS request_files (
  request_id uuid PRIMARY KEY REFERENCES requests(id),
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  media_type text NOT NULL CHECK (media_type IN ('application/pdf','image/jpeg','image/png')),
  filename text NOT NULL, byte_size integer NOT NULL CHECK (byte_size > 0),
  content bytea NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (octet_length(content) = byte_size)
);
CREATE TABLE IF NOT EXISTS extraction_runs (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  request_id uuid NOT NULL REFERENCES requests(id), provider text NOT NULL, model text,
  prompt_version text, status text NOT NULL CHECK (status IN ('COMPLETED','FAILED')),
  reason text, duration_ms integer, input_tokens integer, output_tokens integer, cost_upper_usd numeric(12,6),
  fallback_from text, raw_response jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS extraction_runs_request ON extraction_runs(request_id, id);
CREATE OR REPLACE TRIGGER immutable_request_files BEFORE UPDATE OR DELETE ON request_files
FOR EACH ROW EXECUTE FUNCTION deny_history_mutation();
CREATE OR REPLACE TRIGGER immutable_extraction_runs BEFORE UPDATE OR DELETE ON extraction_runs
FOR EACH ROW EXECUTE FUNCTION deny_history_mutation();
CREATE OR REPLACE FUNCTION protect_request_document() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.pdf_sha256,NEW.document_key,NEW.media_type) IS DISTINCT FROM (OLD.pdf_sha256,OLD.document_key,OLD.media_type) THEN
    RAISE EXCEPTION 'Original document reference is immutable';
  END IF;
  RETURN NEW;
END;
$$;
CREATE OR REPLACE TRIGGER immutable_request_document BEFORE UPDATE ON requests
FOR EACH ROW EXECUTE FUNCTION protect_request_document();

-- Stage 8: two-stage electronic signature, Finance first, then AMIGA's own BOD, one director for every client.
-- Additive only; the client still approves and pays outside the app (brief p7). The role constraint is rebuilt once,
-- and the first stage 8 design's client directors (CLIENT_APPROVER, status CLIENT_APPROVED) move over with it.
ALTER TABLE users ADD COLUMN IF NOT EXISTS title text;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='users'::regclass AND conname='users_role_check'
                 AND pg_get_constraintdef(oid) LIKE '%AMIGA_DIRECTOR%') THEN
    ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
    UPDATE users SET role='AMIGA_DIRECTOR' WHERE role='CLIENT_APPROVER';
    ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('PIC','FINANCE_REVIEWER','AMIGA_DIRECTOR'));
  END IF;
END $$;
UPDATE requests SET status='AMIGA_APPROVED' WHERE status='CLIENT_APPROVED';
CREATE TABLE IF NOT EXISTS approval_steps (
  id uuid PRIMARY KEY, request_id uuid NOT NULL, invoice_version integer NOT NULL,
  voucher_id uuid NOT NULL REFERENCES vouchers(id),
  kind text NOT NULL CHECK (kind IN ('REVIEWER_SIGNED','DIRECTOR_APPROVED','DIRECTOR_RETURNED')),
  actor_id text NOT NULL REFERENCES users(id), signer_name text NOT NULL, signer_title text NOT NULL,
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  document_sha256 text CHECK (document_sha256 ~ '^[0-9a-f]{64}$'),
  previous_step_id uuid REFERENCES approval_steps(id),
  verification_code text NOT NULL UNIQUE CHECK (verification_code ~ '^[2-9A-HJ-NP-Z]{8}$'),
  auth_method text NOT NULL CHECK (auth_method IN ('PASSWORD_REENTRY','SESSION')),
  consent_text text, reason text, client_ip text, user_agent text, signed_at timestamptz NOT NULL,
  FOREIGN KEY(request_id, invoice_version) REFERENCES invoice_versions(request_id, version),
  CHECK (kind='DIRECTOR_RETURNED' OR (auth_method='PASSWORD_REENTRY' AND consent_text IS NOT NULL)),
  CHECK (kind<>'REVIEWER_SIGNED' OR previous_step_id IS NULL),
  CHECK (kind<>'DIRECTOR_APPROVED' OR previous_step_id IS NOT NULL),
  CHECK (kind<>'DIRECTOR_RETURNED' OR length(btrim(coalesce(reason,'')))>=5)
);
CREATE UNIQUE INDEX IF NOT EXISTS approval_steps_one_reviewer ON approval_steps(voucher_id) WHERE kind='REVIEWER_SIGNED';
CREATE UNIQUE INDEX IF NOT EXISTS approval_steps_one_director ON approval_steps(voucher_id) WHERE kind<>'REVIEWER_SIGNED';
CREATE OR REPLACE TRIGGER immutable_approval_steps BEFORE UPDATE OR DELETE ON approval_steps
FOR EACH ROW EXECUTE FUNCTION deny_history_mutation();
CREATE TABLE IF NOT EXISTS voucher_signoffs (
  voucher_id uuid PRIMARY KEY REFERENCES vouchers(id),
  director_step_id uuid NOT NULL UNIQUE REFERENCES approval_steps(id), verify_url text NOT NULL,
  render_status text NOT NULL CHECK(render_status IN ('PENDING','RENDERING','READY','FAILED')),
  attempt_count integer NOT NULL DEFAULT 0, error_code text, document_key text, pdf_sha256 text,
  created_at timestamptz NOT NULL DEFAULT now(), rendered_at timestamptz
);
CREATE OR REPLACE TRIGGER retain_signoffs BEFORE DELETE ON voucher_signoffs
FOR EACH ROW EXECUTE FUNCTION deny_history_mutation();
CREATE OR REPLACE FUNCTION protect_signoff() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.voucher_id,NEW.director_step_id,NEW.verify_url) IS DISTINCT FROM
     (OLD.voucher_id,OLD.director_step_id,OLD.verify_url) THEN
    RAISE EXCEPTION 'Signed voucher snapshot is immutable';
  END IF;
  IF OLD.render_status='READY' AND (NEW.document_key,NEW.pdf_sha256,NEW.render_status)
     IS DISTINCT FROM (OLD.document_key,OLD.pdf_sha256,OLD.render_status) THEN
    RAISE EXCEPTION 'Rendered signed voucher is immutable';
  END IF;
  RETURN NEW;
END;
$$;
CREATE OR REPLACE TRIGGER immutable_signoff BEFORE UPDATE ON voucher_signoffs
FOR EACH ROW EXECUTE FUNCTION protect_signoff();

-- Stage 8: a signature specimen per signer, only the look of a signature. It is stamped on the voucher after the
-- electronic signature succeeds, kept by its hash so an old voucher always re-renders with the same image, and never
-- shown on the public verification page. Demo accounts get a synthetic specimen (app/specimen.py).
CREATE TABLE IF NOT EXISTS signature_specimens (
  sha256 text PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'), user_id text NOT NULL REFERENCES users(id),
  image_png bytea NOT NULL, source text NOT NULL CHECK (source IN ('SYNTHETIC_DEMO','UPLOADED')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE OR REPLACE TRIGGER immutable_signature_specimens BEFORE UPDATE OR DELETE ON signature_specimens
FOR EACH ROW EXECUTE FUNCTION deny_history_mutation();
ALTER TABLE approval_steps ADD COLUMN IF NOT EXISTS specimen_sha256 text REFERENCES signature_specimens(sha256);

-- Stage 8: an account can be closed. A closed account cannot sign in, and its open sessions stop working.
-- The first design's second client director is closed once, when the column arrives; a later reopening stays.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid='users'::regclass AND attname='disabled_at'
                 AND NOT attisdropped) THEN
    ALTER TABLE users ADD COLUMN disabled_at timestamptz;
    UPDATE users SET disabled_at=now() WHERE id='direksi_b';
  END IF;
END $$;

-- 15 Oct: the PIC submits an invoice to Finance after checking it. The status stays the result of the checks; the stage
-- is read from submitted_at. Once, when the columns arrive: a request Finance ever signed counts as submitted by its
-- uploader, with an audit row that says so. Every other request waits for its PIC.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid='requests'::regclass AND attname='submitted_at'
                 AND NOT attisdropped) THEN
    ALTER TABLE requests ADD COLUMN submitted_at timestamptz, ADD COLUMN submitted_by text REFERENCES users(id),
                         ADD COLUMN submitted_version integer;
    UPDATE requests r SET submitted_by=r.uploaded_by, submitted_version=coalesce(r.approved_version,r.current_version),
           submitted_at=coalesce((SELECT min(d.approved_at) FROM review_decisions d WHERE d.request_id=r.id),r.updated_at)
     WHERE r.status IN ('AMIGA_REVIEWED','AMIGA_APPROVED','RETURNED')
        OR EXISTS (SELECT 1 FROM review_decisions d WHERE d.request_id=r.id);
    INSERT INTO audit_events(request_id,actor_id,action,reason,changes,version)
    SELECT id,submitted_by,'INTAKE_SUBMITTED',
           'Ditandai saat migrasi: Finance sudah menandatangani sebelum ada langkah pengajuan PIC.',
           '{"migrated":true}'::jsonb,submitted_version FROM requests WHERE submitted_at IS NOT NULL;
  END IF;
END $$;
-- 15 Oct: a vendor the client's master does not know yet is registered by the PIC who submits its invoice. Who added
-- the row, when, and from which request stays visible to Finance and the director.
ALTER TABLE vendors ADD COLUMN IF NOT EXISTS registered_by text REFERENCES users(id);
ALTER TABLE vendors ADD COLUMN IF NOT EXISTS registered_at timestamptz;
ALTER TABLE vendors ADD COLUMN IF NOT EXISTS registered_request_id uuid REFERENCES requests(id);
-- 15 Oct: portfolios. Team A and team B, each a PIC and a Finance reviewer, hold ten clients each; AMIGA's director
-- holds every client. The three-letter code starts each voucher number of its client.
ALTER TABLE clients ADD COLUMN IF NOT EXISTS code text CHECK (code ~ '^[A-Z]{3}$');
ALTER TABLE clients ADD COLUMN IF NOT EXISTS city text;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS sector text;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS npwp text;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS team text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS team text;
CREATE UNIQUE INDEX IF NOT EXISTS clients_code ON clients(code);
-- 15 Oct: a PIC opens a new client for the team. audit_events needs a request, so a client keeps its own trail.
ALTER TABLE clients ADD COLUMN IF NOT EXISTS created_by text REFERENCES users(id);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS created_at timestamptz;
CREATE TABLE IF NOT EXISTS client_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, client_id text NOT NULL REFERENCES clients(id),
  actor_id text NOT NULL REFERENCES users(id), action text NOT NULL, changes jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE OR REPLACE TRIGGER immutable_client_events BEFORE UPDATE OR DELETE ON client_events
FOR EACH ROW EXECUTE FUNCTION deny_history_mutation();
-- 15 Oct: Robot Admin chat. Each user keeps their own conversations; no other account can read them. A message keeps
-- its text plus the references the server built from tool results, so a reopened conversation shows the same cards.
CREATE TABLE IF NOT EXISTS chat_threads (
  id uuid PRIMARY KEY, user_id text NOT NULL REFERENCES users(id), title text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_threads_user ON chat_threads(user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS chat_messages (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, thread_id uuid NOT NULL REFERENCES chat_threads(id),
  role text NOT NULL CHECK (role IN ('user','assistant')), content text NOT NULL,
  refs jsonb NOT NULL DEFAULT '{}'::jsonb, request_id uuid REFERENCES requests(id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_messages_thread ON chat_messages(thread_id, id);
-- One spend ledger for every schema in this database (live, QA, smoke), so the chat's US$2 cap is one total. A call
-- is reserved before it leaves; only a call with priced usage replaces its reservation with the real cost.
CREATE TABLE IF NOT EXISTS public.chat_usage (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, schema_name text NOT NULL, user_id text, model text NOT NULL,
  state text NOT NULL CHECK (state IN ('PENDING','DONE','FAILED')), reserved_usd numeric(12,6) NOT NULL,
  cost_usd numeric(12,6), input_tokens integer, cached_tokens integer, output_tokens integer, duration_ms integer,
  created_at timestamptz NOT NULL DEFAULT now()
);
-- 16 Okt 2026: Hubungi klien. A PIC keeps Telegram contacts per client and sends the final voucher through n8n. A
-- contact change goes to client_events, a send to audit_events too; a send never changes the invoice status.
CREATE TABLE IF NOT EXISTS client_contacts (
  id uuid PRIMARY KEY, client_id text NOT NULL REFERENCES clients(id), name text NOT NULL,
  telegram_chat_id text NOT NULL CHECK (telegram_chat_id ~ '^-?[0-9]{5,20}$'), active boolean NOT NULL DEFAULT true,
  created_by text NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS client_contacts_active ON client_contacts(client_id, telegram_chat_id) WHERE active;
CREATE TABLE IF NOT EXISTS voucher_deliveries (
  id uuid PRIMARY KEY, request_id uuid NOT NULL REFERENCES requests(id), voucher_id uuid NOT NULL REFERENCES vouchers(id),
  invoice_version integer NOT NULL, contact_id uuid NOT NULL REFERENCES client_contacts(id), pdf_sha256 text NOT NULL,
  status text NOT NULL CHECK (status IN ('SENDING','SENT','FAILED','UNCERTAIN')), provider_message_id text,
  error_code text, detail text, sent_by text NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
-- One send at a time per invoice, so a double click cannot reach the client twice.
CREATE UNIQUE INDEX IF NOT EXISTS voucher_deliveries_one_sending ON voucher_deliveries(request_id) WHERE status='SENDING';
