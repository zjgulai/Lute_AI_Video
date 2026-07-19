---
title: Enterprise AI Content Wave 1A Access and Submit Safety Implementation Plan
doc_type: workflow
module: project
topic: enterprise-ai-content-wave1a-access-submit-safety
status: active
created: 2026-07-11
updated: 2026-07-11
owner: self
source: human+ai
---

# Enterprise AI Content Wave 1A Access and Submit Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four P0 paths that can expose tenant media or create uncontrolled real-provider submissions before broader all-scenario work continues.

**Architecture:** Route every protected media read through a tenant-bound signed URL, normalize the same generation-safety fields for Fast and S1–S5, make browser mutations zero-retry and remove implicit S1 provider work, then make production token smoke single-spec and machine-authorized. Public assets remain a narrow explicit allowlist; all provider, deploy, publish, and production-write execution remains outside this plan.

**Tech Stack:** FastAPI/Python 3.12+, HMAC signed URLs, pytest, Next.js 16/React 19/TypeScript, Vitest, Nginx, GitHub Actions/Playwright.

## Global Constraints

- Work only on `codex/enterprise-ai-content-closure-20260711` in the current checkout; project instructions prohibit a default worktree.
- Do not commit, push, open a PR, merge, deploy, call providers, publish, send webhooks, read secret values, or write production data without a later exact authorization.
- Protected media includes tenant uploads, `tenants/*`, `pending_review`, `quarantine`, renders and generated intermediate/final files that have not been explicitly made public.
- Anonymous media access is allowed only for the explicit public roots `brand_assets` and `demo` in this wave.
- Cross-tenant protected-media lookups return `404`; missing/invalid credentials or signatures never fall back to unsigned access.
- Mutation methods `POST`, `PUT`, `PATCH`, and `DELETE` receive zero automatic browser retry in this wave.
- Token smoke is one approved spec per run with `--workers=1 --retries=0`, an explicit submit/job cap, budget and pending-review-only disposition.
- All behavior changes use RED → GREEN → focused regression → independent task review.

---

## File Map

| Responsibility | Files |
|---|---|
| Media ownership, signing and serving | `src/routers/media.py` |
| Frontend signed-media resolution | `web/src/components/api.ts`, `web/src/hooks/useSignedMediaUrl.ts`, `web/src/components/RuntimeMediaImage.tsx` |
| Canonical Nginx media route | `deploy/lighthouse/ai_video_locations.conf` |
| Media security regressions | `tests/test_p0_media_tenant_security.py`, `tests/test_lighthouse_media_auth_contract.py`, `tests/test_backend_route_auth_contract.py`, `web/src/components/mediaUrlSanitizer.test.ts` |
| Generation safety policy | `src/pipeline/generation_policy.py`, `src/routers/scenario.py`, `src/routers/_state.py` |
| Safety-policy contracts | `tests/test_scenario_generation_safety_policy.py`, `web/src/lib/scenarioPayload.test.ts` |
| Browser submit behavior | `web/src/components/api.ts`, `web/src/components/RecommendPanel.tsx`, `web/src/app/page.tsx` |
| Browser submit regressions | `web/src/components/apiFetchErrorNormalization.test.ts`, `web/src/components/RecommendPanel.test.tsx`, `web/src/app/__tests__/page-smoke.test.ts` |
| Token-smoke control plane | `.github/workflows/e2e-prod.yml`, `web/playwright.prod.config.ts`, `scripts/l4c_token_smoke_plan.py` |
| Token-smoke contracts | `tests/test_l4c_token_smoke_plan.py`, `tests/test_token_smoke_preflight.py`, `tests/test_fast_mode_token_smoke_contract.py` |

---

### Task 1: Enforce Backend Tenant-Bound Protected Media Access

**Files:**

- Modify: `src/routers/media.py`
- Modify: `deploy/lighthouse/ai_video_locations.conf`
- Modify: `configs/backend-route-auth-contract.yaml`
- Modify: `docs/runbooks/backend-route-auth-contract.md`
- Modify: `tests/test_p0_media_tenant_security.py`
- Modify: `tests/test_backend_route_auth_contract.py`
- Create: `tests/test_lighthouse_media_auth_contract.py`

**Interfaces:**

- Produces: `classify_media_scope(canonical_path: str) -> str | None`, where `None` means explicit public and any string is the owning tenant scope.
- Produces: `authorize_media_path(canonical_path: str, tenant_id: str) -> None`, raising `HTTPException(404)` on cross-tenant access.
- Produces: `sign_media_url(media_path: str, *, tenant_id: str, purpose: Literal["view", "download"] = "view", expires_in_sec: int = 900) -> str`.
- Consumes: `AuthContext` from `verify_api_key()` only at `/api/media/sign`; the signing endpoint never accepts a client-supplied tenant id.

- [x] **Step 1: Write backend RED tests for anonymous, cross-tenant and signed-owner access**

Add focused tests to `tests/test_p0_media_tenant_security.py` using a temporary output tree:

```python
def _tenant_file(root: Path, tenant: str, name: str = "proof.png") -> Path:
    target = root / "tenants" / tenant / "pending_review" / "sample" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"protected")
    return target


def test_protected_media_rejects_unsigned_request(tmp_path, monkeypatch):
    from src.routers import media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    app = FastAPI()
    app.include_router(media.router)

    response = TestClient(app).get(
        "/api/media/tenants/tenant-a/pending_review/sample/proof.png"
    )

    assert response.status_code in {401, 403}


def test_cross_tenant_cannot_sign_protected_media(tmp_path, monkeypatch):
    from src.routers import media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)

    with auth_context("tenant-b"), pytest.raises(HTTPException) as exc:
        media.sign_media_url(
            "tenants/tenant-a/pending_review/sample/proof.png",
            tenant_id="tenant-b",
        )

    assert exc.value.status_code == 404


def test_owner_signed_url_serves_protected_media(tmp_path, monkeypatch):
    from src.routers import media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    with auth_context("tenant-a"):
        signed = media.sign_media_url(
            "tenants/tenant-a/pending_review/sample/proof.png",
            tenant_id="tenant-a",
        )

    app = FastAPI()
    app.include_router(media.router)
    response = TestClient(app).get(signed)

    assert response.status_code == 200
    assert response.content == b"protected"
```

- [x] **Step 2: Run the backend RED tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_p0_media_tenant_security.py::test_protected_media_rejects_unsigned_request \
  tests/test_p0_media_tenant_security.py::test_cross_tenant_cannot_sign_protected_media \
  tests/test_p0_media_tenant_security.py::test_owner_signed_url_serves_protected_media \
  -q
```

Expected: the unsigned request currently returns `200`, and the new tenant-bound signing interface is absent or does not reject tenant B.

- [x] **Step 3: Add RED tests for explicit public roots, token tampering and basename fallback removal**

Add:

```python
def test_explicit_public_media_allows_unsigned_request(tmp_path, monkeypatch):
    from src.routers import media

    target = tmp_path / "brand_assets" / "brand" / "logo.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"public")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    app = FastAPI()
    app.include_router(media.router)

    response = TestClient(app).get("/api/media/brand_assets/brand/logo.png")

    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("public")


def test_signed_token_is_bound_to_tenant_path_and_purpose(tmp_path, monkeypatch):
    from src.routers import media

    _tenant_file(tmp_path, "tenant-a")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    signed = media.sign_media_url(
        "tenants/tenant-a/pending_review/sample/proof.png",
        tenant_id="tenant-a",
        purpose="view",
    )

    app = FastAPI()
    app.include_router(media.router)
    assert TestClient(app).get(signed.replace("tenant=tenant-a", "tenant=tenant-b")).status_code == 403
    assert TestClient(app).get(signed.replace("purpose=view", "purpose=download")).status_code == 403


def test_missing_nested_path_does_not_fall_back_by_basename(tmp_path, monkeypatch):
    from src.routers import media

    target = tmp_path / "seedance" / "proof.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"wrong file")
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)

    with pytest.raises(HTTPException) as exc:
        media.sign_media_url(
            "tenants/tenant-a/pending_review/missing/proof.png",
            tenant_id="tenant-a",
        )

    assert exc.value.status_code == 404
```

Run the three tests and confirm the public cache policy, purpose binding and exact-path behavior are not yet implemented.

- [x] **Step 4: Implement the minimal media ownership and signed-token model**

In `src/routers/media.py`:

```python
PUBLIC_MEDIA_ROOTS = frozenset({"brand_assets", "demo"})


def classify_media_scope(canonical_path: str) -> str | None:
    parts = Path(canonical_path).parts
    if not parts:
        raise HTTPException(status_code=400, detail="Invalid path")
    if parts[0] in PUBLIC_MEDIA_ROOTS:
        return None
    if parts[0] == "tenants" and len(parts) >= 3:
        return parts[1]
    if parts[0] == "uploads" and len(parts) >= 3:
        return parts[1]
    return "default"


def authorize_media_path(canonical_path: str, tenant_id: str) -> None:
    owner = classify_media_scope(canonical_path)
    if owner is None:
        return
    if owner != tenant_id:
        raise HTTPException(status_code=404, detail="File not found")
```

Change the token payload to bind `canonical_path`, `tenant_id`, `purpose`, and `expires_at`. The signed URL must carry only `token`, `expires`, `tenant`, and `purpose` query parameters. `sign_media_url()` resolves the exact path, checks `tenant_id` owns it, then signs. `serve_media()` allows unsigned access only when `classify_media_scope()` returns `None`; protected paths require a valid tenant-bound signature.

Load HMAC material only from the server-side `MEDIA_SIGN_SECRET`. Production without that variable must fail closed during startup; development/test may generate a process-random secret. Never derive or fall back to `API_KEY`, tenant credentials, or any client-held value.

Set `Cache-Control: public, max-age=86400` for public roots and `Cache-Control: private, no-store` for protected responses.

- [x] **Step 5: Remove basename fallback and align the route-auth contract**

Delete `_resolve_media_path()`'s `safe_name` search across `OUTPUT_DIR`, `seedance`, `audio`, `gpt_images`, `renders`, `demo`, `uploads`, and `fast_mode`. Resolution must use the exact validated relative path only.

Keep `media.router` classified as a mixed router because the same GET route serves explicit public roots and signed protected roots. Update `configs/backend-route-auth-contract.yaml`, `tests/test_backend_route_auth_contract.py`, and `docs/runbooks/backend-route-auth-contract.md` so the public-route reason says unsigned access is limited to `brand_assets`/`demo`, while every protected path requires a tenant-bound token. `/api/media/sign` remains API-key protected through its own dependency.

- [x] **Step 6: Remove the Nginx bypass with a RED contract and minimal config change**

Create `tests/test_lighthouse_media_auth_contract.py`:

```python
def test_protected_media_is_not_served_by_direct_alias():
    text = AI_VIDEO_LOCATIONS.read_text()
    media_block = re.search(r"location /api/media/ \{(?P<body>.*?)\n\}", text, re.S)
    assert media_block
    body = media_block.group("body")
    assert "alias /var/www/media/" not in body
    assert "proxy_pass http://ai_video_backend" in body
    assert "try_files" not in body
```

Verify RED, then replace the `/api/media/` alias/`try_files` block with a backend proxy block that retains the existing timeouts and burst limit.

- [x] **Step 7: Run Task 1 GREEN and focused regression gates**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_p0_media_tenant_security.py \
  tests/test_backend_route_auth_contract.py \
  tests/test_lighthouse_media_auth_contract.py -q
.venv/bin/python -m ruff check src/routers/media.py \
  tests/test_p0_media_tenant_security.py tests/test_lighthouse_media_auth_contract.py
git diff --check
```

Expected: all commands exit `0`; protected anonymous/cross-tenant tests pass; purpose/path/tenant tampering is rejected; the Nginx contract proves no direct media alias.

- [x] **Step 8: Independent task review**

Dispatch an independent reviewer against the Task 1 brief and only the seven Task 1 files, using the working-tree diff because project rules prohibit an automatic commit. Required verdicts: spec compliance approved and code quality approved. Fix and re-review every Critical/Important finding before marking Task 1 complete. Do not commit.

---

### Task 2: Resolve Protected Media Through Signed URLs in the Frontend

**Files:**

- Create: `web/src/hooks/useSignedMediaUrl.ts`
- Create: `web/src/hooks/useSignedMediaUrl.test.ts`
- Modify: `web/src/components/api.ts`
- Modify: `web/src/components/RuntimeMediaImage.tsx`
- Create: `web/src/components/RuntimeMediaVideo.tsx`
- Create: `web/src/components/RuntimeMediaAudio.tsx`
- Create: `web/src/components/RuntimeMediaLink.tsx`
- Modify: `web/src/components/mediaUrlSanitizer.test.ts`
- Modify: `web/src/lib/runtimeMediaImageGuard.test.ts`
- Create: `web/src/lib/runtimeMediaAccessGuard.test.ts`
- Modify protected media consumers including `web/src/app/works/page.tsx`, `web/src/app/library/MaterialsTab.tsx`, `web/src/app/library/BrandKitTab.tsx`, `web/src/components/AssetCard.tsx`, `web/src/components/AssetLibrary.tsx`, `web/src/components/DirectorPlayback.tsx`, `web/src/components/CompareView.tsx`, `web/src/components/FastModePanel.tsx`, `web/src/components/OneShotResultView.tsx`, and `web/src/components/VideoWorkflow.tsx`.

**Interfaces:**

- Produces: `getSignedMediaUrl(filePath: string, purpose?: "view" | "download") -> Promise<string>`; it returns an empty string on signing rejection and never downgrades to unsigned protected access.
- Produces: `useSignedMediaUrl(filePath: string, purpose?: "view" | "download") -> {url: string; loading: boolean; error: string | null}`.
- Produces: `RuntimeMediaImage`, `RuntimeMediaVideo`, `RuntimeMediaAudio`, and `RuntimeMediaLink`, which accept canonical raw paths and resolve signed protected URLs before creating a DOM `src`/`href`.

- [x] **Step 1: Write RED tests for fail-closed signing and safe signed-URL parsing**

Add to `web/src/components/mediaUrlSanitizer.test.ts`:

```typescript
it("preserves an allowed same-origin signed media URL", () => {
  const signed = "/api/media/tenants/tenant-a/pending_review/a.png?token=abc&expires=2000000000&tenant=tenant-a&purpose=view";
  expect(api.getMediaUrl(signed)).toBe(signed);
});

it("rejects signed media URLs with unknown or duplicate query parameters", () => {
  expect(api.getMediaUrl("/api/media/a.png?token=abc&expires=2000000000&tenant=default&purpose=view&redirect=https://evil.example")).toBe("");
  expect(api.getMediaUrl("/api/media/a.png?token=abc&token=def&expires=2000000000&tenant=default&purpose=view")).toBe("");
});

it("does not fall back to an unsigned protected URL when signing fails", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 403 }));
  expect(await api.getSignedMediaUrl("tenants/tenant-a/a.png")).toBe("");
});
```

Run `cd web && npm test -- --run src/components/mediaUrlSanitizer.test.ts` and confirm current fallback/URL parsing behavior fails the new assertions.

- [x] **Step 2: Write RED hook tests for loading, success, expiry refresh and error**

Create `useSignedMediaUrl.test.ts` with fake timers and a mocked `getSignedMediaUrl`:

```typescript
it("keeps protected media absent until a signed URL is returned", async () => {
  signer.mockResolvedValue("/api/media/tenants/tenant-a/a.png?token=t&expires=2000000000&tenant=tenant-a&purpose=view");
  const { result } = renderHook(() => useSignedMediaUrl("tenants/tenant-a/a.png"));
  expect(result.current.url).toBe("");
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.url).toContain("token=t");
});

it("stays fail-closed when the signer rejects", async () => {
  signer.mockResolvedValue("");
  const { result } = renderHook(() => useSignedMediaUrl("tenants/tenant-a/a.png"));
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.url).toBe("");
  expect(result.current.error).toBeTruthy();
});
```

Add a fake-timer case whose first URL expires in 31 seconds; advance 2 seconds and assert the hook requests a refreshed token 30 seconds before expiry.

- [x] **Step 3: Implement strict URL handling and the hook**

`getMediaUrl()` may preserve an already signed URL only when it is same-origin `/api/media/*`, has no fragment, has exactly one each of `token`, `expires`, `tenant`, and `purpose`, and `purpose` is `view` or `download`. Static `/portfolio/*` demo assets remain unchanged.

`getSignedMediaUrl()` calls `/api/media/sign` with the canonical path and purpose, uses the existing API-key header, and returns `""` for non-OK, invalid JSON, unknown URL shape or exception.

`useSignedMediaUrl()`:

```typescript
export type SignedMediaState = {
  url: string;
  loading: boolean;
  error: string | null;
};

export function useSignedMediaUrl(
  filePath: string,
  purpose: "view" | "download" = "view",
): SignedMediaState;
```

It bypasses signing only for static demo/public URLs recognized by `getMediaUrl()`, cancels stale async results on prop changes/unmount, and refreshes a signed URL 30 seconds before `expires` without ever rendering an expired or unsigned protected URL.

- [x] **Step 4: Centralize DOM media consumers**

Modify `RuntimeMediaImage` to call `useSignedMediaUrl(src, "view")` and render no `<img>` until `url` is non-empty. Implement equivalent small wrappers for video, audio and links. `RuntimeMediaLink` uses purpose `download` for download actions.

Replace direct protected `<video>`, `<audio>`, and download `<a>` consumers in the files listed above. `FastModePanel` must route only internal runtime media through signed wrappers while preserving allowlisted external provider previews. Do not change static icons, local `/portfolio/*` demo assets, or external provider preview URLs that pass the existing allowlist.

- [x] **Step 5: Add a static guard against future unsigned DOM use**

Create `runtimeMediaAccessGuard.test.ts` that scans `web/src` and fails when a TSX file outside the four wrappers uses `src={getMediaUrl(`, `href={getMediaUrl(`, or directly places an `/api/media/` expression into a media DOM attribute. Keep the existing raw `<img>` centralization test.

- [x] **Step 6: Run GREEN and frontend regression gates**

Run:

```bash
cd web && npm test -- --run \
  src/components/mediaUrlSanitizer.test.ts \
  src/hooks/useSignedMediaUrl.test.ts \
  src/lib/runtimeMediaImageGuard.test.ts \
  src/lib/runtimeMediaAccessGuard.test.ts
cd web && npm run lint
cd web && npx tsc --noEmit -p tsconfig.json
git diff --check
```

- [x] **Step 7: Independent task review**

Require approved spec and quality verdicts. Reviewer checks token refresh races, unmount cancellation, demo/public compatibility, audio/video/download coverage and any remaining unsigned DOM path. Do not commit.

---

### Task 3: Normalize a Strict Generation-Safety Intent Across Fast and S1–S5

**Files:**

- Create: `src/pipeline/generation_policy.py`
- Modify: `src/routers/_deps.py`
- Modify: `src/routers/scenario.py`
- Modify: `src/routers/pipeline.py`
- Modify: `src/routers/_state.py`
- Modify: `src/storage/migrations/001_init.sql`
- Create: `migrations/alembic/versions/7c4b8e2f1a09_fail_closed_api_key_permissions.py`
- Modify: `tests/test_auth_context.py`
- Create: `tests/test_scenario_generation_safety_policy.py`
- Modify: `tests/test_s1_e2e.py`
- Modify: `tests/test_s2_e2e.py`
- Modify: `tests/test_s3_e2e.py`
- Modify: `tests/test_s4_e2e.py`
- Modify: `tests/test_s5_e2e.py`
- Modify: `web/src/lib/scenarioPayload.ts`
- Modify: `web/src/lib/scenarioPayload.test.ts`
- Modify: `web/src/lib/scenarioContinuity.ts`
- Modify: `web/src/lib/scenarioContinuity.test.ts`
- Modify: `web/src/components/SceneForm.tsx`
- Modify: `web/src/components/GuidedForm.tsx`
- Modify: `web/src/components/FastModePanel.tsx`
- Modify: `web/src/components/api.ts`

**Interfaces:**

- Produces: strict `GenerationSafetyIntent` with fail-closed defaults: media disabled, `pending_review`, mutation retry `0`.
- Produces: `EffectiveGenerationPolicy`, whose tenant comes only from `AuthContext` and whose provider permission is derived server-side.
- Produces: `resolve_generation_policy(body, *, auth, scenario) -> EffectiveGenerationPolicy`.
- Preserves: `commercial_injection_plan` through its existing dedicated validator rather than a raw safety-field copier.
- Defers explicitly: durable idempotency, budget reservation/ledger, artifact transition records and transparency sidecars. This task must not claim those controls exist.

- [x] **Step 1: Write RED tests for strict intent validation and authority**

Create `tests/test_scenario_generation_safety_policy.py`. Assert:

- omitted safety fields resolve to `False`, `pending_review`, and `0` without implying that the request itself is authorized;
- only strict booleans are accepted (`"false"` and integer `0` are rejected as booleans);
- generation submit accepts only `pending_review` or `quarantine`, never `default`, `approved`, or `public`;
- mutation retry accepts only `0` until durable provider-recognized idempotency exists;
- a request-body `tenant_id` is rejected and cannot override `AuthContext.tenant_id`;
- unimplemented/deferred authority assertions such as `idempotency_key`, client budget/spend, transparency policy, human approval, publish/delivery flags, or a client-supplied effective policy return `422` instead of being silently ignored;
- every AI-provider-backed generation request requires `provider:submit` or `all`, including no-media runs whose strategy/script steps still call an LLM; missing permission fails before any provider-capable config is produced;
- tenant DB keys with null, empty, malformed, or unrecognized permission payloads normalize to deny, while env/test-bundle `all` remains an explicit key-type decision.

- [x] **Step 2: Write a parameterized RED test for every backend submit surface**

Parameterize Fast, S1–S5 blocking, unified async submission, and legacy `/pipeline/start` through real HTTP request validation. With an `AuthContext(tenant-a, {all})`, submit the explicit safe media intent:

```python
{
    "enable_media_synthesis": True,
    "artifact_disposition": "pending_review",
    "provider_max_retries": 0,
}
```

Assert every surface builds the same effective policy/config and preserves exact `True`/`0` values. Send raw HTTP payloads containing `"false"`, boolean `False` in the integer retry field, `tenant_id`, unknown policy versions, and forbidden dispositions; each must fail before Pydantic coercion or extra-field dropping can hide the invalid input. The current Fast schema omission, unified S2 hardcoded `True`, S3–S5 omissions, S5 raw-JSON reparse, and direct-endpoint `default`/`None` defaults must produce meaningful RED failures. Mock runners/services; provider methods must not execute in this task.

- [x] **Step 3: Run RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_scenario_generation_safety_policy.py -q
```

Expected: current permissive defaults, Fast omission, unified field drift, tenant-body tolerance, and retry bounds fail.

- [x] **Step 4: Implement the canonical strict resolver**

Create a small Pydantic-backed policy module. The shape is illustrative; match repository style and keep the contract strict:

```python
class GenerationSafetyIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enable_media_synthesis: StrictBool = False
    artifact_disposition: Literal["pending_review", "quarantine"] = "pending_review"
    provider_max_retries: Annotated[int, Field(strict=True, ge=0, le=0)] = 0
```

`resolve_generation_policy()` must extract only the three intent fields from the larger scenario payload, reject body `tenant_id`, reject a documented `DEFERRED_GENERATION_CONTROL_KEYS` set with `422`, require `provider:submit` for any provider-backed generation request, and return a versioned effective projection containing the authenticated tenant and scenario. Endpoint models must use strict fields or a `mode="before"` validator so invalid raw HTTP cannot be coerced before the resolver sees it. It must never silently accept client idempotency, budget/spend, approval, artifact-publication, effective-policy, or transparency assertions.

Make tenant permission normalization fail closed for DB-backed keys: null, empty, malformed, wrong-type, and unknown-only payloads produce an empty permission set. Env fallback and test-bundle contexts may retain explicit `all`. Change fresh-init and Alembic server defaults to an empty permission array; do not execute the migration against any live database. Admin-created `all` remains an explicit application choice until a later permission-management UI exists.

- [x] **Step 5: Route all backend config builders through the resolver**

Use one resolver result in Fast, S1–S5 blocking endpoints, `/scenario/{scenario}/submit`, and legacy `/pipeline/start`. Remove S2 hardcoding and S5 raw-JSON reinterpretation. Scenario-specific `media_stop_step` remains separately validated and is not a generic safety key. The effective policy is stored in a reserved server-owned field; clients cannot supply it. In `pipeline.py`, Task 3 is limited to strict request/resolver/config integration; execution guards and truthful bounded lifecycle remain Task 4. Do not yet change execution order or call a provider; Task 4 enforces the runtime boundary.

- [x] **Step 6: Make browser submission explicit and fail-closed**

Frontend builders preserve explicit `false`, `0`, and `pending_review`. Missing safety intent defaults to no-media, not provider-on. The actual user click paths in `SceneForm`, `GuidedForm`, and Fast Mode must deliberately set `enable_media_synthesis=true`, `artifact_disposition=pending_review`, and `provider_max_retries=0`; recommendation/render effects must not synthesize that intent implicitly.

Add parameterized tests for Fast and S1–S5 final API payloads, including exact `false` and `0` assertions. Replace the existing continuity test that calls provider-on a “safe default.”

Before GREEN, run an `rg` impact scan for `provider_max_retries`, manually constructed request models, and raw state fixtures. Update every affected test explicitly; never rely on Pydantic coercion or leave an unlisted fixture with implicit media-on policy. The listed S1–S5 E2E files are the known starting set, not permission to relax their assertions.

- [x] **Step 7: Run GREEN and regression gates**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_auth_context.py \
  tests/test_scenario_generation_safety_policy.py \
  tests/test_scenario_commercial_injection_router.py \
  tests/test_s1_e2e.py tests/test_s2_e2e.py tests/test_s3_e2e.py \
  tests/test_s4_e2e.py tests/test_s5_e2e.py -q
.venv/bin/python -m ruff check src/pipeline/generation_policy.py src/routers/_deps.py src/routers/scenario.py \
  tests/test_scenario_generation_safety_policy.py
cd web && npm test -- --run \
  src/lib/scenarioPayload.test.ts \
  src/lib/scenarioContinuity.test.ts
cd web && npm run lint
cd web && npx tsc --noEmit -p tsconfig.json
git diff --check
```

- [x] **Step 8: Independent task review**

Review only Task 3's diff against this brief. Reviewers must confirm raw-HTTP strictness, fail-closed DB permission parsing, explicit env/test-bundle authority, exact `false`/`0` preservation, Fast and S1–S5 parity, and the explicit deferred-control wording. Do not commit.

---

### Task 4: Make Effective Policy Immutable and Enforce Real Scenario Execution Boundaries

**Files:**

- Modify: `src/pipeline/generation_policy.py`
- Modify: `src/pipeline/step_runner.py`
- Modify: `src/pipeline/gate_manager.py`
- Modify: `src/routers/scenario.py`
- Modify: `src/routers/pipeline.py`
- Modify: `src/tools/retry.py`
- Modify: `src/tools/llm_client.py`
- Modify: `src/skills/base.py`
- Modify: `tests/test_scenario_generation_safety_policy.py`
- Modify: `tests/test_scenario_step_regenerate_router.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_quality_score_feedback.py`
- Modify: `tests/test_s1_e2e.py`
- Modify: `tests/test_s2_e2e.py`
- Modify: `tests/test_s3_e2e.py`
- Modify: `tests/test_s4_e2e.py`
- Modify: `tests/test_s5_e2e.py`
- Create: `tests/test_generation_policy_step_guard.py`
- Create: `tests/test_provider_retry_policy.py`

**Interfaces:**

- Produces: versioned exact execution profiles, not index-only stop comparisons.
- Produces: `assert_generation_step_allowed(state, step_name, *, force=False)` for direct step/regenerate paths; `force` never bypasses safety.
- Produces: request-scoped provider retry cap consumed by the LLM retry helper as well as media clients.
- Produces: bounded completion metadata without claiming full-media success or delivery acceptance.
- Preserves: legacy `/pipeline/start` through the same strict policy-aware runner; it must not hardcode media-on or silently replay.

- [x] **Step 1: Write RED tests against the real StepRunner call boundary**

Use a real `StepRunner` with an in-memory state manager. Replace the scenario pipeline constructor/step method with a sentinel and assert a forbidden step fails before pipeline import/class construction. Parameterize S1–S5 no-media profiles:

- S1–S3 stop before `keyframe_images`;
- S4–S5 stop before `video_prompts`;
- provider-capable step functions are not invoked;
- the persisted state is marked bounded/no-media, `current_step=None`, and never claims publish/delivery acceptance.

Missing, corrupt, client-supplied, or unknown-version effective policy fails closed. Legacy persisted states without a policy default to no-media/blocked behavior; update fixtures explicitly rather than silently treating them as media-on.

- [x] **Step 2: Write RED tests for exact bounded profiles**

For S1/S3/S4/S5, use explicit ordered allowlists matching their current bounded helper sequences and terminate after `seedance_clips`. Do not infer permission from canonical index alone because current bounded sequences intentionally omit some steps. A provider-backed step that is already completed in a bounded state cannot be rerun with `force=True`; until a durable atomic attempt ledger exists, media force-regenerate is rejected even when that step belongs to the profile.

For S2, encode the existing segmented profiles as exact allowlists. A profile never grants every canonical step before its terminal point. Provider-backed profiles later than the approved plan must be rejected with `422` before partial execution; refs-only `assemble_final`/`audit` stay separately validated. Assert effective retry `0`, exact provider job caps, bounded metadata, and no step outside the profile.

- [x] **Step 3: Write RED tests for every bypass before mutation**

Assert all of the following fail before side effects:

- `run_step()` and `regenerate_step()` beyond the profile fail before pipeline construction;
- `regenerate_step(force=True)` for an already-completed provider-backed step inside the bounded profile fails before `invalidate_downstream`, pipeline construction and any provider attempt; repeated calls keep total attempts unchanged;
- regenerate routes preflight before `invalidate_downstream`;
- S1 state update rejects overwrite/delete/version-tamper of tenant, effective policy, config safety fields, scenario, lifecycle and execution cursor;
- gate generate/regenerate checks policy outside its retry `try` and before `SkillRegistry.execute`;
- bounded policies forbid media Gate candidate generate/regenerate entirely until a durable attempt ledger/cap exists;
- allowed text Gate candidates may execute the planned candidate count, but each candidate gets at most one attempt and a failure never triggers an extra replacement/fourth provider call;
- gate approval validates the next cursor before saving it;
- `/pipeline/start` consumes the canonical resolver and defaults no-media rather than hardcoding `True`;
- the S1 broad `TypeError` fallback is removed; a TypeError after a fake successful provider attempt still yields total submit count `1`.

- [x] **Step 4: Write RED provider-attempt tests**

Bind policy retry `0`, call `LLMClient` through a fake transport that fails once, and assert exactly one HTTP/provider attempt. Then execute a real LLM-backed `SkillCallable` through `SkillRegistry -> safe_execute -> LLMClient` and assert the outer skill loop does not create another provider attempt. Cover a media client separately. Gate's old three-candidate/retry loop must have zero calls when policy blocks media, and a failed allowed text candidate must not trigger a fourth replacement attempt. These are real client/registry boundaries, not mocks of the entire router or runner.

- [x] **Step 5: Implement immutable profiles and central guards**

Teach `StepRunner.resume()` to stop before/after the versioned effective policy boundary and persist bounded metadata. `run_step()` and `regenerate_step()` call the same assertion so manual routes cannot bypass it. Existing direct-pipeline helper loops may remain, but they must produce the same boundary and cannot widen it.

The hard assertion belongs at the start of `_execute_step()`, before pipeline import/class construction. The force path also checks persisted completion/attempt state; in bounded mode it never turns an allowed first attempt into an unlimited regenerate channel. Effective policy lives in a reserved server-owned state field; public state edit rejects it and all derived cursors/authority fields.

- [x] **Step 6: Close Gate, regenerate, legacy and duplicate-submit bypasses**

Guard GateManager before `SkillRegistry.execute` and before any retry loop. Guard regenerate before invalidation and gate approval before cursor save. Route the legacy `/pipeline/start` contract through strict canonical policy handling without a breaking `410`. Delete the blocking S1 broad-TypeError full-chain fallback; propagate the classified error without replay. Remove duplicate router-local boundary constants after the profile SSOT is in use.

- [x] **Step 7: Apply the provider retry context and truthful bounded projection**

Apply request-scoped mutation retry `0` to `retry_with_backoff()`/`LLMClient`, `SkillCallable.safe_execute()` and existing media clients. Read-only poll retries remain separate. Every blocking and unified status surface must report `completed_bounded` for no-media/bounded runs, `request_succeeded=true`, legacy `success=false`, `full_media_success=false`, `publish_allowed=false`, and `delivery_accepted=false`; `current_step=None` alone must not become generic `completed`. `success=true` is reserved for a verified complete-media result so older clients cannot mistake a bounded run for final output.

Run an impact scan for all manually constructed states. Fixtures that intentionally exercise execution must declare a valid effective policy; missing/corrupt/unknown policy fixtures must assert fail-closed. Do not bulk-add media-on policy merely to preserve old tests.

- [x] **Step 8: Run GREEN and regression gates**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_scenario_generation_safety_policy.py \
  tests/test_generation_policy_step_guard.py \
  tests/test_provider_retry_policy.py \
  tests/test_scenario_step_regenerate_router.py \
  tests/test_quality_score_feedback.py tests/test_api.py \
  tests/test_s1_e2e.py tests/test_s2_e2e.py tests/test_s3_e2e.py \
  tests/test_s4_e2e.py tests/test_s5_e2e.py -q
.venv/bin/python -m ruff check \
  src/pipeline/generation_policy.py src/pipeline/step_runner.py \
  src/pipeline/gate_manager.py src/routers/scenario.py src/routers/pipeline.py \
  src/tools/retry.py src/tools/llm_client.py src/skills/base.py \
  tests/test_generation_policy_step_guard.py tests/test_provider_retry_policy.py
git diff --check
```

- [x] **Step 9: Independent task review**

Require spec and quality approval. Reviewers must inspect real call boundaries, S2 exact profiles, Gate/force/regenerate/state-edit ordering, missing-policy behavior, LLM/media attempt counts, S1 replay removal and bounded response semantics. Config-only assertions are insufficient. Do not commit.

---

### Task 5: Enforce Fast-Mode Tenant Ownership, Bounded Results and Media-Provider Isolation

**Files:**

- Modify: `src/services/fast_mode.py`
- Modify: `src/tasks/fast_task_registry.py`
- Modify: `src/routers/scenario.py`
- Modify: `src/models/runtime_contracts.py`
- Modify: `tests/test_fast_mode_token_smoke_contract.py`
- Modify: `tests/test_fast_mode_async.py`

**Interfaces:**

- Produces: policy-aware Fast results that distinguish `completed_bounded` from full video success.
- Produces: tenant-owned Fast task records and tenant-filtered status lookup.
- Produces: tenant/disposition-scoped video, audio and fallback-audio paths.

- [x] **Step 1: Write RED no-media and attempt-count tests**

Call the real `FastModeService.generate()` with fake LLM, Seedance and CosyVoice transports. With no-media, Seedance and TTS attempts are exactly `0`; text planning may run only with provider permission and uses the retry-0 context. The response has no media URL/path, is `completed_bounded`, sets `request_succeeded=true`, legacy `success=false`, `full_media_success=false`, and does not claim publish or delivery.

- [x] **Step 2: Write RED tenant-output tests**

With enabled pending-review media, assert video, TTS audio and fallback audio all resolve below the authenticated tenant/disposition/run directory. No global `output/fast_mode/audio` path may be returned. Tenant comes only from the effective policy, never request body.

- [x] **Step 3: Write RED registry ownership tests**

Submit a fake async Fast task as tenant A. Tenant A can poll; tenant B receives `404`; unknown and expired task behavior remains unchanged. Persist tenant, effective policy version and bounded/full result status with the task. Test the real registry functions rather than mocking the whole service.

- [x] **Step 4: Implement the policy-aware Fast branch**

Pass effective policy into Fast service. No-media returns after text planning and before Seedance/TTS. Enabled media creates every artifact under tenant scope and carries retry `0`. Define the bounded result/status contract in `runtime_contracts.py` and keep frontend-compatible error fields without claiming a video exists.

- [x] **Step 5: Make task lookup tenant-bound**

`register_fast_task()` stores tenant and policy metadata; `get_fast_task()` requires the authenticated tenant. Router status uses `AuthContext` and returns indistinguishable `404` for unknown/cross-tenant IDs. Cleanup/TTL behavior remains covered.

- [x] **Step 6: Run GREEN and regression gates**

```bash
.venv/bin/python -m pytest \
  tests/test_fast_mode_token_smoke_contract.py \
  tests/test_fast_mode_async.py \
  tests/test_scenario_generation_safety_policy.py -q
.venv/bin/python -m ruff check \
  src/services/fast_mode.py src/tasks/fast_task_registry.py \
  src/routers/scenario.py src/models/runtime_contracts.py \
  tests/test_fast_mode_token_smoke_contract.py tests/test_fast_mode_async.py
git diff --check
```

- [x] **Step 7: Independent task review**

Require spec and quality approval. Reviewers inspect real media-provider counts, LLM retry context, tenant-scoped audio/video paths, cross-tenant status and truthful bounded results. Do not commit.

---

### Task 6: Make Browser Mutations Zero-Retry and Remove Implicit S1 Provider Work

**Files:**

- Modify: `web/src/components/api.ts`
- Modify: `web/src/components/RecommendPanel.tsx`
- Modify: `web/src/app/page.tsx`
- Modify: `web/src/components/apiFetchErrorNormalization.test.ts`
- Modify: `web/src/components/RecommendPanel.test.tsx`
- Modify: `web/src/app/__tests__/page-smoke.test.ts`

**Interfaces:**

- Produces: `isRetryableHttpMethod(method: string) -> boolean` for GET/HEAD/OPTIONS only.
- Removes: automatic legacy S1 fallback after an ambiguous unified-submit exception.
- Preserves: `RecommendPanel.onStart(config)` as the only generation action from the recommendation view.

- [x] **Step 1: Write RED tests for mutation attempts**

In `apiFetchErrorNormalization.test.ts`, parameterize POST/PUT/PATCH/DELETE. Mock a 500 response and assert native fetch is called once. Add a GET case asserting the current single retry remains available.

- [x] **Step 2: Write RED tests for S1 recommendation**

Update `RecommendPanel.test.tsx` so an S1 render waits for the recommendation, then asserts `startS1StepByStep` and `runS1Step` are never called. Clicking Start must call `onStart` exactly once.

- [x] **Step 3: Write RED test for no blind S1 fallback**

In `page-smoke.test.ts`, make unified S1 submit reject after an ambiguous network error. Assert `runS1ProductDirect` is not called and the UI exposes the existing retryable submit error.

- [x] **Step 4: Run RED**

Run:

```bash
cd web && npm test -- --run \
  src/components/apiFetchErrorNormalization.test.ts \
  src/components/RecommendPanel.test.tsx \
  src/app/__tests__/page-smoke.test.ts
```

Expected: mutation retries, S1 recommendation provider calls, and legacy fallback assertions fail on current code.

- [x] **Step 5: Implement method-aware retries**

Add:

```typescript
export function isRetryableHttpMethod(method: string): boolean {
  return ["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
}
```

Set `maxRetries` to zero unless the URL is non-health and the method is retryable. An AbortError from a caller signal must return immediately without retry.

- [x] **Step 6: Make RecommendationPanel local and side-effect free**

Use the existing `buildLocalRecommendation(config)` for S1 as well as unsupported step-by-step scenarios. Remove `startS1StepByStep` and `runS1Step` from the recommendation effect. Keep generation solely in `handleStart()`.

- [x] **Step 7: Remove blind legacy fallback**

In `page.tsx`, on unified-submit exception report the structured error and stop the progress view. Do not call the blocking S1 endpoint. A later idempotency task will support safe ambiguous-response recovery.

- [x] **Step 8: Run GREEN and frontend gates**

Run:

```bash
cd web && npm test -- --run \
  src/components/apiFetchErrorNormalization.test.ts \
  src/components/RecommendPanel.test.tsx \
  src/app/__tests__/page-smoke.test.ts
cd web && npm run lint
cd web && npx tsc --noEmit -p tsconfig.json
git diff --check
```

- [x] **Step 9: Independent task review**

Require approved spec and quality verdicts. Pay particular attention to abort handling, demo mode, duplicated onStart calls and existing submit-lock behavior. Do not commit.

---

### Task 7: Make Production Token Smoke Single-Spec and Machine-Authorized

**Files:**

- Modify: `.github/workflows/e2e-prod.yml`
- Modify: `web/playwright.prod.config.ts`
- Modify: `scripts/l4c_token_smoke_plan.py`
- Modify: `tests/test_l4c_token_smoke_plan.py`
- Modify: `tests/test_token_smoke_preflight.py`
- Modify: `tests/test_fast_mode_token_smoke_contract.py`
- Modify: `docs/runbooks/production-e2e-token-smoke.md`

**Interfaces:**

- Produces workflow inputs: `token_smoke_spec`, `approval_record_path`, and `plan_path`; an empty spec means read-only suite only.
- Produces validated environment: `PLAYWRIGHT_TOKEN_SMOKE_SPEC`, `PLAYWRIGHT_MAX_SUBMIT_COUNT`, `PLAYWRIGHT_PROVIDER_MAX_RETRIES=0`, `PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review`.
- Consumes the existing L4C plan validator before Playwright starts.

- [x] **Step 1: Write static RED tests for workflow boundaries**

Assert the workflow:

```python
assert "environment: production-provider" in workflow_text
assert "l4c_token_smoke_plan.py" in workflow_text
assert "--workers=1" in workflow_text
assert "--retries=0" in workflow_text
assert "npx playwright test -c playwright.prod.config.ts --reporter" not in token_step
```

Parse YAML and assert token execution uses the validated single spec value rather than the full suite.

- [x] **Step 2: Add validator RED cases**

Cover missing approval, spec not in allowlist, submit cap above the plan, retry above zero, non-pending-review disposition and budget mismatch. Each case must exit non-zero before any Playwright command is emitted.

- [x] **Step 3: Run RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_l4c_token_smoke_plan.py \
  tests/test_token_smoke_preflight.py \
  tests/test_fast_mode_token_smoke_contract.py -q
```

Expected: current workflow lacks the environment/validator/single-spec command and fails the new assertions.

- [x] **Step 4: Implement the fail-closed workflow**

Split production E2E into two steps:

1. non-token suite with `RUN_TOKEN_SMOKE=0` and the current read-only grep inversion;
2. token step guarded by a non-empty validated spec, protected environment, plan/approval validation and exact command:

```bash
RUN_TOKEN_SMOKE=1 \
PLAYWRIGHT_PROD_WORKERS=1 \
PLAYWRIGHT_MAX_SUBMIT_COUNT="$MAX_SUBMITS" \
PLAYWRIGHT_PROVIDER_MAX_RETRIES=0 \
PLAYWRIGHT_ARTIFACT_DISPOSITION=pending_review \
npx playwright test -c playwright.prod.config.ts "$TOKEN_SMOKE_SPEC" \
  --workers=1 --retries=0 --reporter=list,html
```

Never interpolate an unvalidated shell path. The validator must return a repository-relative spec from a fixed allowlist and reject separators/options outside the expected pattern.

- [x] **Step 5: Make Playwright config consistent**

When `RUN_TOKEN_SMOKE` is true, require `PLAYWRIGHT_TOKEN_SMOKE_SPEC`; keep `workers=1` and set `retries=0`. Read-only mode may retain its current retry policy. The config must not globally unhide every token spec.

- [x] **Step 6: Update the canonical runbook**

Document the exact approval record, plan, budget, cap, single spec, pending-review disposition, stop conditions and artifact evidence. State that repository configuration does not prove GitHub Environment reviewers are configured; owner verification remains external.

- [x] **Step 7: Run GREEN and safe list-only acceptance**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_l4c_token_smoke_plan.py \
  tests/test_token_smoke_preflight.py \
  tests/test_fast_mode_token_smoke_contract.py -q
cd web && RUN_TOKEN_SMOKE=0 npx playwright test -c playwright.prod.config.ts --list
cd web && RUN_TOKEN_SMOKE=1 \
  PLAYWRIGHT_TOKEN_SMOKE_SPEC=e2e/production/fast-mode-single-submit.prod.spec.ts \
  npx playwright test -c playwright.prod.config.ts \
  e2e/production/fast-mode-single-submit.prod.spec.ts --list --workers=1 --retries=0
git diff --check
```

Expected: tests pass and both Playwright commands only list tests; no browser launch, HTTP submit or provider call occurs.

- [x] **Step 8: Independent task review**

Require approved spec and quality verdicts. Reviewer checks command injection, approval bypass, retry/worker drift, full-suite reachability and artifact retention. Do not commit.

---

## Wave 1A Final Acceptance

- [x] Run all Task 1–7 focused suites again from the final working tree.
- [x] Run `.venv/bin/python -m ruff check src tests`.
- [x] Run `.venv/bin/python -m pytest tests/ -q --tb=short` with provider keys unset and token smoke disabled.
- [x] Run `cd web && npm test -- --run`.
- [x] Run `cd web && npm run lint`.
- [x] Run `cd web && npx tsc --noEmit -p tsconfig.json`.
- [x] Run `cd web && NEXT_PUBLIC_IS_DEMO=true npm run build`.
- [x] Run affected Docker/Nginx/config static contracts; do not deploy.
- [x] Generate a whole-wave diff package and dispatch a broad final reviewer.
- [x] Resolve every Critical/Important finding and re-run the covering tests.
- [x] Update `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md` with fresh command evidence.
- [x] Record maximum evidence as L2 local/fixture/build and explicitly retain `production unchanged`, `provider_call=false`, `no publish/delivery`.
