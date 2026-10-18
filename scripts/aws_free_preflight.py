"""Read signup-plan eligibility for the legacy VM option. No mutations.

This does not assess the ongoing Lambda/DynamoDB service allowances used by
deploy/aws_lambda.py, and must not be used as that deployment's eligibility gate.
"""
import json
import subprocess
import sys


def aws(*args):
    p=subprocess.run(["aws",*args,"--region","us-east-1","--no-cli-pager","--output","json"],capture_output=True,text=True,timeout=45)
    if p.returncode:
        raise RuntimeError("AWS preflight could not authenticate or read Free Tier state; no resources were created")
    return json.loads(p.stdout)


def main():
    aws("sts","get-caller-identity")
    state=aws("freetier","get-account-plan-state")
    print(json.dumps(state,indent=2))
    if state.get("accountPlanType")!="FREE":
        raise RuntimeError("Account is not confirmed as a Free plan. Resource creation is blocked under the zero-spend instruction.")
    print("Free plan verified. Review expiration and remaining credits before selecting an eligible instance.")


if __name__=="__main__":
    try:
        main()
    except Exception as error:
        print(str(error),file=sys.stderr)
        sys.exit(1)
