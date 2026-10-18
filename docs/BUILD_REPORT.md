# Local build verification — 2026-10-18

This report supersedes the earlier phase-one-only status. Historical ZIP reports remain separate.

## Delivered

Integrated the supplied graph backend with a new responsive website and MCP SDK v2 stdio adapter. Added typed HTTP input, visible error/cache states, static serving, graph import/copy coordination, unique forks and retryable graph-committed/repository-pending receipts. Docker pins the required engine and preserves state. Source attribution and the original tests are retained.

## Tests

**124 passed:** 88 original ZIP checks (integrity OK, zero skips), 22 foundation checks and 14 integration checks. The final original score was 88/88 in 64.8 seconds; foundation checks took 1.56 seconds and transport tests 17.61 seconds.

Transport tests cover four cached companies, HTTP validation, unknown questions, source/query parity, real local git commits/read-back, graph-down errors, MCP stdio initialize/list/call, generator execution without MCP installed, an injected external-write outage/retry and four concurrent first-load rehearsals. No original assertion or loop tool was changed. Two phase-one-only cases asserting future commands were absent were removed after those commands were authorized.

The installable wheel was also rebuilt and installed into a separate environment. From outside the checkout it successfully ran the offline demo (37 G events, zero after preview), located all four extraction caches and served the packaged website assets. The benchmark MIT license is included in the wheel.

The final local handoff includes a Git bundle, preserving the history needed by the supplied predictions-before-results test, as well as a source ZIP, wheel, test reports and recorded demo. Recreate it with `python scripts/package_build.py` from a clean committed checkout.

Reproduce with `docker compose --profile checks run --build --rm checks`. Machine-readable results are in `loop/last_score.json`, `loop/junit.xml`, `artifacts/foundation-tests.xml`, `artifacts/transport-tests.xml` and `artifacts/check-run.json`.

## Fresh evaluation

The fresh protocol was committed before output. Seeds 3000–3029 × sizes 1/4/8 × W/R/G/A produced **360 lane records** in 264.4 seconds. W/R/G ran; A's 90 records say not run because no real-model cache matches those inputs.

| Lane | Mean recall against G truth | Exact for its own lane semantics |
|---|---:|---:|
| W: direct owner fields | 12.13% | 100% |
| R: connected records | 27.79% | 100% |
| G: records + gated planted beliefs | 100% | 100% |
| A: AI alone | Not run | Not run |

G matched the independent reference on all 90 company/size combinations. `eval/results/report.md` includes 95% bootstrap-over-seeds intervals. W/R/G run without model keys. This measures graph reasoning with planted beliefs, not fresh LLM extraction accuracy. The website replays source-provided Claude caches; no new GPT/Claude API execution or fresh cost comparison is claimed.

## Browser evidence

Playwright with Microsoft Edge checked live seed 7 (W=6, R=7, G=37), the ghost-duty drawer with message/joblog evidence and actual coverage query, an owes answer with 7 rows/12 cited sources, a 6/6 capacity certificate, and a six-successor preview with zero uncovered events and unchanged live fingerprint.

Desktop width 1440 and mobile width 390 were inspected. Mobile page width equals viewport width. Dark mode was captured. Browser route injection of HTTP 503 verified the explicit recorded-replay badge and disabled mutations; removing the route restores live operation. Screenshots and demo recording are under `output/playwright/`.

## External limits

Running locally; public cloud hosting, a fresh paid-model evaluation, public repository upload and event submission are not claimed. No destinations or credentials were supplied. Local deployment, reproducible tests and demo artifacts provide the ZIP's local-setup fallback. Real-company authentication, production transaction guarantees and unseen-work discovery remain outside this fixture demo.
