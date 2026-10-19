# AMIGA Robot Admin web app (kelompok 9)

A single browser entry point at `http://127.0.0.1:3000/`, backed by Next.js and FastAPI:

- `/` Dashboard antrean. Summary cards per status (click one to filter), filters for
  client, status, and free text, and the invoice list, newest first. Each row opens the
  invoice at `/review#request=<id>` on this same origin. The Manajer Keuangan starts with
  **Menunggu manajer keuangan** selected.
- `/unggah` Unggah invoice, PIC only. 1 to 5 files (PDF, JPG, JPEG, PNG, max 5 MB each), one tax
  preset for the upload, and live progress per file until it is ready for Finance.
- `/persetujuan` Persetujuan, for Finance and the Manajer Keuangan. The same list, narrowed to the invoices that
  wait for the viewer's own decision. The sidebar shows it in place of Unggah invoice for these roles.

`/review` serves the FastAPI workspace through the Next.js proxy. Static assets, API calls, PDF previews,
login, and verification all stay on port 3000. The old backend root on port 8787 redirects to this UI.
**Ganti akun** opens the login form; a Finance-approved review also offers **Masuk sebagai Manajer Keuangan**,
retaining the current request. Every decision still requires the correct role, password, and consent.

## Versions

Pinned exactly in `package.json`:

| Package | Version |
| --- | --- |
| next | 16.3.8 |
| react | 19.3.0 |
| react-dom | 19.3.0 |
| @fontsource-variable/figtree | 5.3.0 |
| typescript | 5.9.3 |
| @types/react | 19.3.0 |
| @types/react-dom | 19.3.0 |
| @types/node | 24.19.2 |

Built and tested on Node 24.21.0 with npm 11.19.0. No install scripts are needed.
Next's SWC compiler ships as a prebuilt optional dependency.

## Before you start

1. Start the FastAPI app first. It must listen on `http://127.0.0.1:8787`.
   From the project root, run `.\app\start.ps1`. Details are in `../app/README.md`.
2. Log in on the main app with the same host name you will use for this app. The session
   cookie is scoped by host, not by port: log in at `127.0.0.1:8787` to use
   `127.0.0.1:3000`, or at `localhost:8787` to use `localhost:3000`. Every link back to
   the main app keeps the host of the page you are on.

## Run

```bash
npm install
npm run build
npm run start
```

Then open `http://127.0.0.1:3000/`.

For development with hot reload, use `npm run dev` on the same address.

To keep Next.js from sending anonymous telemetry, set `NEXT_TELEMETRY_DISABLED=1`
in the shell before running these commands.

## How it talks to the backend

`next.config.ts` rewrites `/api/v1/:path*` to `http://127.0.0.1:8787/api/v1/:path*`.
The browser therefore calls its own origin, and sends the session cookie with it.

That rewrite forwards with `Host: 127.0.0.1:8787` while the browser's `Origin` stays on
port 3000, so FastAPI's origin check would reject every POST. `proxy.ts` runs the same
check against this app's own host first (403 `ORIGIN_REJECTED` on a mismatch), then hands
the request on with the Origin FastAPI expects. FastAPI still checks the CSRF token and
the SameSite=strict cookie.

The app is not mounted inside FastAPI on purpose. The backend's CSP
(`script-src 'self'`) blocks the inline scripts Next.js needs.

| Endpoint | Used for |
| --- | --- |
| `GET /api/v1/session` | Name, role, clients, and the CSRF token for uploads |
| `GET /api/v1/requests?client_id=<id>` | Queue per client, fetched in parallel and merged |
| `GET /api/v1/sop/label` | Friendly titles per issue code, once per page load |
| `GET /api/v1/tax/rules` | Tax presets for the upload form |
| `POST /api/v1/intake-batches` | Upload manifest (`Idempotency-Key`, `x-csrf-token`) |
| `POST /api/v1/intake-batches/{id}/items/{position}` | One raw file per pending item |
| `GET /api/v1/intake-batches/{id}` | Upload progress, polled every 1.5 s while invoices are read |

The upload follows `app/static/batches.js`. Files that fail the browser's checks are still
listed in the manifest with a zero hash, so the server records them as rejected. An
ambiguous network error on one file does not stop the others; the page reads the stored
result afterwards and offers to resend what did not arrive.

When `/api/v1/sop/label` fails or lacks a code, the dashboard uses its own wording for
known codes and otherwise makes the code readable ("POSSIBLE_DUPLICATE" becomes
"Possible duplicate").

## Screen states

| Situation | What the screen shows |
| --- | --- |
| Session missing or expired (401) | "Masuk dulu ke AMIGA, ya." with a link to the main app login |
| FastAPI down, or any 5xx | "Layanan AMIGA belum bisa dihubungi." with a retry button |
| Refresh fails after a good load | Last good data stays on screen, with a warning banner |
| CSRF or origin rejected on upload | "Sesi berubah. Muat ulang halaman." |

The dashboard refreshes every 15 seconds while the tab is visible. Both screens reload
by themselves when you return to the tab after logging in.

## Files

| Path | Purpose |
| --- | --- |
| `app/layout.tsx` | Root layout, Figtree font, titles, app shell |
| `app/page.tsx` | The dashboard (client component) |
| `app/unggah/page.tsx` | The upload page (client component) |
| `app/unggah/layout.tsx` | Tab title for the upload page |
| `app/globals.css` | Brand tokens and every style |
| `app/icon.svg` | Browser tab icon |
| `components/shell.tsx` | Sidebar, top bar, signed-in user |
| `components/states.tsx` | Loading, signed-out, offline, and error states |
| `components/icons.tsx` | Inline SVG icons |
| `lib/api.ts` | Fetch helpers, error mapping, links to the main app |
| `lib/upload.ts` | File checks, manifest, upload calls, progress per file |
| `lib/hooks.ts` | Main app origin, safe for server rendering |
| `lib/format.ts` | Rupiah and Asia/Jakarta date formatters |
| `lib/status.ts` | Status, issue, and role labels |
| `lib/types.ts` | Response types |
| `proxy.ts` | Origin check for POSTs through the `/api/v1` rewrite |
| `next.config.ts` | `/api/v1` rewrite, `poweredByHeader: false` |
