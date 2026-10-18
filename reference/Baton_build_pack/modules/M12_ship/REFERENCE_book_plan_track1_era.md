# Baton: the final plan (written 11:05 IST, 18 Oct; submission due 21:00)

How this was made: 8 readers each read one part of *The Leverage Toolkit* in full (every page, about 19,000 lines) and applied its tools to Baton. This file merges their answers into one decision. Where they disagreed, the call made here is marked **DECIDED** with the reason.

Probabilities are our own judgement, not data. Numbers from Halden (our synthetic company) are marked **[fixture]**.

---

## 0. The decision in 10 lines

1. **One story only: a person leaves, and Baton rehearses next month before it happens.** Access that follows the work stays in, but as a single 10-second beat using the same engine.
2. **Lead with "N-1 for people".** Grid operators simulate "what if this line trips?" every few minutes. Companies never ask "what if this person leaves?" We are EEE students, so this is knowledge few other teams have.
3. **The hero moment is "Same month, three ways".** The same Saturday is rehearsed three times, side by side:
   - **Systems of record only** finds 1 of 4 problems.
   - **AI alone** finds some of them and believes a false claim.
   - **Baton** finds all 4, each one backed by a "no path found" proof.

   This one screen proves that both the AI and FalkorDB are necessary.
4. **It is not a prediction.** The Rehearsal only walks through things the company has already scheduled: cron runs, certificate expiry dates, the on-call rota, promise due dates. Each red day is a query that found no path to anyone who can still act.
5. **The whole product is one query: "no accountable path at time t".** The Rehearsal, offboarding, grant expiry and ghost duties are four uses of it.
6. **We build about a quarter of the old design.** Okta, Jira Cloud, the six side features, precedent learning and per-agent graphs are cut. Gitea, running locally, is our real write.
7. **Nothing in the video depends on a live outside service.** A judge's clean clone runs with `OFFLINE=1`, using cached AI outputs and no API keys.
8. **The anti-"scripted" proof is built in:**
   - The generator plants schedules, never failures.
   - The answer-key hash and our predictions go into git before anything runs.
   - On camera we switch to a new random company and the result still holds.
9. **Track 1 only.** Placeholder submission at 18:30, final at 21:00.
10. **No plan guarantees first place.** Our honest estimate for this plan is about 10–15% to win Track 1 and about 20% for any prize. Reader C's model says the focused plan roughly doubles our chances compared with building everything.

---

## 1. The problem, in plain words

When someone leaves, IT removes their accounts. Nobody hands over **the things they were quietly keeping alive**:

- a job they rerun every Monday by hand
- the on-call shift that escalates to them
- a promise they made a customer in a chat
- a certificate only they renew

Nobody wrote these down, so no tool knows about them. They break weeks later, at 3 am, in front of a customer or an auditor.

**The secret (Thiel):** most people think offboarding is about access ("remove the accounts and you're done"). The dangerous part is the work nobody recorded. You can find it and test it *before* the person leaves, the same way a grid operator tests N-1.

**Who it is for:** the engineering or IT manager on the day someone on their team resigns.

> When someone on my team resigns, I want to know everything that will silently break, and get a named person to accept each piece before they go, so I don't get paged at 3 am, miss a customer promise or take an audit finding.

**Today's tools fall short (labelled data):**
- Only 27% of organisations automate offboarding (BetterCloud 2026, vendor data).
- With no confirmed owner, a P1 incident took 3 days instead of 30 minutes (Lamare, Jun 2026, a single practitioner account).
- Existing tools (Okta, SailPoint, ConductorOne) decide from *who you are*. Their default for a leaver's leftovers is "give it all to the manager". None of them asks the successor for a yes.

---

## 2. What Baton does: one query, four uses

**The core:** at any moment t, is there an *accepted* path from each obligation to a person who is still there?

| Use | What the query is asked |
|---|---|
| **Rehearsal** | On a GRAPH.COPY fork with Priya gone, step t across the next 30 days of scheduled events |
| **Offboarding gate** | Same fork, t = her last day. Any obligation with no path blocks the departure |
| **Grant expiry** (access follows the work) | t = now. Every grant whose reason path has broken (tested) |
| **Ghost duties** (the query run in reverse) | Repeated actions by a person on something they have no duty path to |

**Hero query (tested at 11:10 on v4.22.1, `verify/hero_check.py`). On the live graph the 03:12 page reaches Priya through the rota → Kenji (already left) → Priya chain. On the fork with Priya gone, both events return `no_path = true`:**

```cypher
// run on the fork, after: MATCH (p:Person {id:$leaver}) SET p.left_at = $leave_at
MATCH (e:Event)-[:NEEDS]->(d:Duty)
WHERE e.at >= $from AND e.at < $to
OPTIONAL MATCH path = (d)-[:HELD_BY|ROUTES_TO|ESCALATES_TO*1..4]->(who:Person)
WHERE all(r IN relationships(path)
          WHERE r.vf <= e.at AND r.vt > e.at AND coalesce(r.status,'confirmed') = 'confirmed')
  AND (who.left_at IS NULL OR who.left_at > e.at)
WITH e, d, collect(DISTINCT who.id) AS can_act
RETURN e.id, d.id, (e.at - $from) / $day AS day, can_act, size(can_act) = 0 AS no_path
ORDER BY e.at
```

Python only moves the clock forward. The query decides each day. Every red row links to the edge and timestamp it came from, labelled *scheduled* or *believed*.

**Who decides what (put this in the README word for word):**

> **The model reads. The graph decides. A human confirms.**

- The AI turns messy chat and log text into *believed* facts (JSON only). It never writes Cypher.
- A belief becomes a fact only with **2 independent sources plus the person's own yes**.
- Every verdict comes from fixed Cypher or `algo.maxFlow`: grant, block, IMPOSSIBLE, red day.
- Responsibility moves **on accept, not on send**. The old owner's edge closes only after the successor has accepted and the write has been read back (make-before-break).

---

## 3. The hero moment: "Same month, three ways"

Three forks of the same company, with the same Saturday removed and the same query:

| | Systems of record only (W) | AI alone (A) | Baton (G) |
|---|---|---|---|
| **What it has** | Ownership fields, group memberships, direct on-call. This is what an offboarding workflow template uses. | Same raw text and tables, same model, no graph | Graph plus AI-extracted beliefs that passed the gate |
| Day 17: TLS cert expires (in an owner field) | ✅ | ✅ | ✅ |
| Day 6, 03:12: payments page reaches nobody (escalation chain, 4 hops: rota → secondary who already left → Priya) | ❌ only looks one hop | likely ❌ | ✅ no-path proof |
| Day 3: Monday recon fails (ghost duty: job log plus a Slack line) | ❌ no field records it | maybe ✅ | ✅ after Priya says yes |
| Day 7: Acme credit promise missed (only exists in a chat thread) | ❌ | maybe ✅ | ✅ |
| False chat claim "Sam owns recon now" | n/a | likely **believes it** | **Blocked: no accepted edge** |

- **Delete the model** and Baton falls back to W. It is blind to anything that lives only in chat.
- **Delete the graph** and you get A: it misses chained failures and repeats a false claim. Research found a planted false belief gets repeated 97–99% of the time.

So **one screen passes both "is it AI-native?" and "is FalkorDB central?"**

**Write the W definition into git before generating any data**, so nobody can say we shaped the company to make W lose. Then make our predictions about A and commit those before running it.

**Honesty line, shown on screen:** "The Rehearsal is a lower bound. It only counts duties it can trace to two sources. A frequency rule could also catch the recon job. The chat-only promise and the false claim are what need both AI and graph."

---

## 4. Scope: the barbell

| | Item | Owner | Status |
|---|---|---|---|
| **SAFE CORE** (~60% of hours) | Generator that plants *schedules only*, plus a validator and a sealed answer key (hash committed) | Builder 1 | new |
| | Load into one tenant graph; AI extraction to believed facts; 2-source plus yes gate | B1 / B2 | gate tested |
| | Variable-length work path, nested-group reach, depth-1 vs depth-6 | B1 | tested |
| | Single-query commit with authority re-check and UNIQUE owner constraint | B1 | tested |
| | Gitea, local in Docker: issue assignment is the "work" signal; the CODEOWNERS commit is the real write, read back, with a receipt | B2 | new |
| | Broken-reason-grant query (access follows the work) | B1 | tested |
| | `docker compose up && make demo`, FalkorDB pinned to `v4.22.1`, `OFFLINE=1` cache, stop FalkorDB → Baton refuses loudly | B2 | new |
| **BOLD BET** (~40%) | Rehearsal via the hero query, "Same month, three ways", live-graph hash unchanged | B1 | half tested |
| | Accountability Cut: IMPOSSIBLE 3/4, with the min-cut naming the gap | B1 | tested |
| | Sealed mini-eval: 20–25 cases, lanes W/A/G, predictions committed first, A's win reported | B1 | new |
| **STRETCH** (only if green at 14:30) | Candidate successors: AI proposes 2, each fork scored ("Ravi → 0 failures; Sam → day 3 still fails"), human picks | B2 | new |
| | Slack interactive Accept. **DECIDED:** default is a local accept button / CLI; Slack only if it works by 14:30, because Reader C's sums gave it no positive edge | B2 | new |
| | Proactive trigger: leave filed → Rehearsal posted automatically | B2 | new |
| **CUT** | Okta, Jira Cloud (Gitea issues replace it), promise keeper, fragility radar, incident routing, day-one joiners, audit Q&A, precedent learning, per-agent graphs, "rehearse anything" montage, Track 3, any custom UI (judges use FalkorDB Browser) | — | — |

**DECIDED: precedent learning is cut.** Readers B and H said cut; C said 0.4 h. It is the hardest claim to make honestly ("learns") and no hero beat needs it.

---

## 5. The 2:45 video: 6 beats, one focal point (red timeline turns green)

| Time | On screen | Words (plain) |
|---|---|---|
| 0:00–0:15 | Phone shows a 03:12 page. FalkorDB Browser: the path ends at Priya, valid_to = Saturday | "Priya left on Friday. On Wednesday at 3 am the payments pager rang for someone who no longer works here." |
| 0:15–0:40 | Rewind to Friday. Leave filed and Baton starts on its own. Job log plus Slack line become a believed duty, and Priya taps Yes. A promise is pulled from a chat thread | "Baton reads the team's chat and job logs. It found a job Priya reruns every Monday that no system knew was hers. It only counts it once two sources agree and Priya says yes." |
| 0:40–1:30 | **Same month, three ways**: three columns. W 1/4. AI alone 2/4 plus a false belief. Baton 4/4. Red days click through to their Cypher. Live-graph hash: same before and after | "Same company, same Saturday, three ways. Without the AI you see one problem. Without the graph, the AI believes a false message. Baton finds all four. Each one is a path that doesn't exist, and that's proof, not a guess. Our real graph is untouched." |
| 1:30–1:55 | Cut: **IMPOSSIBLE 3/4**, with the min-cut highlighted (nobody left has write access to ledger-core). AI draft "Sam owns this now" **blocked** | "And the team left behind can't absorb it. That's proven by max-flow. The AI tried to say Sam took over. He never accepted, so Baton blocks it." |
| 1:55–2:25 | Ravi accepts. Gitea CODEOWNERS commit, read back, receipt. Replay: **4 → 0**, all green. 5 s: stop FalkorDB and Baton refuses. 10 s: Arjun's grant ends when his incident closes | "Responsibility moves on accept, not on send. The real change is written, then read back. Replay: zero failures. Turn off FalkorDB and Baton refuses to act. Same engine, every day: access lasts only as long as the work." |
| 2:25–2:45 | Lane table: predictions hash, A's win shown, a new random company. Limits line | "Predictions committed before we ran. AI alone beat us on plain-language requests. Grid operators run N-1 every few minutes. Now companies can. Baton." |

**Taglines** (use one per surface; don't stack them):
- README line 1: **"A baton isn't passed until it's caught."**
- Video close: **"N-1 for people."**
- Rule: **"Responsibility moves on accept, not on send."**
- Proof: **"No path, no promise."**

**Never say:**
- "predicts failures"
- "autopilot"
- "replaces Okta"
- "production-ready"
- MVCC
- "credentials are the #1 breach vector"
- unlabelled vendor statistics
- anything about rival entries
- "accountability graph" as the headline

---

## 6. Hour-by-hour plan with kill times

B1 = engine (graph, generator, eval). B2 = action and story (compose, Gitea, accept, video, README). Coding agents write the code; your attention is what runs out, so each person has **one open feature at a time**.

| Time (IST) | Who | Deliverable | Done means | If not done |
|---|---|---|---|---|
| 11:15–11:30 | Both | Sign the cut list and kill times (`KILL.md` committed). Write and commit the W definition. Track 1 only | Committed | Stop at 11:30 regardless |
| 11:30–12:30 | B1 | Generator v0: 12 people, 8 services, nested groups, rota, cron, cert dates, Acme promise in chat, ghost-duty evidence, false claim, sealed key. **Plants schedules, never failures.** Plus a validator | Validator passes; key hash printed | **12:30 → hand-written fixture JSON**; generator becomes a README limit |
| 11:30–12:30 | B2 | Compose (FalkorDB `v4.22.1` + Gitea), extraction prompt → JSON with cache, Gitea CODEOWNERS write + read-back | `compose up` clean; 3 sample lines give valid JSON; one write read back | Gitea write via plain git push |
| 12:30–13:15 | Both | **Walking skeleton:** `make demo` runs generate → load → extract → gate → fork → Rehearsal → accept → write → read-back → replay, on fresh volumes | One command prints the receipt | **13:15 → fixture; all stretch items dead** |
| 13:15–13:30 | B1 | Commit predictions (§9) and the seed hash. **Mid-term exam:** on an unseen seed W ≤ 1/4, G 4/4 with 0 invented failures, replay 0 | Exam passes 3 runs out of 3 | If W ≥ 3/4, the AI claim is decoration: hero becomes ghost duties + false-claim block |
| 13:15–13:30 | B2 | README skeleton (§7) | Headings in | — |
| 13:30–14:30 | B1 | Three-way forks, hero query, hash proof, Cut certificate on Halden | One command renders all three columns | **14:30 → hero = Cut certificate + broken-reason query** (both tested) |
| 13:30–14:30 | B2 | Accept (local button), make-before-break write, stop-FalkorDB refusal, A-lane harness | Round trip works once | Slack stays out |
| 14:30–15:15 | B1 | Eval: 20–25 cases, 4–5 families, run **once** | Table with n, per-family scores, A's win | **15:15 →** 3 families, or "pre-registered, not run" |
| 14:30–15:15 | B2 | Stretch (candidate successors, then Slack) **only if everything is green**; otherwise shot list + saved Browser queries | — | Skip silently |
| **15:30** | Both | **No new features.** An agent runs clean clone #1 in a fresh container | Clone log saved | Fix only what broke |
| **16:00** | Both | Freeze checklist (§8A), tag `v-freeze` | Tag pushed | Never edit the tag in place |
| 16:00–17:00 | B1 / B2 | B1: bug fixes and `OFFLINE=1`. B2: record each beat separately, 2 takes each | All 6 beats captured | Use recorded terminal runs |
| 17:00–18:00 | B2 / B1 | B2: edit to ≤2:45, captions, AI-use slate. B1: README numbers, claims ledger | Unlisted upload by 18:00 | **18:00 → 60-s hero-only cut + stop-FalkorDB beat** |
| **18:30** | B2 | **Placeholder submission** (if the form allows edits) | Submitted | — |
| 18:00–19:30 | Both + GPT | Each reads the other's claims cold. GPT checks every claim against the ledger. Q&A drill (§10) | No unsourced claim | Delete the claim |
| 19:30–20:30 | Both | Red buffer: fix red items only, log why each went red | — | Nothing new |
| **20:30** | **The non-author runs it** | Clean clone #2 from the README alone, fresh container, `OFFLINE=1` | Passes | **`git checkout v-freeze`**, no patching forward |
| **21:00** | Both | Pre-submit checklist (§8B). **Submit.** | Form submitted | — |
| 21:00–23:59 | — | Untouched buffer, emergencies only | — | — |

---

## 7. README top (paste and fill in the [ ] numbers from the real run)

```markdown
# Baton — a baton isn't passed until it's caught

When someone leaves, IT removes their accounts. Nobody hands over the things they were
quietly keeping alive: the job they rerun every Monday, the on-call chain that ends at
them, the promise they made a customer in a chat. Baton finds that work, rehearses the
next 30 days on a copy of the company without them, and won't let them go until a named
person has accepted each piece.

**N-1 for people.** Grid operators ask "what if this line trips?" every few minutes.
Baton asks "what if this person leaves?" — before Friday.

- **The model reads. The graph decides. A human confirms.** The LLM turns chat and logs
  into *believed* facts (JSON). It never writes Cypher. A belief becomes a fact only with
  two independent sources and the person's own yes.
- **Not a prediction.** The Rehearsal walks obligations already scheduled in the graph
  (cron, cert expiry, on-call rota, promise dates). Each red day is a Cypher query that
  found no accepted path to anyone still there. "No path found" is the proof.
- **Same month, three ways.** Systems of record only: [1]/4. AI alone: [x]/4 and adopted
  a false claim. Baton: [4]/4. Predictions committed before the run: `<hash>`.
- **Responsibility moves on accept, not on send.** The successor accepts, the Gitea
  change is written and read back, and only then does the old edge close.
- **Turn FalkorDB off and Baton refuses to act.**

> Halden is a synthetic company (FIXTURE). Writes to the local Gitea are real.
> AI use: [what GPT/Claude wrote] — see AI-USE.md.
```

Below that, in order:
1. The hero Cypher (5–10 lines).
2. The data model.
3. The list of queries and algorithms Baton depends on (required by rule 10).
4. The lane table, including the family where we lost.
5. The flow-network definition for the Cut: duties are sources, people are sinks, acceptance edges have capacity 1, and "3/4" means one duty has no possible taker.
6. Fork timing and graph size.
7. "We knowingly do not".
8. AI disclosure.

**We knowingly do not** (put it near the top, with reasons):
- **Okta or Jira Cloud.** Neither is needed for the proof and both add fragile sign-ins. Gitea issues stand in for tickets.
- **Promise keeper, fragility radar, day-one access, audit Q&A** as separate features. They run on the same engine but weren't built or tested this round.
- **Precedent learning, per-agent graphs.** Not built.
- **Predict unknown events.** The Rehearsal only walks what is already scheduled. It is a lower bound.
- **Claim MVCC or scale.** We use v4.22.1, the C engine, on one synthetic company with a small eval.
- **Store real chat text.** Only derived facts with permalink and hash, because Slack's API terms ban bulk export and LLM use.

---

## 8. Checklists (read aloud; either person can stop the release)

**A. Freeze, 16:00**
1. `docker compose up && make demo` is green on fresh volumes.
2. `falkordb/falkordb:v4.22.1` is pinned everywhere (not `latest`).
3. No LLM output reaches a Cypher string; grep shows only parameterised queries.
4. No lane ever loads the answer key.
5. Predictions and the W definition were committed before the eval (hash in the README).
6. The live-graph hash is unchanged after the Rehearsal and the Cut.
7. A risky write with no accept fails loudly.
8. Stopping FalkorDB makes Baton refuse.
9. Tag `v-freeze` is pushed. "Any concern before we freeze?"

**B. Pre-submit, 20:30**
10. The non-author passed clean clone #2 from the README alone.
11. `OFFLINE=1` works with no API key.
12. The video is ≤2:45, opens when logged out, and discloses AI use.
13. Every number is sourced, and vendor data is labelled.
14. No MVCC, "#1 breach vector" or "predicts" claims.
15. Data is synthetic only; gitleaks shows no secrets.
16. "We knowingly do not" is near the top.
17. The lane table shows A's win.
18. The form lists Track 1, the repo, the video and AI disclosure, and the code is new this hackathon.
19. "Anyone see a reason not to submit?"

---

## 9. Predictions: commit these to git by 13:30, before any lane runs

| Eval family | Prediction | P |
|---|---|---|
| Hidden chained dependency | Baton beats both; rules miss it entirely | 0.90 |
| False chat ownership claim | AI-only adopts it in ≥30% of cases; Baton <10% | 0.80 |
| Nested-group reach | AI-only misses the customer-pii reach in ≥40% | 0.80 |
| Grants that should end | Baton recall ≥95%; rules <50% | 0.75 |
| Plain-language requests | **AI-only wins** | 0.70 |
| Overall | Baton best in ≥4 of 5 families | 0.65 |

| Hackathon outcome | P |
|---|---|
| Valid submission that passes a clean clone | 0.85 |
| Top-50 t-shirt | 0.45 |
| Any prize | 0.20 |
| Track 1 win | 0.10–0.15 |

These are judgement, not data. Score them with Brier when results come out.

---

## 10. The hardest questions and 30-second answers

1. **"What works without FalkorDB?"** Nothing gets decided. Every block, red day and IMPOSSIBLE verdict is Cypher or `algo.maxFlow`. Without the graph you get the AI-only lane, which lost [n] of 5 families. We show the stop-FalkorDB refusal.
2. **"You planted the failures."** No. The generator plants schedules: cron, rota, cert dates, promises. The failures are worked out by traversal on a fork. The key was sealed (hash committed), and we re-rolled the company on camera.
3. **"What breaks without the LLM?"** Anything that only exists in chat. The promise to Acme and the meaning of Priya's Monday reruns disappear, and you're left with the W column: 1 of 4.
4. **"What stops a hallucinated owner?"** It stays *believed* until two independent sources and a human yes. The UNIQUE constraint makes a second owner impossible. The demo blocks "Sam owns this now".
5. **"How is this different from Okta, SailPoint or ConductorOne?"** They decide from who you are and move leftovers to the manager. Baton decides from the work, asks the successor to accept, and rehearses the month before it happens.
6. **"What does maxFlow model?"** Duties are sources and the remaining people are sinks; an edge exists where someone has the access and skill, with capacity 1. A flow of 3/4 proves one duty has nobody who can take it, and the min-cut names the gap. It's the grid's N-1 thinking.
7. **"Why GRAPH.COPY?"** It gives a full fork in [ms] for [nodes/edges]. We rehearse, then throw the fork away, and the live hash shows nothing changed.
8. **"What's real and what's mocked?"** Real: FalkorDB, all queries, the local Gitea writes and read-backs. Synthetic: the company, its chat and logs. Not built: the list in the README.
9. **"Who decides two sources are independent?"** A fixed rule: sources of different types (chat vs job log), from different systems, not derived from each other. We say plainly that in the demo one generator wrote both.
10. **"Why did AI-only win plain-language requests?"** Because understanding loose wording is what models are good at. We report it rather than hide it.

---

## 11. What happens next (only if you say go)

The next step is the **walking skeleton**, due 13:15. First comes the generator, planting schedules only, along with the W definition committed before any data exists. I can start writing it now.
