# Deployment and recovery

## Verified local stack

`docker compose up -d --build` starts the website/API on localhost:8000 and FalkorDB v4.22.1 on localhost:6379 with its browser on localhost:3000. The API waits for graph health. Named graph/application volumes preserve state. Inspect with `docker compose ps` and `docker compose logs --tail 100 api falkordb`. `docker compose down` stops services without erasing data.

Offline replay is the default. Supplied extraction caches support seeds 7, 101, 202 and 303. An unknown seed fails with HTTP 409; it never silently substitutes another company or calls a model. Keep any explicitly configured model keys out of source control.

The API runs one worker with serialized operations. Redis locks coordinate first import, graph-copy creation and commits across processes. Fork UUIDs prevent name collisions, and cleanup runs in `finally`. External live graph edits can still affect fingerprint comparisons; this is not MVCC.

## Checks

`docker compose --profile checks run --build --rm checks` runs the unchanged original scoring harness and additional suites. The checkout's Git history is mounted for the supplied predictions-before-results test. The tests own temporary graph processes, separate from your application data. Do not change locked assertions or manifests to conceal an integrity failure.

## Write receipts

The explicit commit action writes accepted successors to the live synthetic graph, then commits `OWNERS.d/<graph>.yaml` in `/data/ops-repo`. A stable operation ID keys local receipts under `.baton/receipts/` in that repo. External failure returns `state: external_pending` and the already committed assignments; resending the same plan retries the repository write without duplicating graph ownership. A successful retry verifies `git show HEAD:<file>`.

Only the ownership file is staged. The journal is runtime metadata. An abrupt crash between graph mutation and first journal persistence remains a gap; this is not an atomic distributed transaction. Handover checks active successors and owner uniqueness; capacity feasibility is a separate tool, not enforcement of every selected assignment. HTTP saves require a local operator session, exact-plan preview and consent attestation. Organizational permissions and independent successor accounts are not implemented. Safe ownership and receipt writes run in the Linux container; native platforms without no-follow directory handles fail closed.

## Public hosting

The pack proposes EC2 Docker plus Vercel static hosting. No AWS host, DNS name or hosting project was supplied, so no public deployment was created. The verified Compose stack includes local operator authentication, host/origin restrictions and protected writes; it remains configured for loopback access. A public deployment needs HTTPS, explicit trusted hosts, private graph ports and persistent backed-up volumes. See [operator access and security verification](SECURITY_FIXES.md).

If using a separate frontend, route its API requests to the HTTPS backend and set `BATON_ALLOWED_ORIGIN` to that frontend's origin. The bundled same-origin website requires no CORS exception. MCP runs locally with `python -m baton.mcp_server`; diagnostics must not be redirected onto protocol stdout.
