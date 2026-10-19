"""Select the approved Groq Free goal model without changing other settings.

Run in the existing authenticated AWS CloudShell. Credentials and existing
environment values remain in memory; output contains only the model and revision.
"""
import json

import boto3


def main():
    client = boto3.client("lambda", region_name="ap-south-1")
    before = client.get_function_configuration(FunctionName="baton-workspace")
    variables = dict(before.get("Environment", {}).get("Variables", {}))
    expected = {**variables, "BATON_GOAL_MODEL": "openai/gpt-oss-120b"}
    client.update_function_configuration(
        FunctionName="baton-workspace", RevisionId=before["RevisionId"],
        Environment={"Variables": expected})
    client.get_waiter("function_updated_v2").wait(FunctionName="baton-workspace")
    after = client.get_function_configuration(FunctionName="baton-workspace")
    if after.get("Environment", {}).get("Variables") != expected:
        raise RuntimeError("Goal model configuration was not independently confirmed")
    print(json.dumps({"goal_model": expected["BATON_GOAL_MODEL"],
                      "revision": after["RevisionId"],
                      "other_environment_preserved": True,
                      "new_resources": False}))


if __name__ == "__main__":
    main()
