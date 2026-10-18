# Red-team fixes and end-to-end verification

Verified locally on 2026-10-18. All five findings from the original audit are fixed; the additional browser-header gap is fixed too. The original report is retained as historical evidence, not a statement of current behavior.

| Finding | Fix | Regression evidence |
|---|---|---|
| RT-01: unauthenticated writes | Saving requires an authenticated local operator session, a 15-minute preview bound to that session and exact assignments, an unchanged company fingerprint (except an exact journaled retry), and explicit successor-consent attestation. Invalid hosts and cross-site state changes are rejected. | Anonymous 401; invalid host 400; foreign Origin 403; altered/expired/other-session preview 409; missing consent 422; expired/revoked session 401. Valid save, retry and read-back pass. |
| RT-02: borrowed evidence | Every citation must concern both the person and duty. Structured metadata must match both. Messages/tickets need person attribution and specific duty-topic terms. Unknown duties must ground both identifier and name; duplicate belief IDs cannot borrow another belief's relevance. | Original fabricated-duty attack and copied-topic/duplicate-ID variants rejected; original 88 checks still pass. |
| RT-03: oversized assignments | Bounded identifier types, known company membership checks, and a 64 KiB streaming body limit apply before CLI dispatch. | 150 KB identifier and oversized chunked body return 413; overlong and unknown identifiers return 422. |
| RT-04: uncached seed disk growth | HTTP/MCP demo provisioning accepts only the four supplied companies, regardless of model mode. Unsupported seeds fail before any file allocation or model invocation. | Six rejected seeds leave zero files/bytes; every company route rejects unprovisioned seeds. |
| RT-05: repository links | Ownership files and receipt journals use directory handles, no-follow opens, regular-file checks, and atomic replacement. Unsafe destinations fail before graph writes. | Leaf, dangling, parent-directory and journal-directory symlinks plus hardlinks are rejected; swapping a leaf before replacement cannot change the outside sentinel. |
| RT-06: browser headers | CSP, nosniff, frame denial, same-origin referrer policy and no-store API responses. Swagger's trusted initializer gets a script hash; no arbitrary inline scripts are allowed. | Headers checked on pages/API/error responses; actual UI, graph and Swagger run with zero CSP violations. |

Relevant implementation: `server/security.py`, `server/app.py`, `baton/evidence.py`, `baton/rehearse.py`, `baton/commit.py`. Regression tests: `tests/integration/test_security.py` and `tests/redteam/test_attacks.py`.

## Operator access

Read-only demo flows stay available. Saving ownership requires **Operator sign in**. Docker generates a random operator credential in its private data volume. Retrieve it locally:

```powershell
docker compose exec api cat /data/.operator-token
```

Paste it into the password field; the browser exchanges it for an opaque, HttpOnly, SameSite=Strict session lasting eight hours. It is not stored in localStorage or JavaScript files. HTTPS deployments set Secure cookies. Operators can sign out to revoke the session. Login guesses are rate-limited. Alternatively provision a secret `BATON_OPERATOR_TOKEN` of at least 32 characters; rotating it invalidates old sessions.

After choosing successors, preview the plan, confirm that they agreed, and save. The confirmation records **operator attestation**; this local demo does not independently authenticate each successor. Preview eligibility is no longer described in the interface as actual human acceptance. This is a single local operator role, not an enterprise identity or organizational-permissions system.

Safe repository writes require the Linux directory-handle primitives available in the supplied Docker deployment. Native Windows CLI writes fail closed with instructions to use Docker. Local CLI access remains a trusted filesystem-level interface; HTTP credentials are enforced at the HTTP boundary. Source-topic relevance is a conservative lexical gate, not a proof that arbitrary prose is true or a substitute for review.

## Results

`python scripts/check_all.py` in the checks container passes **170 tests**: 88 unchanged original checks, 22 foundation, 37 integration/security, and 23 red-team regressions. Current red-team observations contain 22 blocked attacks and one protected-header result, with no reproduced vulnerable outcome. Original integrity hashes remain valid.

Playwright/Edge ran against a disposable full stack at loopback port 8001 with its own FalkorDB and temporary data. The browser exercised invalid and valid login, anonymous write rejection, capacity suggestions, preview, required consent, six-duty save, graph/repository verification, receipt history after reload, graph exploration, logout revocation, a 390-pixel mobile viewport, all 25 Acme benchmark questions, and Swagger. Result: zero page errors, zero CSP violations, mobile width 390/390. The test credential was supplied through a local file without embedding its value in source or logs; its temporary copy is removed afterward.

The browser DOM injection test was rerun against the updated main service: script-bearing names and evidence still render literally, with no injected markup or execution. The normal Acme browser replay also passes. Main service data was checked after deployment: seed 7 retains 37 uncovered G-lane events; seed 303 retains zero and its original receipt `0bfa57451b7a03881ef04a9d`.

Evidence: `artifacts/check-run.json`, the four suite XML outputs, `artifacts/security-browser-results.txt`, `artifacts/redteam-observations.json`, `artifacts/redteam-browser-results.txt`, and screenshots `output/playwright/security-verified-write.png` / `security-mobile.png`. Test infrastructure is in `scripts/security_e2e_server.py` and `scripts/verify_security_browser.js`.

This verification covers the local fixture application and the reported findings. No external deployment or paid-model run was tested. Design references: [FastAPI security](https://fastapi.tiangolo.com/tutorial/security/) and [Python descriptor-based filesystem operations](https://docs.python.org/3/library/os.html#os.open).
