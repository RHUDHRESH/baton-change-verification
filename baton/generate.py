"""Deterministic generator of "Halden", the synthetic demo company (label FIXTURE).

`python -m baton generate --seed N --out DIR` writes DIR/world.json (what the company's systems hold: people, duties,
ownership/rota/escalation records, scheduled events, chat, job logs, tickets) and DIR/answer_key.json (the beliefs a
reader of that chat would form, split into true ones and planted noise). It also holds capability data for the Cut:
CAN records (who could take on a recorded duty) and people[].capacity. The world holds schedules only: nothing in it
says what breaks when someone leaves. Every choice comes from random.Random(seed) and a fixed base date, never the clock.
"""
import json
import random
from datetime import datetime, timezone
from pathlib import Path

DAY = 86_400_000
HOUR = 3_600_000
WINDOW_DAYS = 30
BASE_NOW = 1_792_713_600_000  # Friday 2026-10-23 00:00 UTC; the leaver's last day

FIRST = ["Mira", "Tomas", "Anika", "Dev", "Priya", "Jonas", "Lena", "Rafael", "Sofia", "Kwame", "Ines", "Arjun",
         "Hana", "Mateo", "Freya", "Omar", "Yuki", "Elena", "Tariq", "Nadia", "Felix", "Zara", "Ravi", "Clara",
         "Bao", "Lucia", "Emeka", "Ingrid", "Noah", "Amara"]
LAST = ["Okafor", "Lindqvist", "Sharma", "Moreau", "Castillo", "Nakamura", "Brandt", "Haddad", "Ferreira",
        "Kowalski", "Mensah", "Iyer", "Novak", "Duarte", "Halvorsen", "Achebe", "Rossi", "Petrov", "Silva", "Engel",
        "Varga", "Osei", "Tanaka", "Quinn", "Abara", "Lund"]
ROLES = {
    "Platform": ["Staff SRE", "Senior SRE", "Platform engineer", "SRE"],
    "Security": ["Security lead", "Security engineer"],
    "Billing": ["Billing engineer", "Senior backend engineer", "Payments engineer"],
    "Support": ["Support lead", "Customer success manager", "Support engineer"],
    "Data": ["Data engineer", "Analytics engineer"],
}
SERVICES = ["api", "checkout", "payments", "auth", "partners", "ledger", "webhooks", "status", "files", "search"]
DOMAINS = ["halden.io", "halden-pay.com", "haldenhq.net"]
APPS = ["Halden Go", "Halden Driver", "Halden Pay"]
IDPS = ["Okta", "Azure AD", "Google Workspace", "OneLogin"]
ONCALL = [("checkout", "Checkout"), ("payments-api", "Payments API"), ("core-platform", "Core platform"),
          ("edge", "Edge and CDN"), ("identity", "Identity")]
JOBS = [("billing-reconcile", "Nightly billing reconciliation", "Billing"),
        ("warehouse-snapshot", "Warehouse snapshot to cold storage", "Data"),
        ("search-reindex", "Search index rebuild", "Platform"),
        ("partner-sftp-export", "Partner SFTP export", "Data"),
        ("gdpr-sweep", "GDPR deletion sweep", "Security"),
        ("invoice-pdf-batch", "Invoice PDF batch", "Billing"),
        ("payroll-export", "Payroll export to Ledgerly", "Billing"),
        ("usage-rollup", "Usage metering rollup", "Data")]
REVIEWS = [("aws-access-review", "Quarterly AWS access review", "review"),
           ("pg-failover-drill", "Postgres failover drill", "drill"),
           ("backup-restore-test", "Monthly backup restore test", "drill"),
           ("pentest-scoping", "Annual pentest scoping call", "review")]
OTHER_DUTIES = [("soc2-evidence", "SOC 2 evidence upload", "compliance", "Security"),
                ("statuspage-report", "Monthly status-page report", "report", "Support"),
                ("vat-filing-export", "VAT filing export", "report", "Billing"),
                ("churn-dashboard", "Churn dashboard refresh", "report", "Data")]
ORPHANS = [("partner-key-rotation", "Partner API key rotation", "rotation"),
           ("dr-runbook-review", "Disaster-recovery runbook review", "review")]
CUSTOMERS = ["Brightwell Foods", "Kestrel Logistics", "Oaktree Clinics", "Norvale Bank", "Pinecrest Media",
             "Tidemark Retail", "Larkspur Travel", "Quayside Energy"]
PROMISES = [("csv-export", "a fix for the CSV export encoding"),
            ("sso", "SSO through {idp}"),
            ("rca", "the written RCA for last week's outage"),
            ("eu-region", "their move to the EU region"),
            ("rate-limit", "a rate-limit bump to 500 req/s"),
            ("audit-export", "a full audit-log export")]
VENDORS = ["PagerDuty", "Datadog", "Cloudflare", "Snowflake", "Twilio"]
CAUSES = ["S3 throttling", "expired DB creds", "a lock timeout", "the worker running out of memory",
          "the partner SFTP being flaky", "a schema drift upstream"]

T_GHOST_MSG = [
    "re-ran {job} by hand again, {cause} bit it around {hh}:00. I'll keep an eye on it",
    "{job} fell over overnight ({cause}), kicked it manually. all green now",
    "fyi I babysit {job}. if it goes red just rerun it with --resume, I usually do it before standup",
    "{job} failed again, reran it myself. one day I'll fix {cause} properly",
    "had to restart {job} at {hh}:30 - {cause} again. done now, numbers look right",
]
T_GHOST_CLAIM = [
    "{who} keeps {job} running by re-running it by hand when it fails",
    "{who} is the person who restarts {job} whenever it breaks",
    "{job} only stays green because {who} reruns it manually",
]
T_PROMISE_MSG = [
    "Spoke to {contact} at {cust} - I promised them {what} by {date}. I'll own that one.",
    "told {cust} we'd have {what} done by {date}, that's on me",
    "{cust} call went ok. Committed to {what} by {date}; I'll ping {contact_first} when it's out",
    "ok so I may have promised {cust} {what} by {date}. I'll sort it",
]
T_PROMISE_TICKET = [
    "Following up on our call with {leaver_first}: you committed to {what} by {date}. Please confirm we're on track.",
    "Hi team, {leaver_first} promised us {what} by {date}. Our launch depends on it - any update?",
    "Re: {what}. {leaver_first} said {date}. Can someone confirm that date still holds?",
]
T_PROMISE_CLAIM = [
    "{who} promised {cust} {what} by {date}",
    "{who} personally committed to deliver {what} to {cust} by {date}",
]
T_TRANSFER = [
    "pretty sure {s} took over {job} last month?",
    "{s} owns {job} now I think, saw them poking at it",
    "isn't {job} {s}'s thing these days?",
]
T_VENDOR = [
    ("{l} is the one who deals with the {v} renewal, right?", "yeah I think {l} handles {v}, ask them"),
    ("who renews {v}? {l}?", "{l} did it last year I believe"),
]
T_FILLER = [
    "deploying {svc} {ver} to prod",
    "standup: finishing the {svc} migration, then reviews",
    "anyone seen elevated 5xx on {svc}? looks fine now",
    "reminder: retro at 3pm",
    "PR for the {svc} rate limiter is up, would love a review",
    "rolled back {svc} {ver}, investigating",
    "lunch order closes in 10",
    "{svc} dashboards moved to the new folder, links in the wiki",
]
T_FILLER_TICKET = [
    "Invoice for last month shows the wrong VAT number",
    "Can't log in via SSO since this morning",
    "CSV export stuck at 99% for our account",
    "Webhook deliveries delayed by ~10 minutes",
]
CHANNELS = {"Platform": "#platform", "Security": "#security", "Billing": "#billing", "Support": "#support",
            "Data": "#data-eng"}


def _slug(s):
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-").replace("--", "-")


def _date(ms):
    d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return d.strftime("%a ") + str(d.day) + d.strftime(" %b")


class _Halden:
    def __init__(self, seed):
        self.seed = seed
        self.rng = random.Random(seed)
        self.now = BASE_NOW
        self.leave_at = self.now + DAY
        self.end = self.now + WINDOW_DAYS * DAY
        self.people, self.duties, self.records = [], [], []
        self.events, self.messages, self.joblogs, self.tickets = [], [], [], []
        self.esc = {}
        self.true_beliefs, self.noise_beliefs = [], []
        self.duty_pool = {}  # duty id -> who could take it on (scale > 1: the people of the duty's own unit)
        self.unit = None  # None = the core company; a business unit (see _Unit) prefixes its ids, names, channels
        self.units = []

    # unit-aware naming: identity for the core company, so scale 1 is unchanged byte for byte -----------------
    def _sid(self, sid):
        return sid if self.unit is None else f"{self.unit}-{sid}"

    def _nm(self, name):
        return name if self.unit is None else f"{name} ({self.unit_label})"

    def _ch(self, channel):
        return channel if self.unit is None else f"#{self.unit}-{channel.lstrip('#')}"

    # helpers -------------------------------------------------------------------------------------------------
    def person(self, pid):
        return next(p for p in self.people if p["id"] == pid)

    def first(self, pid):
        return self.person(pid)["name"].split()[0]

    def duty(self, did, name, kind):
        self.duties.append({"id": did, "name": name, "kind": kind})
        return did

    def owner(self, did, pid):
        self.records.append({"type": "OWNER", "duty": did, "person": pid,
                             "since": self.now - self.rng.randint(45, 700) * DAY})

    def event(self, did, at, label):
        self.events.append({"duty": did, "at": at, "label": label})

    def escalate(self, a, b):
        self.esc[(a, b)] = {"type": "ESCALATES_TO", "from_person": a, "to_person": b}

    def msg(self, channel, author, at, text):
        m = {"channel": channel, "author": author, "at": at, "text": text}
        self.messages.append(m)
        return m

    def past(self, lo_days, hi_days):
        return self.now - self.rng.randint(lo_days, hi_days) * DAY + self.rng.randint(8, 19) * HOUR \
            + self.rng.randint(0, 59) * 60_000

    # world ---------------------------------------------------------------------------------------------------
    def build(self, scale=1):
        r = self.rng
        self._people()
        self.services = r.sample(SERVICES, len(SERVICES))
        self.jobs = r.sample(JOBS, len(JOBS))
        self._certs()
        self._shared_and_other_duties()
        self._oncall()
        self._ghost_jobs()
        self._owned_jobs()
        self._promises()
        self._noise()
        self._chatter()
        if scale > 1:
            self._grow(scale)
        return self._finish()

    def _grow(self, scale):
        """Scale N: add business units until people, events and messages are each at least N x the core company
        (and at least N - 1 units). Each unit is a whole department built by the same planting code from its own RNG
        stream (so the core stream, and scale 1, are untouched) around a local anchor who stays: its own duties,
        rotas, ghost jobs and promises (true beliefs, held by the anchor), noise claims and chatter. About half the
        units' stale on-call shifts escalate to the real leaver: hidden dependencies only the records reveal."""
        base = {k: len(getattr(self, k)) for k in ("people", "events", "messages")}
        taken = {p["name"] for p in self.people}
        k = 1
        while k < scale or any(len(getattr(self, x)) < scale * n for x, n in base.items()):
            if k > 4 * scale + 4:
                break
            u = _Unit(self, k, taken)
            u.build_unit()
            self.units.append(u)
            for attr in ("people", "duties", "records", "events", "messages", "joblogs", "tickets", "true_beliefs",
                         "noise_beliefs"):
                getattr(self, attr).extend(getattr(u, attr))
            self.esc.update(u.esc)
            for d in u.duties:
                self.duty_pool[d["id"]] = u.stayers + [u.leaver]
            k += 1

    def _names(self, k):
        r = self.rng
        return [f"{a} {b}" for a, b in zip(r.sample(FIRST, k), r.sample(LAST, k))]

    def _people(self):
        r = self.rng
        n_active, n_gone = r.randint(6, 9), r.randint(1, 3)
        names = self._names(n_active + n_gone + 8)
        self.spare_names = names[n_active + n_gone:]
        leaver_team = r.choice(["Platform", "Security"])
        teams = [leaver_team, "Platform", "Platform", "Billing", "Support"]
        teams += [r.choice(list(ROLES)) for _ in range(n_active - len(teams))]
        teams += [r.choice(list(ROLES)) for _ in range(n_gone)]
        for i in range(n_active + n_gone):
            name = names[i]
            role = r.choice(ROLES[teams[i]][:2] if i == 0 else ROLES[teams[i]])
            left = None if i < n_active else self.now - r.randint(4, 75) * DAY + 17 * HOUR
            self.people.append({"id": _slug(name).replace("-", "."), "name": name, "team": teams[i],
                                "role": role, "left_at": left})
        self.leaver = self.upstream = self.people[0]["id"]
        self.stayers = [p["id"] for p in self.people[1:n_active]]
        self.gone = [p["id"] for p in self.people[n_active:]]
        self.manager = next(p for p in self.stayers if self.person(p)["team"] == "Platform")

    def _certs(self):
        r = self.rng
        dom, app, idp = r.choice(DOMAINS), r.choice(APPS), r.choice(IDPS)
        self.idp = idp
        cands = [(f"tls-{s}", f"TLS certificate for {s}.{dom}", "cert") for s in self.services[:3]]
        cands += [(f"apns-{_slug(app)}", f"Apple push certificate for {app}", "cert"),
                  (f"saml-{_slug(idp)}", f"SAML signing certificate for {idp}", "cert"),
                  (f"domain-{_slug(dom)}", f"Domain registration for {dom}", "renewal"),
                  ("codesign-windows", "Windows code-signing certificate", "cert"),
                  ("stripe-webhook-secret", "Stripe webhook signing secret rotation", "renewal")]
        n = r.randint(1, 3)
        picked = r.sample(cands, n + 1)
        self.leaver_duties = []
        for i, (sid, name, kind) in enumerate(picked):
            name = self._nm(name)
            did = self.duty(f"d-{self._sid(sid)}", name, kind)
            self.owner(did, self.leaver)
            self.leaver_duties.append(did)
            day = r.randint(2, WINDOW_DAYS - 1) if i < n else r.randint(WINDOW_DAYS + 5, 90)
            at = self.now + day * DAY + r.randint(0, 23) * HOUR
            self.event(did, at, f"{name} expires")
            if at - 14 * DAY >= self.now:
                self.event(did, at - 14 * DAY, f"{name}: renewal reminder")
        # something the leaver still does before they go (inside the window, before leave_at)
        first = self.leaver_duties[0]
        self.event(first, self.now + r.randint(9, 16) * HOUR, "Renewal ticket opened")

    def _shared_and_other_duties(self):
        r = self.rng
        sid, name, kind = r.choice(REVIEWS)
        name = self._nm(name)
        did = self.duty(f"d-{self._sid(sid)}", name, kind)
        co = r.choice([p for p in self.stayers if self.person(p)["team"] == "Platform"])
        self.owner(did, self.leaver)
        self.owner(did, co)
        self.event(did, self.now + r.randint(3, 27) * DAY + 14 * HOUR, name)
        for sid, name, kind, team in r.sample(OTHER_DUTIES, r.randint(2, 3)):
            name = self._nm(name)
            did = self.duty(f"d-{self._sid(sid)}", name, kind)
            team_people = [p for p in self.stayers if self.person(p)["team"] == team] or self.stayers
            self.owner(did, r.choice(team_people))
            for k in range(3):
                self.event(did, self.now + (r.randint(2, 12) + 21 * k) * DAY + 10 * HOUR, name)
        if len(self.gone) > 1:  # owned by someone long gone: broken already, not because of the leaver
            sid, name, kind = r.choice(ORPHANS)
            name = self._nm(name)
            did = self.duty(f"d-{self._sid(sid)}", name, kind)
            self.owner(did, self.gone[-1])
            self.event(did, self.now + r.randint(4, 26) * DAY + 11 * HOUR, name)

    def _oncall(self):
        r = self.rng
        monday = self.now - 4 * DAY + 9 * HOUR
        for i, (sid, label) in enumerate(r.sample(ONCALL, r.randint(1, 2))):
            label = self._nm(label)
            did = self.duty(f"d-oncall-{self._sid(sid)}", f"{label} on-call", "oncall")
            rota = f"rota-{self._sid(sid)}"
            self.records.append({"type": "ROUTES_TO", "duty": did, "rota": rota})
            pool = r.sample(self.stayers, 3)
            primaries = [pool[k % 3] for k in range(7)]
            if i == 0:  # the rota still lists someone who already left; their escalation goes to the leaver
                stale = self.gone[0]
                for k in r.sample([1, 2, 3, 4], r.randint(1, 2)):
                    primaries[k] = stale
                self.escalate(stale, self.upstream)
            elif len(self.gone) > 1:  # also stale, but escalates to someone who stays: still covered
                primaries[r.randint(1, 4)] = self.gone[1]
                self.escalate(self.gone[1], self.manager)
            for p in pool:
                if p != self.manager and r.random() < 0.5:
                    self.escalate(p, self.leaver if r.random() < 0.6 else self.manager)
            for k, who in enumerate(primaries):
                start = monday + 7 * k * DAY
                self.records.append({"type": "SHIFT", "rota": rota, "person": who, "from": start,
                                     "to": start + 7 * DAY})
                self.event(did, start, f"{label} on-call handover, week of {_date(start)}")

    def _schedule(self, did, name):
        r = self.rng
        kind = r.choice(["daily", "weekly", "twice-weekly"])
        hour = r.randint(1, 5)
        days = {"daily": list(range(7)), "weekly": [r.randint(0, 6)], "twice-weekly": r.sample(range(7), 2)}[kind]
        for week in range(6):
            for wd in sorted(days):
                at = self.now + (7 * week + wd) * DAY + hour * HOUR
                if at < self.end + 10 * DAY:
                    self.event(did, at, f"{name} run")
        return hour

    def _ghost_jobs(self):
        r = self.rng
        self.ghosts = []
        lname = self.person(self.leaver)["name"]
        for sid, name, team in self.jobs[:r.randint(1, 2)]:
            sid, name = self._sid(sid), self._nm(name)
            did = self.duty(f"d-job-{sid}", name, "job")
            self.ghosts.append((did, name))
            hour = self._schedule(did, name)
            reruns = []
            for d in sorted(r.sample(range(1, 22), r.randint(4, 7)), reverse=True):
                at = self.now - d * DAY + hour * HOUR
                if r.random() < 0.5 or not reruns:
                    self.joblogs.append({"job": did, "actor": "scheduler", "at": at, "status": "failed"})
                    rr = {"job": did, "actor": self.leaver, "at": at + r.randint(3, 6) * HOUR, "status": "succeeded"}
                    self.joblogs.append(rr)
                    reruns.append(rr)
                else:
                    self.joblogs.append({"job": did, "actor": "scheduler", "at": at, "status": "succeeded"})
            last = max(reruns, key=lambda x: x["at"])
            text = r.choice(T_GHOST_MSG).format(job=sid, cause=r.choice(CAUSES), hh=f"{hour:02d}")
            m = self.msg(self._ch(r.choice(["#platform", "#ops", CHANNELS[team]])), self.leaver, last["at"] + 20 * 60_000,
                         text)
            self.true_beliefs.append({
                "person": self.leaver, "duty": did, "duty_name": name, "kind": "job",
                "claim": r.choice(T_GHOST_CLAIM).format(who=lname, job=name), "events": [],
                "sources": [m, r.choice(reruns)]})

    def _owned_jobs(self):
        r = self.rng
        for sid, name, team in self.jobs[2:2 + r.randint(1, 2)]:
            sid, name = self._sid(sid), self._nm(name)
            did = self.duty(f"d-job-{sid}", name, "job")
            team_people = [p for p in self.stayers if self.person(p)["team"] == team] or self.stayers
            self.owner(did, r.choice(team_people))
            hour = self._schedule(did, name)
            for d in range(1, 8):
                self.joblogs.append({"job": did, "actor": "scheduler", "at": self.now - d * DAY + hour * HOUR,
                                     "status": "failed" if r.random() < 0.1 else "succeeded"})

    def _promises(self):
        r = self.rng
        lname = self.person(self.leaver)["name"]
        self.customers = r.sample(CUSTOMERS, 4)
        for cust, (pslug, what) in zip(self.customers, r.sample(PROMISES, r.randint(1, 2))):
            what = what.format(idp=self.idp)
            day = r.choice([d for d in range(3, 28) if (d % 7) not in (1, 2)])  # now is a Friday: skip weekends
            due = self.now + day * DAY + 17 * HOUR
            date = _date(due)
            contact = self.spare_names.pop()
            m = self.msg(self._ch(r.choice([f"#cust-{_slug(cust)}", "#support-escalations"])), self.leaver,
                         self.past(4, 20),
                         r.choice(T_PROMISE_MSG).format(contact=contact, contact_first=contact.split()[0],
                                                        cust=cust, what=what, date=date))
            t = {"author": f"{contact} ({cust})", "at": m["at"] + r.randint(2, 40) * HOUR,
                 "text": r.choice(T_PROMISE_TICKET).format(leaver_first=lname.split()[0], what=what, date=date)}
            self.tickets.append(t)
            events = [{"at": due, "label": f"Due to {cust}: {what}"}]
            if due - 3 * DAY >= self.now:
                events.append({"at": due - 3 * DAY, "label": f"Check in with {cust} on {what}"})
            self.true_beliefs.append({
                "person": self.leaver, "duty": f"promise-{self._sid(_slug(cust))}-{pslug}",
                "duty_name": self._nm(f"{what[0].upper()}{what[1:]} for {cust}"), "kind": "promise",
                "claim": r.choice(T_PROMISE_CLAIM).format(who=lname, cust=cust, what=what, date=date),
                "events": sorted(events, key=lambda e: e["at"]), "sources": [m, t]})

    def _noise(self):
        r = self.rng
        lname = self.person(self.leaver)["name"]
        lfirst = lname.split()[0]
        # 1. false transfer, one chat line only
        gdid, gname = self.ghosts[0]
        s = r.choice(self.stayers)
        author = r.choice([p for p in self.stayers if p != s])
        m = self.msg(self._ch(r.choice(["#platform", "#ops"])), author, self.past(1, 10),
                     r.choice(T_TRANSFER).format(s=self.first(s), job=gdid.replace("d-job-", "")))
        self.noise_beliefs.append({"person": s, "duty": gdid, "duty_name": gname, "kind": "job",
                                   "claim": f"{self.person(s)['name']} owns {gname} now", "events": [],
                                   "sources": [m]})
        # 2. two chat lines, a single source type
        v = r.choice(VENDORS)
        a, b = r.sample(self.stayers, 2)
        q, ans = r.choice(T_VENDOR)
        at = self.past(2, 15)
        m1 = self.msg(self._ch("#general"), a, at, q.format(l=lfirst, v=v))
        m2 = self.msg(self._ch("#general"), b, at + 7 * 60_000, ans.format(l=lfirst, v=v))
        self.noise_beliefs.append({
            "person": self.leaver, "duty": f"vendor-{self._sid(_slug(v))}", "duty_name": self._nm(f"{v} contract renewal"),
            "kind": "vendor", "claim": f"{lname} handles the {v} contract renewal",
            "events": [{"at": self.now + r.randint(5, 25) * DAY + 12 * HOUR, "label": f"{v} contract renews"}],
            "sources": [m1, m2]})
        # 3. cites a ticket that does not exist
        cust = self.customers[-1]
        m3 = self.msg(self._ch("#support-escalations"), self.leaver, self.past(3, 12),
                      f"{cust} asked about the uptime report again, I'll look")
        self.noise_beliefs.append({
            "person": self.leaver, "duty": f"report-{self._sid(_slug(cust))}-uptime",
            "duty_name": self._nm(f"Uptime report for {cust}"),
            "kind": "promise", "claim": f"{lname} sends {cust} a monthly uptime report",
            "events": [{"at": self.now + r.randint(5, 25) * DAY + 9 * HOUR, "label": f"Uptime report to {cust}"}],
            "sources": [m3, "missing-ticket"]})
        # 4. sometimes: a single job log row
        owned_logs = [j for j in self.joblogs if j["actor"] == "scheduler"]
        if r.random() < 0.5 and owned_logs:
            j = r.choice(owned_logs)
            self.noise_beliefs.append({
                "person": s, "duty": j["job"], "duty_name": next(d["name"] for d in self.duties if d["id"] == j["job"]),
                "kind": "job", "claim": f"{self.person(s)['name']} watches this job's runs", "events": [],
                "sources": [j]})

    def _chatter(self):
        r = self.rng
        for _ in range(r.randint(8, 14)):
            p = r.choice(self.stayers + [self.leaver])
            self.msg(self._ch(CHANNELS[self.person(p)["team"]]), p, self.past(1, 40),
                     r.choice(T_FILLER).format(svc=r.choice(self.services), ver=f"v{r.randint(2, 9)}.{r.randint(0, 30)}"))
        for g in self.gone:
            self.msg(self._ch("#general"), g, self.person(g)["left_at"] - 5 * HOUR,
                     r.choice(["Last day today. Thanks everyone, it's been a blast", "Signing off for good - "
                               "thanks all, handover notes are in the wiki (mostly)"]))
        if self.unit is None:  # only the real leaver announces a last day; a unit's anchor stays
            self._last_day_notes(r)
        for text in r.sample(T_FILLER_TICKET, r.randint(2, 3)):
            self.tickets.append({"author": f"{self.spare_names.pop()} ({r.choice(self.customers)})",
                                 "at": self.past(1, 30), "text": text})

    def _last_day_notes(self, r):
        lname = self.person(self.leaver)["name"]
        self.msg("#general", self.manager, self.now - r.randint(5, 9) * DAY + 10 * HOUR,
                 f"Heads up: {lname}'s last day is {_date(self.now)}. Grab them before then for anything they run.")
        self.msg(CHANNELS[self.person(self.leaver)["team"]], self.leaver, self.now - 2 * DAY + 15 * HOUR,
                 "writing up handover notes this week, shout if there's something I should cover")

    def _capability(self, n_records):
        """Who could take on which recorded duty (CAN records) and how many extra duties each person can absorb
        (people[].capacity). Drawn from its own RNG stream and numbered after every other record, so adding it
        leaves every other byte of the world, every id and every belief exactly as before. CAN is a skill, not
        ownership: nothing in the rehearsal reads it. Some duties have nobody else who knows how to do them."""
        r = random.Random(f"halden-capability-{self.seed}")
        for p in self.people:
            p["capacity"] = r.choice([1, 1, 2, 2, 3])
        can = []
        for d in sorted(self.duties, key=lambda x: x["id"]):
            k = r.choice([0, 1, 1, 2, 2, 3])
            pool = self.duty_pool.get(d["id"], self.stayers)
            for pid in sorted(r.sample(pool, min(k, len(pool)))):
                can.append({"type": "CAN", "duty": d["id"], "person": pid})
        for i, c in enumerate(can, n_records + 1):
            c["id"] = f"rec-{i:04d}"
        self.records += can

    # output --------------------------------------------------------------------------------------------------
    def _finish(self):
        def number(items, prefix, key):
            items.sort(key=key)
            for i, x in enumerate(items, 1):
                x["id"] = f"{prefix}-{i:04d}"

        self.records += list(self.esc.values())
        number(self.records, "rec", lambda x: json.dumps(x, sort_keys=True))
        number(self.events, "ev", lambda x: (x["at"], x["duty"], x["label"]))
        number(self.messages, "msg", lambda x: (x["at"], x["channel"], x["author"], x["text"]))
        number(self.joblogs, "log", lambda x: (x["at"], x["job"], x["actor"], x["status"]))
        number(self.tickets, "tkt", lambda x: (x["at"], x["author"], x["text"]))
        missing = f"tkt-{len(self.tickets) + self.rng.randint(10, 99):04d}"

        def resolve(beliefs):
            out = []
            for b in beliefs:
                b = dict(b, sources=[missing if s == "missing-ticket" else s["id"] for s in b["sources"]])
                out.append(b)
            return out

        self._capability(len(self.records))
        true_b, noise_b = resolve(self.true_beliefs), resolve(self.noise_beliefs)
        ids = [f"blf-{i:02d}" for i in range(1, len(true_b) + len(noise_b) + 1)]
        self.rng.shuffle(ids)
        for b, i in zip(true_b + noise_b, ids):
            b["id"] = i
        world = {
            "seed": self.seed, "label": "FIXTURE", "company": "Halden", "now": self.now, "day_ms": DAY,
            "window_days": WINDOW_DAYS, "leaver": self.leaver, "leave_at": self.leave_at,
            "people": sorted(self.people, key=lambda p: p["id"]),
            "duties": sorted(self.duties, key=lambda d: d["id"]),
            "records": self.records, "events": self.events, "messages": self.messages,
            "joblogs": self.joblogs, "tickets": self.tickets,
        }
        key = {"leaver": self.leaver,
               "true_beliefs": sorted(true_b, key=lambda b: b["id"]),
               "noise_beliefs": sorted(noise_b, key=lambda b: b["id"])}
        return world, key


UNITS = ["Nordics", "Iberia", "DACH", "Benelux", "UK", "India", "LatAm", "ANZ", "Japan", "Canada", "Gulf", "Africa",
         "Baltics", "Korea", "France", "Italy", "Poland", "Brazil", "Mexico", "Singapore"]


class _Unit(_Halden):
    """One extra business unit of a scaled Halden. Same planting code as the core; its 'leaver' slot holds a local
    anchor who stays (so nothing of the unit breaks on its own), and its ids, duty names and channels carry the
    unit's name so nothing merges across units. Never used at scale 1."""

    def __init__(self, parent, k, taken):
        super().__init__(parent.seed)
        self.rng = random.Random(f"halden-unit-{parent.seed}-{k}")
        label = UNITS[k - 1] if k <= len(UNITS) else f"Unit {k}"
        self.unit, self.unit_label = _slug(label), label
        self.taken, self.global_leaver = taken, parent.leaver

    def _names(self, k):
        r, out = self.rng, []
        while len(out) < k:
            name = f"{r.choice(FIRST)} {r.choice(LAST)}"
            for _ in range(30):
                if name not in self.taken:
                    break
                name = f"{r.choice(FIRST)} {chr(65 + r.randrange(26))}. {r.choice(LAST)}"
            if name in self.taken:
                continue
            self.taken.add(name)
            out.append(name)
        return out

    def build_unit(self):
        r = self.rng
        self._people()
        if r.random() < 0.5:
            self.upstream = self.global_leaver  # this unit's stale on-call shift escalates to the real leaver
        self.services = r.sample(SERVICES, len(SERVICES))
        self.jobs = r.sample(JOBS, len(JOBS))
        self._certs()
        self._shared_and_other_duties()
        self._oncall()
        self._ghost_jobs()
        self._owned_jobs()
        self._promises()
        self._noise()
        self._chatter()


def build(seed, scale=1):
    """Return (world, answer_key) for a seed and scale. Pure: same arguments, same bytes. Scale 1 is the default
    company; scale N adds business units (see _Halden._grow) and records `scale` and `units` in the world."""
    h = _Halden(seed)
    world, key = h.build(scale)
    if scale > 1:
        world["scale"] = scale
        world["units"] = [{"id": u.unit, "name": u.unit_label, "anchor": u.leaver} for u in h.units]
    return world, key


def run(seed, out, scale=1):
    if scale < 1 or scale > 64:
        raise SystemExit("baton generate: --scale must be between 1 and 64")
    world, key = build(seed, scale)
    d = Path(out)
    d.mkdir(parents=True, exist_ok=True)
    (d / "world.json").write_text(json.dumps(world, sort_keys=True, indent=1) + "\n", encoding="utf-8", newline="\n")
    (d / "answer_key.json").write_text(json.dumps(key, sort_keys=True, indent=1) + "\n", encoding="utf-8", newline="\n")
    name = f"halden_{seed}" if scale == 1 else f"halden_{seed}_x{scale}"
    return {"seed": seed, "scale": scale, "out": str(d), "leaver": world["leaver"], "graph": name,
            "counts": {k: len(world[k]) for k in ("people", "duties", "records", "events", "messages", "joblogs",
                                                  "tickets")},
            "beliefs": len(key["true_beliefs"]) + len(key["noise_beliefs"])}
