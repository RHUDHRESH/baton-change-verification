"""Deploy only Lambda, a provisioned control table and a minimal execution role.

Run in authenticated CloudShell. No EC2, EBS, NAT, ALB, API Gateway, S3 bucket,
ECR repository, provisioned concurrency, custom KMS key or paid model plan.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

REGION="ap-south-1"
NAME="baton-workspace"
TABLE="baton-workspace-control"
ROLE="baton-workspace-lambda-exec"


def clients():
    return boto3.client("lambda",region_name=REGION),boto3.client("dynamodb",region_name=REGION),boto3.client("iam")


def prepare(archive):
    lam,ddb,iam=clients()
    account=boto3.client("sts").get_caller_identity()["Account"]
    table_arn=f"arn:aws:dynamodb:{REGION}:{account}:table/{TABLE}"
    existing=ddb.list_tables()["TableNames"]
    other_capacity=[ddb.describe_table(TableName=name)["Table"]["ProvisionedThroughput"] for name in existing if name!=TABLE]
    if sum(int(t["ReadCapacityUnits"]) for t in other_capacity)>15 or sum(int(t["WriteCapacityUnits"]) for t in other_capacity)>15:
        raise RuntimeError("Other table capacity leaves insufficient ongoing free allowance for this deployment")
    if TABLE not in existing:
        ddb.create_table(TableName=TABLE,KeySchema=[{"AttributeName":"pk","KeyType":"HASH"}],
            AttributeDefinitions=[{"AttributeName":"pk","AttributeType":"S"}],BillingMode="PROVISIONED",
            ProvisionedThroughput={"ReadCapacityUnits":10,"WriteCapacityUnits":10},TableClass="STANDARD",
            Tags=[{"Key":"Application","Value":"Baton"}])
        ddb.get_waiter("table_exists").wait(TableName=TABLE)
    if ddb.describe_time_to_live(TableName=TABLE)["TimeToLiveDescription"]["TimeToLiveStatus"] == "DISABLED":
        ddb.update_time_to_live(TableName=TABLE,TimeToLiveSpecification={"Enabled":True,"AttributeName":"expires"})
    trust={"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}
    try:
        role=iam.get_role(RoleName=ROLE)["Role"]
        if role.get("Description")!="Baton free allowance workspace execution role":
            raise RuntimeError("Existing role is not this app's managed role; no changes made")
    except iam.exceptions.NoSuchEntityException:
        role=iam.create_role(RoleName=ROLE,Description="Baton free allowance workspace execution role",AssumeRolePolicyDocument=json.dumps(trust))["Role"]
    policy={"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["dynamodb:GetItem","dynamodb:PutItem","dynamodb:UpdateItem","dynamodb:DeleteItem","dynamodb:DescribeTable"],"Resource":table_arn}]}
    iam.put_role_policy(RoleName=ROLE,PolicyName="BatonControlTableOnly",PolicyDocument=json.dumps(policy))
    # Generated operator credential stays in encrypted Lambda env, never stdout.
    variables={"BATON_DATA":"/tmp/baton","BATON_CONTROL_DYNAMODB_TABLE":TABLE,"BATON_INFERENCE_MODE":"request",
               "BATON_CLOUD_STATE_GRAPH":"baton_workspace_state","BATON_OPERATOR_TOKEN":secrets.token_urlsafe(36),
               "BATON_ALLOWED_HOSTS":"localhost","BATON_OFFLINE":"1","GROQ_MODEL":"openai/gpt-oss-20b"}
    code=Path(archive).read_bytes()
    try:
        configuration=lam.get_function_configuration(FunctionName=NAME)
    except lam.exceptions.ResourceNotFoundException:
        for attempt in range(12):
            try:
                lam.create_function(FunctionName=NAME,Runtime="python3.12",Role=role["Arn"],Handler="server.lambda_entry.handler",
                    Code={"ZipFile":code},Timeout=180,MemorySize=256,Publish=False,Environment={"Variables":variables},
                    Architectures=["x86_64"],EphemeralStorage={"Size":512},Tags={"Application":"Baton"})
                break
            except ClientError as error:
                if error.response["Error"]["Code"]!="InvalidParameterValueException" or attempt==11:
                    raise
                time.sleep(5)
    else:
        lam.update_function_code(FunctionName=NAME,ZipFile=code)
    lam.get_waiter("function_updated_v2").wait(FunctionName=NAME)
    try:
        url=lam.get_function_url_config(FunctionName=NAME)["FunctionUrl"]
    except lam.exceptions.ResourceNotFoundException:
        url=lam.create_function_url_config(FunctionName=NAME,AuthType="NONE")["FunctionUrl"]
    configuration=lam.get_function_configuration(FunctionName=NAME)
    variables=configuration["Environment"]["Variables"]
    variables["BATON_ALLOWED_HOSTS"]=urlparse(url).hostname+",localhost,127.0.0.1"
    lam.update_function_configuration(FunctionName=NAME,Environment={"Variables":variables})
    lam.get_waiter("function_updated_v2").wait(FunctionName=NAME)
    try:
        lam.put_function_concurrency(FunctionName=NAME,ReservedConcurrentExecutions=2)
        cap=2
    except lam.exceptions.InvalidParameterValueException:
        cap=lam.get_account_settings()["AccountLimit"]["ConcurrentExecutions"]
        if cap>10:
            raise RuntimeError("Cannot enforce the intended small concurrency bound; do not publish")
    print(json.dumps({"prepared":True,"url":url,"public_access_changed":False,"control_table":TABLE,"capacity":"10 RCU / 10 WCU, no autoscaling","maximum_concurrency":cap},indent=2))


def configure():
    lam,_,_=clients()
    variables=lam.get_function_configuration(FunctionName=NAME)["Environment"]["Variables"]
    variables["FALKORDB_HOST"]=input("FalkorDB Cloud endpoint hostname: ").strip()
    variables["FALKORDB_PORT"]=str(int(input("FalkorDB Cloud port: ").strip()))
    variables["FALKORDB_USERNAME"]=input("FalkorDB username [falkordb]: ").strip() or "falkordb"
    variables["FALKORDB_TLS"]="0" # explicitly selected Free instance has no TLS
    variables["FALKORDB_PASSWORD"]=getpass.getpass("FalkorDB password (hidden): ")
    variables["GROQ_API_KEY"]=getpass.getpass("Groq Free key (hidden): ")
    if not variables["FALKORDB_PASSWORD"] or not variables["GROQ_API_KEY"]:
        raise RuntimeError("Both provider secrets are required")
    lam.update_function_configuration(FunctionName=NAME,Environment={"Variables":variables})
    lam.get_waiter("function_updated_v2").wait(FunctionName=NAME)
    print("Provider secrets configured in Lambda. No secret values printed.")


def publish():
    lam,_,_=clients()
    config=lam.get_function_configuration(FunctionName=NAME)
    variables=config["Environment"]["Variables"]
    if not all(variables.get(k) for k in ("FALKORDB_HOST","FALKORDB_PORT","FALKORDB_PASSWORD","GROQ_API_KEY")):
        raise RuntimeError("Configure provider credentials before enabling the public URL")
    for sid,action,extra in [("BatonPublicFunctionURL","lambda:InvokeFunctionUrl",{"FunctionUrlAuthType":"NONE"}),
                             ("BatonOnlyViaFunctionURL","lambda:InvokeFunction",{"InvokedViaFunctionUrl":True})]:
        try:
            lam.add_permission(FunctionName=NAME,StatementId=sid,Action=action,Principal="*",**extra)
        except lam.exceptions.ResourceConflictException:
            pass
    print(json.dumps({"url":lam.get_function_url_config(FunctionName=NAME)["FunctionUrl"],"published":True},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["prepare","configure","publish"])
    parser.add_argument("--archive",default="Baton_lambda.zip")
    args=parser.parse_args()
    if args.action=="prepare":
        prepare(args.archive)
    elif args.action=="configure":
        configure()
    else:
        publish()
