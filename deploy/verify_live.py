"""Run in authenticated AWS CloudShell; keep credentials/cookies in memory only."""
import http.cookiejar
import json
import os
import re
import urllib.error
import urllib.request
import boto3

BASE = os.environ.get("BATON_VERIFY_BASE", "https://baton-workspace.vercel.app")
if not re.fullmatch(r"https://baton-workspace(?:-[a-z0-9]+-risehackathonsupport-3406)?\.vercel\.app", BASE):
    raise ValueError("Verification credentials may only be sent to the Baton frontend")


def main():
    jar = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def call(path, body=None, method=None, origin=BASE, expected=200):
        request = urllib.request.Request(BASE + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type":"application/json", "Origin":origin},
            method=method or ("POST" if body is not None else "GET"))
        try:
            with client.open(request, timeout=170) as response:
                status, raw = response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read().decode()
        if status != expected:
            raise RuntimeError(path + " returned " + str(status) + ": " + raw[:600])
        return json.loads(raw) if raw[:1] in ("{", "[") else raw
    assert call("/api/health")["ok"]
    call("/api/public/tasks", {"item_id":"invalid","title":"anonymous"}, expected=401)
    call("/api/auth/login", {"token":"invalid"}, origin="https://hostile.example", expected=403)
    config = boto3.client("lambda",region_name="ap-south-1").get_function_configuration(FunctionName="baton-workspace")
    token = config["Environment"]["Variables"]["BATON_OPERATOR_TOKEN"]
    call("/api/auth/login", {"token":token})
    assert call("/api/auth/status")["authenticated"]
    status = call("/api/public/status")
    imported = call("/api/public/import", {}) if not status["imported"] else {"already_imported":True}
    workspace = call("/api/public/workspace")
    assert workspace["items"] and workspace["edges"] and workspace["sources"]
    print(json.dumps({"stage":"import_graph", "import":imported, "counts":workspace["counts"], "edges":len(workspace["edges"]), "fingerprint":workspace["fingerprint"]}), flush=True)
    item = workspace["items"][0]
    source = call("/api/public/sources/" + item["source_ids"][0])
    assert source["payload"] and source["sha256"]
    run = call("/api/public/inference", {"item_id":item["id"],"question":"Summarize the change and identify concrete verification steps using only cited source evidence."}, expected=202)
    print(json.dumps({"stage":"inference", **{k:run.get(k) for k in ("id","status","provider","model","provider_response_id","input_tokens","output_tokens","error")}}), flush=True)
    if run["status"] != "succeeded":
        raise RuntimeError("Live inference failed; remaining inference-dependent checks were not passed")
    assert set(run["output"]["source_ids"]).issubset(set(item["source_ids"]))
    task = call("/api/public/tasks", {"item_id":item["id"],"title":"Review the cited change and verify the Groq triage against its source", "run_id":run["id"]}, expected=201)
    call("/api/public/tasks/" + task["id"], {"status":"done"}, method="PATCH")
    reloaded = call("/api/public/workspace")
    assert any(t["id"] == task["id"] and t["status"] == "done" for t in reloaded["tasks"])
    assert reloaded["counts"].get("AIClaim",0) and reloaded["counts"].get("InferenceRun",0) and reloaded["counts"].get("LocalTask",0)
    csv = call("/api/public/tasks.csv")
    assert task["id"] in csv
    call("/api/auth/logout", {})
    assert not call("/api/auth/status")["authenticated"]
    print(json.dumps({"stage":"complete", "live_flow_passed":True, "task_id":task["id"], "counts":reloaded["counts"], "receipt":run["provider_response_id"]}))


if __name__ == "__main__":
    main()
