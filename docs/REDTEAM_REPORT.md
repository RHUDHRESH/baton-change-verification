# Baton red-team test report

**Current status: all five findings and the browser-header gap below are fixed.** See [fixes and current end-to-end results](SECURITY_FIXES.md). The following is the original pre-fix audit; its source line numbers and vulnerable behavior describe that revision.

Tested 2026-10-18 against the local v0.2 application. No production security fixes were applied in this audit. Tests ran against an isolated, disposable FalkorDB; the browser payload was injected into an intercepted response and removed afterward. No third-party service was attacked. The later Acme demo has separate bounds/injection tests but was not part of this original audit.

23 backend attack scenarios reproduced successfully; **this does not mean 23 security passes**. Five scenarios confirmed weaknesses, one identified missing defense headers. A separate real-browser DOM injection test was blocked. Evidence: `artifacts/redteam-observations.json`, `artifacts/redteam-tests.xml`, `artifacts/redteam-browser-results.txt`, `output/playwright/redteam-xss.png`.

## Findings

### RT-01 — High if exposed: callers can commit without identity or acceptance

`server/app.py:148` invokes the commit CLI without authentication, authorization, preview validation or successor acceptance. An unauthenticated request changed the isolated live graph and produced a verified repository receipt. Arbitrary Host and Origin headers were also accepted. The compose service binds to loopback, and the project documents itself as a local demo; this limits the default exposure. This was a direct HTTP test, **not a demonstrated browser cross-origin exploit or DNS-rebinding exploit**. Ordinary cross-origin JSON preflight was denied, and simple text/plain and form requests were rejected. CORS does not provide caller authentication; see [FastAPI CORS documentation](https://fastapi.tiangolo.com/tutorial/cors/).

Mitigation: require authenticated, authorized users for writes and validate the accepted plan server-side; restrict allowed hosts. Establish actual successor consent if the product promises it.

### RT-02 — Medium: unrelated evidence can promote an invented duty

`baton/rehearse.py:38` (`Q_GATE`) treats message/ticket sources with null `people` as relevant to any belief. An invented duty citing two unrelated existing sources of different types was promoted with `confirm=all`. This requires control over proposed beliefs through a cache, CLI input or extraction output; no HTTP belief-upload endpoint was found. The test demonstrates semantic evidence weakness, not a successful live-model prompt injection.

Mitigation: validate person/duty relevance for every cited source and require meaningful corroboration. Preserve the distinction between a claim and an accepted obligation.

### RT-03 — Medium: unbounded assignment strings cause an internal error

`server/app.py:141` limits assignment count but not individual key/value lengths. A 150,000-character key reached subprocess creation and returned HTTP 500 on Linux due to argument-size limits. Only one request was tested; sustained denial of service was not attempted.

Mitigation: validate identifier lengths and membership before spawning a CLI; impose request-body limits and map expected validation failures to 422/413.

### RT-04 — Medium: rejected uncached seeds leave files behind

`server/app.py:33` generates a company before discovering that its offline extraction cache is absent. Six uncached seeds returned 409 but left six directories containing 175,306 bytes in the disposable test directory. A caller with access can repeat across the large seed space; disk exhaustion was not attempted.

Mitigation: reject unsupported offline seeds before generation, or generate in a bounded temporary directory and publish only after successful extraction.

### RT-05 — Medium, local prerequisite: repository symlink redirects writes

`baton/commit.py:135` (`_write_external`) uses `Path.write_text` on the ownership destination. In a controlled temporary repository, a symlink redirected the write to a sentinel file outside that repository. Exploitation requires control over repository contents/filesystem; the default API creates its own repository. This does not establish a remote path to host takeover.

Mitigation: reject symlinks in destination parents and leaf, resolve and enforce repository containment, and use an atomic write strategy that does not follow links.

### RT-06 — Low: browser defense headers absent

Responses lacked Content-Security-Policy, X-Content-Type-Options and X-Frame-Options. This is a hardening gap; clickjacking or script execution was not demonstrated. Add a CSP suited to the application assets, `nosniff`, and frame restrictions before public deployment.

## Defenses that held

Assignment/ask injection strings did not mutate the graph or execute shell code; static path traversal returned 404; duplicate evidence failed corroboration; invalid seeds, oversized questions and forbidden raw-query fields returned 422. Cross-origin simple-body requests returned 422 and unknown-origin preflight returned 405. DOM payloads in names, duty labels and source text rendered literally: no injected img/svg elements and no execution marker.

## Reproduction

From the repository root:

```powershell
docker run --rm -v 'C:\Users\acer\Desktop\GraphHacks:/workspace' graphhacks-checks python -m pytest tests/redteam -q --junitxml=artifacts/redteam-tests.xml
```

Browser attack: `scripts/redteam_browser.js` via the established Playwright CLI session against the local demo. Original locked-test integrity verification passed. No dependency-advisory scan, external deployment assessment, model-key extraction test or exhaustive penetration test was performed.
