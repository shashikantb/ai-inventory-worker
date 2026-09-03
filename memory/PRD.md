# AI INVENTORY WORKER — PRD & Implementation Log

## Original problem statement
Build a universal AI-powered SaaS platform for warehouse & inventory operations that sits on top of an org's existing systems. Frontline workers should be able to Ask, Scan, Find, and Act via natural language, barcode, image, and voice.

## User choices (confirmed)
- **LLM**: Claude Sonnet 4.6 (chat) + Gemini 3 Flash (image ID) via Emergent Universal Key
- **Auth**: JWT + bcrypt, multi-tenant with org isolation
- **Voice**: OpenAI Whisper (deferred — backlog)
- **Scanning**: Web camera + ZXing barcode + Gemini vision for photo ID
- **Scope for MVP**: multi-tenant orgs/users/roles + products/inventory/locations + AI chat with tool calling + barcode scan + image recognition + dashboard + CSV import + audit logs

## Architecture
- **Backend**: FastAPI + Motor (MongoDB), single `server.py` (routers, models, seed, LLM streaming)
- **Frontend**: React 19 + React Router 7 + Tailwind + shadcn/ui + Recharts + ZXing + Sonner
- **AI Chat**: SSE streaming via `emergentintegrations` with 4 tools: `search_product`, `get_inventory`, `find_product_location`, `get_low_stock`
- **Image ID**: Gemini 3 Flash multimodal with catalog-aware system prompt
- **Barcode**: `@zxing/browser` in-browser (EAN/UPC/QR/Code128) + manual entry fallback
- **Audit**: every mutation writes to `audit_logs` with before/after/reason
- **RBAC**: `super_admin` / `org_admin` / `manager` / `worker`

## User personas
- **Org Admin**: sets up warehouses, imports catalog, invites team
- **Manager**: monitors dashboards, approves actions, manages inventory
- **Worker (frontline)**: scans, asks AI, checks stock, adjusts qty with reason

## What's implemented (Feb 2026)
### Backend
- JWT auth (`/api/auth/signup`, `/login`, `/me`), bcrypt, 7-day tokens
- Multi-tenant org isolation on every query via `org_id` from JWT
- Products CRUD + search (name/sku/barcode/brand/model/category)
- Warehouses + hierarchical Locations (zone→aisle→rack→shelf→bin) with recursive path builder
- Inventory list + low-stock filter + adjust + transfer (both audited)
- Barcode lookup + product detail with resolved warehouse/location path
- Image scan via Gemini 3 Flash — catalog-aware identification with matches
- AI chat SSE streaming (Claude/Gemini) + 4 controlled tools
- CSV/XLSX import with column auto-detect
- Users CRUD (org_admin only)
- Audit logs (org_admin + manager)
- Dashboard stats (KPIs + stock-by-warehouse + recent activity)
- Seeded admin `borgavakarshashikant@gmail.com` / `AdminPass@2026` with 8 sample products + Pune/Mumbai warehouses + full location hierarchy for SM-XYZ-2026

### Frontend
- Tactical dark theme (Barlow Condensed + Inter + JetBrains Mono) with amber `#F59E0B` primary
- Landing page with hero + AI chat mock + feature grid
- Login / Signup pages
- Sidebar layout with role-gated nav (mobile Sheet drawer)
- Dashboard: KPI cards + Recharts bar chart + recent activity feed + quick actions
- Products list + search + detail with inventory rows + adjust dialog
- Scan page: live ZXing camera + manual fallback + image upload for photo ID
- AI Chat: SSE streaming with tool badges + suggestions + model switcher
- Inventory table with low-stock filter tab
- Warehouses: add + location hierarchy with parent selector
- Users: invite + role select + deactivate
- CSV import wizard with result summary
- Audit logs table
- Sonner toasts throughout, data-testids on every interactive element

## Testing (iteration_1)
- 100% backend + 100% frontend on requested scope (see `/app/test_reports/iteration_1.json`)
- No blocking issues

## Backlog (P1)
- Voice assistant (Whisper multilingual EN/HI/MR) — module E
- Advanced approval workflows for destructive actions
- Real-time sync via webhooks + polling for external ERPs
- ERP connectors (REST/GraphQL/PostgreSQL/MySQL/MSSQL)
- PDF report generation
- Push notifications + email digests
- Product image upload + thumbnail generation
- Warehouse floor-plan visual (interactive tree)

## Backlog (P2)
- Native mobile shell (PWA install prompt)
- Barcode label PDF generator
- Bulk transfer wizard
- Supplier + purchase-order module
- More languages, timezone-aware audit

---

## Iteration 2 (Feb 2026): Voice, Connectors, Barcode Labels, Approvals

### Added
- **Voice** — `POST /api/voice/transcribe` (OpenAI Whisper via Emergent Universal Key, multilingual). Mic button in AI Chat that records via MediaRecorder → uploads webm → transcript auto-sends to chat.
- **ERP Connectors** — full CRUD `/api/connectors` supporting **REST API**, **PostgreSQL**, **MySQL** (SQLAlchemy). Field-mapping UI (source column → AIW field). `POST /:id/test` fetches 3 sample rows; `POST /:id/sync` upserts products. Passwords/auth values masked in list response.
- **Barcode Label Studio** — `GET /api/products/:id/label?kind=barcode|qr&count=10` returns A4 PDF (Code128 or QR) using python-barcode + qrcode + reportlab. "Barcode labels" & "QR labels" buttons on ProductDetail open PDF in a new tab.
- **Approval Workflow** — Workers submitting `POST /api/inventory/adjust` with |delta| > 50 are auto-routed into `approvals` collection instead of applied. Managers/admins see pending queue at `/app/approvals` with Approve/Reject dialogs. Approve executes the original adjust; both decisions are audited.

### Tested (curl e2e)
- REST connector to jsonplaceholder → 3 rows fetched, sample identified
- Barcode PDF → 14 KB response, `application/pdf`
- Worker +100 units → returned `{approval_required: true, approval_id: ...}`; +3 units → auto-applied
- Approval visible in admin UI with correct product, warehouse, delta and requester

### Backlog remaining
- Real-time sync via webhooks
- Scheduled connector polling (P1)
- Native mobile PWA shell
- Product image upload / thumbnails
- Supplier & purchase-order module
