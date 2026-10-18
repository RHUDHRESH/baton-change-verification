# A company workspace people can use

The default page and `/amb.html` now open Halden's company workspace. Fonts and the green/cream palette are retained. The main experience introduces the business, its people, customer commitments and a concrete departure scenario; the benchmark is no longer the landing page.

Halden is explicitly fictional. Its description and business-impact explanations are editorial scenario context. People, roles, departure dates, evidence, scheduled events, capacity suggestions, handover results and receipts come from the existing seeded company and live API. No real customer relationship or external communication is claimed.

## Working flows

- **Understand the company:** overview, searchable people/team directory, a customer page and six understandable workstreams. Former employees are labelled and excluded from successor/task-owner choices.
- **Review evidence:** open a customer promise, recovery job, renewal or escalation dependency. Read the underlying conversation, ticket, job runs and records, with source references.
- **Plan a handover:** choose owners or apply the actual capacity solver's suggestion. Preview the next month before saving.
- **Save ownership:** operator authentication, exact-plan preview and consent attestation remain required. A save writes the graph and repository, verifies read-back and appears in Activity. Refresh retains the result.
- **Track follow-ups:** an operator can create a task tied to a responsibility, choose a staying teammate, set a due date, add notes, mark it done and reopen it. The server persists tasks in the data volume. Notes and task reads are protected by operator access. Tasks do not imply messages were sent or responsibility ownership was changed.
- **Take the context away:** download a plain-text handover brief with the work, impact, selected/saved owners and source references.

The original analysis remains at `/rehearsal.html`; Liz Zhang's Acme benchmark remains at `/benchmark.html`, linked from Technical details. The preserved benchmark still uses the original temporal graph and five question categories.

## Implementation and validation

`server/company.py` supplies the business context and source material for seed 7. Task endpoints use bounded models, known responsibility IDs, active staying owners, same-origin protections, operator sessions and a 200-task cap. Files use the same anchored no-follow/atomic operations introduced by the security fixes. Task status is durable server state, not a local checkbox simulation.

Browser checks cover navigation, directory/search, customer proof, filters, six suggested owners, preview, a downloaded brief and mobile layout. A disposable full-stack instance verifies actual six-duty save/read-back, history after reload, and task creation/assignment/completion after reload. The main service's saved companies remain intact. Test scripts: `scripts/verify_company_browser.js` and `scripts/verify_company_write_browser.js`.

Evidence is in `artifacts/company-browser-results.txt`, `artifacts/company-write-browser-results.txt`, and screenshots under `output/playwright/company-*.png`.

Latest verification: all 172 automated checks pass (88 original, 22 foundation, 39 integration/security, 23 red-team). Both new browser flows pass with no page errors; the mobile viewport measures 390/390. The preserved benchmark still matches all 25 answers.
