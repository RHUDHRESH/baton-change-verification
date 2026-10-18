"""Business context for the explicitly fictional Halden demonstration."""
WORK = [
    {"id":"promise-oaktree-clinics-csv-encoding", "title":"Get Oaktree’s launch export ready", "category":"Customer commitment", "impact":"Oaktree Clinics is waiting for the CSV encoding fix before its launch can move ahead.", "short":"Oaktree’s launch depends on a promised CSV fix.", "customer":"Oaktree Clinics", "priority":"Customer blocked", "icon":"↗"},
    {"id":"d-job-warehouse-snapshot", "title":"Keep the daily warehouse backup running", "category":"Daily operations", "impact":"Hana reruns failed snapshots by hand. The job has no recorded owner, so that recovery work could stop when she leaves.", "short":"Daily snapshots still depend on Hana’s manual recovery.", "priority":"Hidden responsibility", "icon":"◫"},
    {"id":"d-oncall-edge", "title":"Make sure an edge incident reaches someone", "category":"Incident response", "impact":"The on-call rota looks staffed, but its escalation path still ends at Hana. The next incident needs an active person at the end of that path.", "short":"A staffed rota still escalates to the person leaving.", "priority":"Escalation gap", "icon":"↳"},
    {"id":"d-tls-ledger", "title":"Renew the ledger connection certificate", "category":"Service continuity", "impact":"The ledger endpoint needs its certificate renewed. Hana is the recorded owner; a successor needs to take over the scheduled renewal.", "short":"Keep the ledger endpoint’s scheduled renewal covered.", "priority":"Recorded duty", "icon":"⌁"},
    {"id":"d-tls-status", "title":"Keep the status site certificate current", "category":"Service continuity", "impact":"Customers need a reachable status site. The certificate’s upcoming renewal is still assigned to Hana.", "short":"The status site renewal needs a new owner.", "priority":"Recorded duty", "icon":"⌁"},
    {"id":"d-codesign-windows", "title":"Keep Windows releases signed", "category":"Release operations", "impact":"The code-signing certificate has scheduled renewal work. Passing ownership keeps that work covered after Hana’s departure.", "short":"Hand over the certificate behind Windows releases.", "priority":"Recorded duty", "icon":"✓"},
]


def context(directory):
    import json
    from baton.load import _sources
    world = json.loads((directory / "world.json").read_text())
    return {"name":"Halden", "fictional":True, "description":"Reporting software for operations teams.",
            "about":"Halden helps operations teams move business data into dependable reports and customer exports. This workspace follows the people, recurring jobs and customer commitments behind that work.",
            "scenario":"Hana’s departure", "work":WORK, "sources":_sources(world), "records":world["records"],
            "events":world["events"], "messages":world["messages"], "tickets":world["tickets"]}


def tasks(data):
    import json
    from baton.commit import _safe_read
    if not data.exists():
        return []
    return json.loads(_safe_read(data, ".company/tasks.json") or "[]")


def save_tasks(data, rows):
    import json
    from baton.commit import _safe_write
    _safe_write(data, ".company/tasks.json", json.dumps(rows, indent=2))
