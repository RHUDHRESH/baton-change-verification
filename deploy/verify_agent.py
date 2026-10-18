"""CloudShell verification of MCP discovery, live graph tools and agent action."""
import http.cookiejar
import json
import urllib.request
import boto3

BASE="https://baton-workspace.vercel.app"
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(path,body=None):
    request=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type":"application/json","Origin":BASE})
    with client.open(request,timeout=115) as response:
        return json.load(response)


if __name__=="__main__":
    variables=boto3.client("lambda",region_name="ap-south-1").get_function_configuration(FunctionName="baton-workspace")["Environment"]["Variables"]
    call("/api/auth/login",{"token":variables["BATON_OPERATOR_TOKEN"]})
    del variables
    initialization=call("/api/mcp",{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"live-verifier","version":"1"}}})
    catalog=call("/api/mcp",{"jsonrpc":"2.0","id":2,"method":"tools/list"})
    assert len(catalog["result"]["tools"])>=3
    workspace=call("/api/public/workspace")
    item=next((i for i in workspace["items"] if i["files"]),workspace["items"][0])
    graph=call("/api/mcp",{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"follow_connections","arguments":{"item_id":item["id"]}}})
    assert not graph["result"]["isError"]
    print(json.dumps({"stage":"mcp","protocol":initialization["result"]["protocolVersion"],"catalog":[t["name"] for t in catalog["result"]["tools"]],"selected":item["id"]}),flush=True)
    result=call("/api/public/agent",{"item_id":item["id"]})
    print(json.dumps({"stage":"agent","run_id":result["id"],"status":result["status"],"error":result.get("error"),"tools":[s["request"]["params"]["name"] for s in result["trace"]],"receipts":result["receipts"],"action":result.get("action"),"duration_ms":result["duration_ms"]}),flush=True)
    assert result["status"]=="succeeded", "Live agent did not complete a verified action"
    reloaded=call("/api/public/agent/"+result["id"])
    assert reloaded["action"]["verified"] and reloaded["action"]["task"]["id"]==result["action"]["task"]["id"]
    print(json.dumps({"stage":"complete","agent_flow_passed":True,"task_id":result["action"]["task"]["id"]}),flush=True)
