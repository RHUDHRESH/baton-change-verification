"""Update existing Lambda from a reviewed exact Git commit in CloudShell.

Preserves Linux runtime wheels and all existing environment variables. Fetches
only this app's source using the explicitly approved server credential. Does not
create IAM permissions, cloud services, subscriptions, or a runner execution.
"""
import base64
import hashlib
import io
import json
import re
import sys
import urllib.request
import zipfile

import boto3


def main(commit):
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("An exact reviewed source commit is required")
    client = boto3.client("lambda", region_name="ap-south-1")
    current = client.get_function(FunctionName="baton-workspace")
    token = current["Configuration"]["Environment"]["Variables"]["BATON_GITHUB_TOKEN"]
    with urllib.request.urlopen(current["Code"]["Location"], timeout=45) as response:
        old = zipfile.ZipFile(io.BytesIO(response.read(49 * 1024 * 1024)))
    request = urllib.request.Request("https://api.github.com/repos/RHUDHRESH/baton-graph-workspace/zipball/" + commit,
        headers={"Authorization": "Bearer " + token, "User-Agent": "Baton-Reviewed-Deploy"})
    with urllib.request.urlopen(request, timeout=45) as response:
        source = zipfile.ZipFile(io.BytesIO(response.read(20 * 1024 * 1024)))
    replacements = {}
    for name in source.namelist():
        if name.endswith("/"):
            continue
        relative = name.split("/", 1)[1]
        if relative.startswith(("baton/", "server/", "web/", "fixtures/", "third_party/")):
            replacements[relative] = source.read(name)
        elif relative.startswith("docs/evidence/"):
            replacements["web/evidence/" + relative.removeprefix("docs/evidence/")] = source.read(name)
    if not all(name in replacements for name in ("server/autonomous_workflow.py", "server/autonomous_publication.py", "web/workflows.js")):
        raise ValueError("Reviewed commit does not include the complete workflow")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for row in old.infolist():
            if row.filename not in replacements:
                archive.writestr(row.filename, old.read(row.filename))
        for name, content in replacements.items():
            archive.writestr(name, content)
    raw = output.getvalue()
    result = client.update_function_code(FunctionName="baton-workspace", ZipFile=raw)
    client.get_waiter("function_updated_v2").wait(FunctionName="baton-workspace")
    expected = base64.b64encode(hashlib.sha256(raw).digest()).decode()
    actual = client.get_function_configuration(FunctionName="baton-workspace")
    if actual["CodeSha256"] != expected or result["CodeSha256"] != expected:
        raise RuntimeError("Lambda code digest readback mismatch")
    print(json.dumps({"source_commit": commit, "code_sha256": expected, "revision": actual["RevisionId"],
                      "environment_preserved": True, "new_resources": False, "bytes": len(raw)}))


if __name__ == "__main__":
    main(sys.argv[1])
