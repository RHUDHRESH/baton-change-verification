"""Explicit CloudShell test: publish one approved task and verify replay safety.

This performs a real external write. Run only for an approved target/task.
Credentials stay in memory; output contains public artifact receipts only.
"""
import argparse
import http.cookiejar
import json
import re
import urllib.request

import boto3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["jira", "slack"])
    parser.add_argument("task_id")
    parser.add_argument("--base", default="https://baton-workspace.vercel.app")
    args = parser.parse_args()
    if not re.fullmatch(r"https://baton-workspace(?:-[a-z0-9]+-risehackathonsupport-3406)?\.vercel\.app", args.base):
        parser.error("Verification credentials may only be sent to the Baton frontend")
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(path, body=None):
        request = urllib.request.Request(args.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "Origin": args.base})
        with client.open(request, timeout=110) as response:
            return json.load(response)

    variables = boto3.client("lambda", region_name="ap-south-1").get_function_configuration(
        FunctionName="baton-workspace")["Environment"]["Variables"]
    call("/api/auth/login", {"token": variables["BATON_OPERATOR_TOKEN"]})
    del variables
    path = "/api/public/tasks/" + args.task_id + "/publish"
    first = call(path, {"target": args.target})
    print(json.dumps({"stage": "provider_readback", **{key: first.get(key) for key in
        ("id", "target", "task_id", "status", "url", "remote_id", "graph_linked", "message")}}), flush=True)
    assert first["status"] == "verified" and first["graph_linked"], "External action remains unverified"
    repeated = call(path, {"target": args.target})
    assert repeated["remote_id"] == first["remote_id"] and repeated["status"] == "verified"
    workspace = call("/api/public/workspace")
    assert any(edge["data"]["kind"] == "PUBLISHED_AS" and
        edge["data"]["source"] == args.task_id and edge["data"]["target"] == first["id"]
        for edge in workspace["edges"]), "External artifact missing from queried graph"
    print(json.dumps({"stage": "complete", "target": args.target,
        "same_artifact_on_repeat": True, "graph_readback": True}), flush=True)


if __name__ == "__main__":
    main()
