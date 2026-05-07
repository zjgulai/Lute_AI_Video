# Admin Panel — Phase 1 Design Spec

**Status:** Draft
**Date:** 2026-05-06
**Author:** Claude (brainstorming with Pray)

## 1. Overview

### 1.1 Product Context

Short Video Agent (v0.2.0) is a multi-agent AI video creation pipeline targeting cross-border e-commerce. The platform is evolving from a self-hosted single-tenant tool toward a **multi-tenant SaaS** product. Currently there is no administrative interface — all operational tasks (tenant management, API key provisioning, error diagnostics, system health checks) require direct database access or CLI operations.

### 1.2 Goals

Build a **platform-level admin panel** (Phase 1) that gives the platform operator a web-based control plane for:

1. **Observability** — answer "is the system healthy right now?" in under 5 seconds
2. **Operability** — create and manage tenants and their API keys without touching the database
3. **Security boundary** — separate admin authentication from tenant API key authentication

### 1.3 Target User

The **platform operator** (Pray). Not tenants, not end-users. The admin panel is an operational tool for the person running the SaaS platform.

### 1.4 Non-Goals (Phase 1)

- Tenant self-service workspace (tenants managing their own projects, assets, team members)
- Admin account registration UI (manual seed script only)
- Cross-tenant asset browsing
- LLM provider configuration UI (remains .env + restart)
- Usage/billing dashboards
- Content moderation queue
- Admin action audit log

---

## 2. Authentication & Authorization Model

### 2.1 Two-Layer Auth Architecture

```
┌─────────────────────────────────────────────────┐
│  Admin Auth Layer (NEW)                         │
│  Mechanism: email + password → session cookie    │
│  Scope: /api/admin/* endpoints                   │
│  Isolation: entirely independent of API key auth │
├─────────────────────────────────────────────────┤
│  Creative API Auth Layer (EXISTING, unchanged)   │
│  Mechanism: tenant API key → x-api-key header    │
│  Scope: /scenario/*, /pipeline/*, /assets/*, etc.│
│  Isolation: admin auth never touches this layer  │
└─────────────────────────────────────────────────┘
```

**Key principle:** The admin never needs a tenant's API key to perform administrative operations. Admin auth and tenant API key auth are two completely independent channels. There is no "super key" that grants admin access — the admin logs in with credentials, not API keys.

### 2.2 Login Flow

```
1. POST /api/admin/auth/login { email, password }
2. bcrypt.compare(password, stored_hash) — work factor 12
3. Generate 64 random bytes → admin session token
4. SHA-256(token) → INSERT INTO admin_sessions
5. Set-Cookie: admin_session=<raw_token>
   - HttpOnly: true
   - Secure: true (production) / false (localhost dev)
   - SameSite: Lax
   - Path: /api/admin
   - Max-Age: 86400 (24 hours)
6. Response: 200 { admin_id, email }
```

### 2.3 Session Validation Middleware

`verify_admin_session` dependency function (mirrors `verify_api_key` pattern):

```
1. Read admin_session cookie from request
2. SHA-256(cookie_value) → token_hash
3. SELECT FROM admin_sessions WHERE token_hash = $1 AND expires_at > NOW()
4. If valid → resolve admin_id, inject into context
5. If invalid/expired → 401 { error: "Invalid or expired session" }
```

### 2.4 Rate Limiting

- Login endpoint: max 5 attempts per minute per IP (separate from the general 120r/m rate limit)
- General admin endpoints: reuse existing nginx rate limit (120r/m per IP)

### 2.5 Initial Admin Account

- Created via CLI script: `python scripts/create_admin.py <email> <password>`
- No registration UI in Phase 1
- Script checks if any admin exists; if yes, exits with "admin already exists" unless `--force` flag is passed

---

## 3. Feature Modules

### 3.1 Module Overview

Four modules for Phase 1. No more, no less.

| Module | Page Route | Purpose |
|--------|-----------|---------|
| Dashboard | `/admin/dashboard` | 5-second system overview |
| Tenant Management | `/admin/tenants` | CRUD tenants + API key lifecycle |
| System Logs | `/admin/logs` | Persistent error log viewer |
| System Health | `/admin/health` | Service status dashboard |

### 3.2 Dashboard

**Purpose:** Answer "is the system healthy?" in one glance.

**Metrics displayed:**
- **Tenant count** — total active tenants + today's new registrations
- **Pipeline runs today** — total / success / failed / running (stacked indicator)
- **Error rate (24h)** — percentage of pipeline runs that degraded (entered degraded state)
- **Recent errors** — last 10 entries from error_logs table, showing timestamp, tenant, error code, first 100 chars of message

**Interactions:**
- Click tenant count → navigate to `/admin/tenants`
- Click pipeline metrics → navigate to `/admin/logs?filter=degraded`
- Click any error row → open log detail

**Refresh:** Manual refresh button. No auto-polling (avoids unnecessary load).

### 3.3 Tenant Management

**List view (`/admin/tenants`):**

Table columns: tenant_id, display_name, contact_email, status (active/disabled chip), key_count, created_at, last_active. Paginated (20 per page). Search by tenant_id or display_name (ILIKE).

**Create tenant (`/admin/tenants/new` or modal):**

Form fields: tenant_id (required, unique, pattern `^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$` — lowercase alphanumeric + hyphens, 3–32 chars, no leading/trailing hyphens), display_name (required), contact_email (optional). Format enforced on both frontend form validation and backend (422 rejection on violation). No API key generated at creation time — keys are a separate operation.

**Disable confirmation:** Must type tenant_id to confirm (prevents accidental disable). Disabling a tenant sets `tenants.status = 'disabled'` AND sets `revoked_at = NOW()` on all active API keys for that tenant. Existing pipeline sessions using those keys fail on the next auth check.

**Tenant detail (`/admin/tenants/[tenant_id]`):**

Three sections:
1. **Info card** — tenant_id, display_name, contact_email, status, created_at. Edit button for display_name and contact_email. Enable/Disable toggle.
2. **API Keys table** — all keys for this tenant with: key_id (first 8 chars of hash), label, created_at, last_used_at, status (active/revoked/expired). Action buttons: Create New Key, Revoke (per key).
3. **Recent activity** — last 20 pipeline runs for this tenant from the pipeline_states table (label, scenario, status, started_at).

**Create API Key flow:**
```
1. Click "Create New Key" → confirmation dialog
2. Backend generates 32 random bytes → plaintext key
3. SHA-256(plaintext) → INSERT INTO api_keys
4. Response returns the plaintext key ONCE
5. Frontend shows modal: "New API Key — copy it now, it won't be shown again"
   - Copy button (copies to clipboard)
   - Visual key display with mask/unmask toggle
   - Warning text: "Store this key securely. You will not be able to retrieve it later."
6. After user clicks "Done, I've saved it" → modal closes, keys table refreshes
```

### 3.4 System Logs

**Log viewer (`/admin/logs`):**

Table columns: timestamp, tenant_id, scenario, error_code, message (truncated to 150 chars). Paginated (50 per page). Sorted by created_at DESC.

**Filters:**
- Time range: last 1h / 6h / 24h / 7d / custom date range
- Error level: ERROR / WARNING / INFO (default: all)
- Scenario: s1-s5 dropdown
- Tenant ID: text search

**Log detail (expandable row or modal):**
- Full timestamp
- Tenant ID + link to tenant detail
- Scenario
- Error code
- Full message
- Traceback (monospace, scrollable)
- Copy traceback button

**Data retention:** Rows older than `ADMIN_LOG_RETENTION_DAYS` (env var, default 30) are deleted by a periodic cleanup task (runs every hour, deletes in batches of 1000 to avoid table locks). Setting `ADMIN_LOG_RETENTION_DAYS=0` disables automatic cleanup entirely.

### 3.5 System Health

**Status dashboard (`/admin/health`):**

Service status cards (one per service):
- **PostgreSQL** — connection check + latency_ms + tables_exist boolean
- **DeepSeek API** — connectivity check (simple models list or ping endpoint)
- **POYO API** — connectivity check
- **SiliconFlow API (CosyVoice)** — connectivity check
- **Remotion Renderer** — environment validation

Each card shows:
- Status indicator: green (healthy), yellow (degraded — slow but working), red (unreachable)
- Last checked time
- Latency in ms (if green)

**Health check history:**
- Table below cards showing last 24h of checks (one row per check cycle)
- Background task runs health checks every 5 minutes (on the backend, not the frontend)

**Manual refresh:** "Check Now" button triggers an immediate health check cycle.

---

## 4. Frontend Architecture

### 4.1 Route Structure

```
web/src/app/admin/
├── layout.tsx              → AdminLayout (sidebar + header + auth guard)
├── page.tsx                → Redirect to /admin/dashboard
├── dashboard/page.tsx      → Dashboard page
├── tenants/
│   ├── page.tsx            → Tenant list
│   └── [tenantId]/page.tsx → Tenant detail
├── logs/page.tsx           → Log viewer
└── health/page.tsx         → System health
```

### 4.2 AdminLayout Component

Structure:
```
┌──────────────────────────────────────────────────┐
│ Header bar: "AI Video Admin" | admin email | Logout│
├──────────┬───────────────────────────────────────┤
│ Sidebar  │                                       │
│          │                                       │
│ 📊 Dash  │        Content area                    │
│ 👥 Tenants│        (child route)                  │
│ 📋 Logs  │                                       │
│ ❤️ Health│                                       │
│          │                                       │
└──────────┴───────────────────────────────────────┘
```

**Design constraints:**
- Reuse Warm Light theme colors (`#FDF8F6` background, `#D75C70` accent) from the main app
- No film grain / vignette overlay (admin is a tool, not a creative experience)
- Sidebar: 220px wide, collapsible to 60px (icon-only mode)
- Active route highlighted with Fortune Red accent
- Responsive: sidebar collapses to top nav on mobile (< 768px)

### 4.3 Auth Guard

`AdminAuthGuard` component wraps all admin routes:

```
1. On mount: GET /api/admin/auth/session
2. If 401 → redirect to /admin/login
3. If 200 → render children
4. 401 on any subsequent API call → redirect to /admin/login (session expired)
```

Login page (`/admin/login`): standalone page with email + password form, no sidebar. On success, redirect to `/admin/dashboard`.

### 4.4 API Client

Extend existing `web/src/components/api.ts` with admin-specific functions:

```typescript
// Admin API client — uses session cookie auth (no API key header)
async function adminFetch(path: string, options?: RequestInit): Promise<any>;
```

Key differences from `apiFetch`:
- Does NOT send `x-api-key` header
- `credentials: 'include'` to send the session cookie
- Error handling: on 401, redirect to login; on other errors, return structured error

### 4.5 Component Tree

```
AdminLayout
├── AdminSidebar
│   ├── AdminNavItem (Dashboard)
│   ├── AdminNavItem (Tenants)
│   ├── AdminNavItem (Logs)
│   └── AdminNavItem (Health)
├── AdminHeader
│   ├── Breadcrumb
│   ├── AdminEmail
│   └── LogoutButton
└── {children}

Dashboard
├── MetricCard (Tenant Count)
├── MetricCard (Pipeline Runs)
├── MetricCard (Error Rate)
└── RecentErrorsList
    └── ErrorRow (×10)

TenantList
├── SearchBar
├── CreateTenantButton → CreateTenantModal
├── TenantTable
│   └── TenantRow (×N)
└── Pagination

TenantDetail
├── TenantInfoCard
│   └── EditTenantModal
├── ApiKeysTable
│   ├── CreateKeyButton → CreateKeyModal (shows plaintext once)
│   └── ApiKeyRow (×N)
│       └── RevokeKeyButton (confirm dialog)
└── RecentActivityTable

LogViewer
├── LogFilters (time range, level, scenario, tenant)
├── LogTable
│   └── LogRow (×N)
│       └── LogDetailModal
└── Pagination

HealthDashboard
├── ServiceStatusCards (5 cards)
├── CheckNowButton
└── HealthHistoryTable
```

---

## 5. Backend Architecture

### 5.1 Router & Mount Point

New file: `src/routers/admin.py`

Mounted in `src/api.py`:
```python
from src.routers.admin import router as admin_router
app.include_router(admin_router, prefix="/api/admin")
```

**Note on prefix:** The existing router prefix pattern uses `/pipeline/*`, `/scenario/*`, etc. Admin uses `/api/admin/*` to clearly separate it from the creative API surface. The nginx rate limit configuration exempts `/api/admin/auth/login` from the general rate limit (it has its own stricter limit).

### 5.2 API Endpoints

All endpoints return JSON with the standard `_meta` wrapper (trace_id, duration_ms, version, timestamp).

#### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/admin/auth/login` | None (rate limited) | Login with email + password |
| POST | `/api/admin/auth/logout` | Session | Logout, clear session |
| GET | `/api/admin/auth/session` | Session | Validate current session |

**POST /api/admin/auth/login**
```
Request:  { email: str, password: str }
Response: 200 { admin_id: int, email: str, _meta: {...} }
Errors:   401 { error: "Invalid credentials" }
          429 { error: "Too many attempts" }
```
Response includes `Set-Cookie: admin_session=<token>; HttpOnly; Secure; SameSite=Lax; Path=/api/admin; Max-Age=86400`

#### Dashboard

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/admin/dashboard/summary` | Session | Aggregated dashboard data |

**GET /api/admin/dashboard/summary**
```
Response: 200 {
  tenant_count: int,
  tenant_count_today: int,
  pipeline_runs_today: {
    total: int,
    success: int,
    failed: int,
    running: int
  },
  error_rate_24h: float,  // 0.0 - 1.0
  recent_errors: [
    {
      id: int,
      tenant_id: str,
      scenario: str,
      error_code: str,
      message: str,  // first 150 chars
      created_at: str  // ISO 8601
    }
  ]
}
```

#### Tenants

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/admin/tenants` | Session | List tenants (paginated, searchable) |
| POST | `/api/admin/tenants` | Session | Create tenant |
| GET | `/api/admin/tenants/{tenant_id}` | Session | Tenant detail |
| PUT | `/api/admin/tenants/{tenant_id}` | Session | Update tenant (enable/disable, edit info) |
| POST | `/api/admin/tenants/{tenant_id}/keys` | Session | Create API key for tenant |
| POST | `/api/admin/tenants/{tenant_id}/keys/{key_id}/revoke` | Session | Revoke API key |

**GET /api/admin/tenants**
```
Query:    ?page=1&limit=20&q=<search>&status=active|disabled|all
Response: 200 {
  items: [{ id, tenant_id, display_name, contact_email, status,
            key_count, created_at, last_active }],
  total: int,
  page: int,
  limit: int
}
```

**POST /api/admin/tenants**
```
Request:  { tenant_id: str, display_name: str, contact_email?: str }
Response: 201 { id: int, tenant_id: str, display_name: str,
                contact_email: str, status: "active", created_at: str }
Errors:   409 { error: "Tenant ID already exists" }
          422 { error: "Validation failed", fields: {...} }
```

**PUT /api/admin/tenants/{tenant_id}**
```
Request:  { display_name?: str, contact_email?: str, status?: "active"|"disabled" }
Response: 200 { ...updated tenant fields... }
Side effect (status=disabled): UPDATE api_keys SET revoked_at=NOW()
  WHERE tenant_id=$1 AND revoked_at IS NULL
```

**POST /api/admin/tenants/{tenant_id}/keys**
```
Request:  { label?: str }
Response: 201 { key_id: int, tenant_id: str, api_key: str,  // PLAINTEXT — only once
                label: str, created_at: str }
Note:     api_key is the raw plaintext key. The backend stores only SHA-256(key).
          This is the ONLY response that returns the key in plaintext.
```

**POST /api/admin/tenants/{tenant_id}/keys/{key_id}/revoke**
```
Response: 200 { success: true, key_id: int, revoked_at: str }
```

#### Logs

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/admin/logs` | Session | List error logs (paginated, filtered) |
| GET | `/api/admin/logs/{log_id}` | Session | Log detail with full traceback |

**GET /api/admin/logs**
```
Query:    ?page=1&limit=50&level=&scenario=&tenant_id=&from=&to=
Response: 200 {
  items: [{ id, tenant_id, scenario, error_code, message,
            created_at }],
  total: int, page: int, limit: int
}
```

#### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/admin/health/status` | Session | Current service health |
| GET | `/api/admin/health/history` | Session | Recent health check records |

**GET /api/admin/health/status**
```
Response: 200 {
  checked_at: str,  // ISO 8601
  services: {
    postgres:    { status: "healthy"|"degraded"|"down", latency_ms: float },
    deepseek:    { status: ..., latency_ms: float },
    poyo:        { status: ..., latency_ms: float },
    siliconflow: { status: ..., latency_ms: float },
    remotion:    { status: ..., available: bool }
  }
}
```

### 5.3 Dependency Injection

Admin dependencies follow the existing `src/routers/_deps.py` pattern. New file: `src/routers/_admin_deps.py`:

```python
# _admin_deps.py
import contextvars
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Cookie, HTTPException, Request

_admin_id_var: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "admin_id", default=None
)

async def verify_admin_session(
    request: Request,
    admin_session: str | None = Cookie(None),
) -> int:
    """Validate admin session cookie, return admin_id."""
    if not admin_session:
        raise HTTPException(status_code=401, detail="Missing session")
    
    token_hash = hashlib.sha256(admin_session.encode()).hexdigest()
    
    # Query admin_sessions table
    row = await fetch_admin_session(token_hash)
    if not row or row["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    _admin_id_var.set(row["admin_id"])
    return row["admin_id"]
```

### 5.4 Auth Endpoint Implementation Detail

**POST /api/admin/auth/login** — special considerations:

- Rate limit: use a simple in-memory dict with IP key + timestamp, max 5 attempts per minute (NOT stored in PG — avoids DB dependency for rate limiting)
- Password comparison: `bcrypt.checkpw(password.encode(), stored_hash.encode())` — use constant-time comparison only (bcrypt handles this)
- Generic error message: "Invalid credentials" regardless of whether email exists or password is wrong (prevents enumeration)
- On success: generate 64 random bytes via `secrets.token_bytes(64)`, store SHA-256 hash in `admin_sessions`, return raw bytes as cookie value

### 5.5 Error Log Persistence

Currently `src/telemetry.py` `error_collector` only stores errors in memory (FIFO, last 100). For the admin log viewer to work:

1. Add a `persist_error()` function call at the end of `error_collector.add_error()`
2. `persist_error()` inserts into `error_logs` table (async, fire-and-forget — don't block the pipeline on log persistence)
3. Cleanup task: `DELETE FROM error_logs WHERE created_at < NOW() - INTERVAL '30 days'` in batches of 1000, executed every hour via asyncio background task registered in `api.py` startup

### 5.6 Health Check Background Task

Registered in `api.py` startup:

```python
async def health_check_loop():
    while True:
        await asyncio.sleep(300)  # every 5 minutes
        results = {}
        for service in ["postgres", "deepseek", "poyo", "siliconflow", "remotion"]:
            status, latency = await check_service(service)
            results[service] = {"status": status, "latency_ms": latency}
        # Store results in memory (last 288 entries = 24h)
        _health_history.append({"checked_at": datetime.now(timezone.utc), "services": results})
```

Health history is in-memory only (not persisted to PG). On restart, the history starts fresh — acceptable for Phase 1.

Each health check reuses the existing LLM client instances (`LLMClient`, `PoyoClient`, `CosyVoiceClient`) to verify authentic connectivity (full auth + network path). For DeepSeek, a minimal 1-token completion is used; for POYO and SiliconFlow, lightweight model-list or ping-equivalent calls. This validates the real production path without requiring dedicated ping endpoints.

Three background tasks run in `api.py` startup:
1. **Health check loop** — every 5 minutes
2. **Log retention cleanup** — every hour, respects `ADMIN_LOG_RETENTION_DAYS`
3. **Expired session cleanup** — every hour, `DELETE FROM admin_sessions WHERE expires_at < NOW()`

---

## 6. Data Model

### 6.1 New Tables

**admin_accounts**
```sql
CREATE TABLE admin_accounts (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);
```

**admin_sessions**
```sql
CREATE TABLE admin_sessions (
    id SERIAL PRIMARY KEY,
    admin_id INTEGER NOT NULL REFERENCES admin_accounts(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_admin_sessions_token_hash ON admin_sessions(token_hash);
CREATE INDEX idx_admin_sessions_expires ON admin_sessions(expires_at);
```
A background task runs every hour to purge expired sessions: `DELETE FROM admin_sessions WHERE expires_at < NOW()`.

**tenants**
```sql
CREATE TABLE tenants (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) UNIQUE NOT NULL
        CHECK (tenant_id ~ '^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$'),
    display_name VARCHAR(255) NOT NULL DEFAULT '',
    contact_email VARCHAR(255) NOT NULL DEFAULT '',
    status VARCHAR(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
Backend additionally validates tenant_id against the same regex at the API layer, returning 422 with a descriptive message on mismatch — the DB CHECK is a defense-in-depth measure.

**error_logs**
```sql
CREATE TABLE error_logs (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(64),
    scenario VARCHAR(64),
    error_code VARCHAR(32),
    message TEXT NOT NULL,
    traceback TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_error_logs_created_at ON error_logs(created_at DESC);
CREATE INDEX idx_error_logs_tenant_created ON error_logs(tenant_id, created_at DESC);
```

### 6.2 Existing Tables (No Migration Needed)

**api_keys** — already created by Alembic migration `1ffe98505ace`. Columns include: `id`, `tenant_id`, `key_hash`, `permissions`, `expires_at`, `revoked_at`, `last_used_at`, `created_at`. The admin panel reads and writes this table through the existing schema — no changes required.

### 6.3 Alembic Migration

Single new migration: `2_admin_panel_phase1.py` creating the four tables above.

### 6.4 Seed Script

`scripts/create_admin.py`:
```python
"""Create the initial admin account. Run once during setup."""
import sys
import bcrypt

def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/create_admin.py <email> <password>")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    
    if len(password) < 12:
        print("Error: password must be at least 12 characters")
        sys.exit(1)
    
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    
    # Connect to DB, INSERT INTO admin_accounts
    # If admin already exists, warn and exit unless --force
    ...
```

---

## 7. Key Data Flows

### 7.1 Admin Login
```
Browser                     Backend                     Database
  │                            │                           │
  ├─ POST /auth/login ────────►│                           │
  │  {email, password}         │                           │
  │                            ├─ SELECT password_hash ───►│
  │                            │◄── row ──────────────────│
  │                            │                           │
  │                            ├─ bcrypt.compare()         │
  │                            │                           │
  │                            ├─ gen 64 random bytes      │
  │                            ├─ SHA-256(bytes)           │
  │                            ├─ INSERT admin_sessions ──►│
  │                            │◄── ok ───────────────────│
  │                            │                           │
  │◄── 200 + Set-Cookie ──────┤                           │
```

### 7.2 Create Tenant (No Key)
```
Browser                     Backend                     Database
  │                            │                           │
  ├─ POST /admin/tenants ─────►│                           │
  │  {tenant_id, name, ...}    │                           │
  │                            ├─ Validate unique ────────►│
  │                            │◄── ok ───────────────────│
  │                            ├─ INSERT tenants ─────────►│
  │                            │◄── row ──────────────────│
  │◄── 201 { tenant } ────────┤                           │
```

### 7.3 Create API Key for Existing Tenant
```
Browser                     Backend                     Database
  │                            │                           │
  ├─ POST /tenants/X/keys ────►│                           │
  │  {label: "production"}     │                           │
  │                            ├─ Verify tenant exists ───►│
  │                            │◄── active ───────────────│
  │                            ├─ gen 32 random bytes      │
  │                            ├─ SHA-256(key)             │
  │                            ├─ INSERT api_keys ────────►│
  │                            │◄── ok ───────────────────│
  │◄── 201 { key_id,           │                           │
  │    api_key: "raw_plain" } ─┤                           │
  │                            │                           │
  │  [Frontend shows modal     │                           │
  │   with raw key once.       │                           │
  │   Discards after close.]   │                           │
```

### 7.4 Disable Tenant (Cascade Revoke)
```
Browser                     Backend                     Database
  │                            │                           │
  ├─ PUT /tenants/X ──────────►│                           │
  │  {status: "disabled"}      │                           │
  │                            ├─ BEGIN TRANSACTION        │
  │                            ├─ UPDATE tenants ─────────►│
  │                            │  SET status='disabled'     │
  │                            ├─ UPDATE api_keys ────────►│
  │                            │  SET revoked_at=NOW()      │
  │                            │  WHERE tenant_id=X AND    │
  │                            │    revoked_at IS NULL      │
  │                            ├─ COMMIT ─────────────────►│
  │                            │◄── ok ───────────────────│
  │◄── 200 { updated } ───────┤                           │
```

---

## 8. Security Considerations

### 8.1 Password Storage
- bcrypt with work factor 12 (tunable via env var `BCRYPT_ROUNDS`)
- Never log password or password hash

### 8.2 Session Security
- Token: 64 random bytes from `secrets.token_bytes()` (cryptographically secure)
- Stored as SHA-256 hash in database (not plaintext — same pattern as API keys)
- Cookie flags: HttpOnly, Secure (prod), SameSite=Lax
- Absolute expiry: 24 hours, no sliding extension
- No "remember me" in Phase 1

### 8.3 API Key Handling
- Plaintext key generated server-side, returned exactly once
- Only SHA-256 hash stored in database
- No endpoint to retrieve a previously created key's plaintext (by design)
- Revocation is immediate (sets `revoked_at`, no delay)

### 8.4 Login Protection
- Rate limit: 5 attempts per minute per IP (in-memory, not persistent)
- Generic error message: "Invalid credentials" regardless of cause
- No password reset flow in Phase 1 (manual admin intervention via script)

### 8.5 CORS
- Admin endpoints follow the same CORS_ORIGINS configuration as the main API
- No cross-origin access unless explicitly configured

---

## 9. Error Handling

### 9.1 Conventions
- All admin API responses use the existing `_meta` wrapper (trace_id, duration_ms, version, timestamp)
- Internal errors: return generic message + trace_id, log full error to structlog
- Validation errors: return 422 with field-level details
- Auth errors: return 401 with generic message (no user enumeration)

### 9.2 Frontend Error States
Each page handles four states:
1. **Loading** — skeleton/spinner while data loads
2. **Empty** — "No tenants yet" / "No errors found" with appropriate messaging
3. **Error** — inline error banner with message + retry button
4. **Data** — normal data display

### 9.3 Backend Error Classification
Admin-specific errors use the existing `error_classifier`:
- `ADMIN_AUTH_FAILED` — login failures
- `ADMIN_SESSION_EXPIRED` — expired sessions
- `ADMIN_TENANT_NOT_FOUND` — invalid tenant_id in URL
- `ADMIN_KEY_NOT_FOUND` — invalid key_id
- `ADMIN_VALIDATION` — input validation errors

---

## 10. Testing Strategy

### 10.1 Backend Tests

| Test File | Scope |
|-----------|-------|
| `tests/admin/test_admin_auth.py` | Login flow, logout, session validation, rate limiting, invalid credentials |
| `tests/admin/test_admin_tenants.py` | CRUD, disable cascade, status transitions, duplicate tenant_id rejection |
| `tests/admin/test_admin_keys.py` | Key creation, plaintext response, revocation, revoked key auth rejection |
| `tests/admin/test_admin_logs.py` | Listing, pagination, filtering by time/level/scenario/tenant, detail view |
| `tests/admin/test_admin_health.py` | Status checks, history endpoint, all services reporting |

### 10.2 Frontend Tests

| Test File | Scope |
|-----------|-------|
| `web/src/app/admin/__tests__/AdminLogin.test.tsx` | Form validation, error display, redirect on success |
| `web/src/app/admin/__tests__/AdminDashboard.test.tsx` | Data loading, metric cards, click navigation |
| `web/src/app/admin/__tests__/AdminTenants.test.tsx` | List rendering, create flow, disable confirmation, key modal |
| `web/src/app/admin/__tests__/AdminLogs.test.tsx` | Filter controls, pagination, detail modal |

### 10.3 Integration Tests
- End-to-end: create tenant → create key → use key to run a pipeline → verify pipeline appears in tenant detail
- Session expiry: log in → wait (or mock expiry) → verify 401 on admin endpoint → verify redirect to login

---

## 11. Implementation Sequence

1. **Database migration** — Alembic migration for 4 new tables
2. **Backend: auth** — `_admin_deps.py`, login/logout/session endpoints, seed script
3. **Backend: tenants** — CRUD endpoints + key management
4. **Backend: logs** — error persistence + query endpoints
5. **Backend: health** — service check endpoints + background task
6. **Frontend: layout** — AdminLayout + AdminSidebar + AdminHeader + auth guard
7. **Frontend: login** — login page (standalone, no sidebar)
8. **Frontend: dashboard** — metric cards + recent errors
9. **Frontend: tenants** — list, create modal, detail page, key management modals
10. **Frontend: logs** — table, filters, detail modal
11. **Frontend: health** — service cards + history table
12. **Integration testing** — end-to-end flow verification
13. **Deploy** — Lighthouse production, nginx config update if needed

---

## 12. Resolved Design Decisions

1. **Admin session cleanup:** Periodic cleanup task deletes expired sessions (`WHERE expires_at < NOW()`) every hour. Registered in `api.py` startup alongside the health check loop and log retention task.

2. **Tenant ID format:** Enforced both frontend and backend. Pattern: `^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$` (lowercase alphanumeric + hyphens, 3-32 chars, no leading/trailing hyphens). Backend rejects with 422 on violation.

3. **Log retention:** Configurable via env var `ADMIN_LOG_RETENTION_DAYS` (default 30). Cleanup task respects this value. Setting to 0 disables automatic cleanup.

4. **Health check external API calls:** Reuses existing LLM client instances (DeepSeek, POYO, SiliconFlow) for authentic connectivity testing — a simple lightweight request (e.g., model list or 1-token completion) that validates the full auth + network path. No dedicated ping endpoints needed.

---

## 13. Revision History

| Date | Change |
|------|--------|
| 2026-05-06 | Initial draft — Phase 1 admin panel design |
| 2026-05-06 | Resolved 4 open decisions: session cleanup task, backend tenant_id format enforcement, log retention env var, health check reuses existing LLM clients |
