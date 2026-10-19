# Initial snapshot verification — 19 October 2026

Source baseline: AMIGA module from `aldiandarwin/aldian_skills`, latest module commit `f0f666f`,
plus Vercel/EC2 proxy adjustments. This standalone repository starts a new Git history.

## Previously verified implementation

- Frontend deployment/origin tests: 7 passed.
- Backend HTTP boundary, SOP endpoints and voucher tests: 28 passed.
- Payment summary and review guide regression tests: 25 passed.
- TLS transport smoke: 12 checks passed through HTTPS gateway → Next.js → HTTPS FastAPI.
- Production frontend build and TypeScript: passed.
- SOP corpus: 70 cards passed strict validation.

The TLS smoke used synthetic sessions and storage stubs; no database, worker, AI, or Telegram was run.
These results do not claim a live production deployment or live provider validation.

## Standalone snapshot checks

- Frontend deployment/origin tests in this standalone checkout: 7 passed.
- Backend HTTP boundary, SOP endpoint and voucher tests: 28 passed.
- Payment summary/review guide tests: 25 passed.
- Bedrock configuration tests with normalized synthetic credentials: 7 passed.
- Frozen sample replay/dataset hash check: 1 passed; dataset bytes in the Git index match the working files.
- Total: 68 tests passed in this checkout; no paid providers were called.
- SOP corpus: 70 cards passed strict validation in this checkout.
- Production frontend build with TypeScript and seven generated pages: passed using `npm run build -- --webpack`.
  Existing local dependencies were reused via a junction; Turbopack rejects dependencies outside its project root,
  so Webpack was used for this isolated checkout. Standard Turbopack build passed in the source checkout before copying.
  A fresh clone or Vercel deployment installs its own dependencies with `npm ci` and uses `npm run build`.
- Publication scan: no matches for the checked local secret values or credential/private-key patterns.
  Only `.env.example` templates are included; no local `.env` or connector configuration is staged.
- Synthetic AWS credential IDs in test fixtures use `TESTACCESSKEY...` placeholders while preserving distinct
  values for alias-conflict tests. Personal n8n credential references were removed from the workflow export.

## Publication boundaries

Only source, synthetic fixtures, tests, and setup/deployment documentation are included.
No previous Git history is imported. Local credentials, connection configuration, live invoices,
cloud resource state, logs, private briefs/BRD, local storage, and installed dependencies are excluded.
The n8n export contains no account credential references. Knowledge Base configuration is an empty example.

Vercel Root Directory: `web`. Public frontend and backend origins and the shared proxy secret remain
placeholders until the target deployment is configured.
