"""AWS Lambda Function URL adapter, with a conservative monthly request guard."""
import os
import time

os.environ.setdefault("BATON_DATA","/tmp/baton")
os.environ.setdefault("BATON_CLOUD_STATE_GRAPH","baton_workspace_state")
os.environ.setdefault("BATON_INFERENCE_MODE","request")

from mangum import Mangum
from .app import app
from .control import connect

asgi=Mangum(app,lifespan="off")


def handler(event,context):
    # Counts all app requests, including static assets. Rejections still incur
    # small Lambda invocations; this is a workload guard, not an AWS billing cap.
    db=connect(int(os.environ.get("FALKORDB_PORT","6379")))
    key="lambda:requests:"+time.strftime("%Y-%m",time.gmtime())
    used=db.incr(key)
    if used==1:
        db.expire(key,65*86400)
    if used>5000:
        return {"statusCode":429,"headers":{"content-type":"application/json","cache-control":"no-store"},
                "body":'{"detail":"The 5,000-request monthly demo allowance is exhausted."}'}
    return asgi(event,context)
