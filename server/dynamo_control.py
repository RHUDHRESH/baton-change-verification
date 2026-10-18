"""Minimal control-store operations backed by a provisioned DynamoDB table.

Sessions, short leases and counters only. Never stores provider API keys.
"""
import time
import uuid
from contextlib import contextmanager


class DynamoControl:
    def __init__(self, name):
        import boto3
        self.table=boto3.resource("dynamodb").Table(name)

    def get(self,key):
        row=self.table.get_item(Key={"pk":key},ConsistentRead=True).get("Item")
        if not row or (row.get("expires",0) and int(row["expires"])<=int(time.time())):
            return None
        return str(row["value"])

    def set(self,key,value,nx=False,ex=None):
        row={"pk":key,"value":str(value)}
        if ex:
            row["expires"]=int(time.time())+int(ex)
        args={"Item":row}
        if nx:
            args.update(ConditionExpression="attribute_not_exists(pk) OR expires <= :now",ExpressionAttributeValues={":now":int(time.time())})
        try:
            self.table.put_item(**args)
            return True
        except self.table.meta.client.exceptions.ConditionalCheckFailedException:
            return False

    def incr(self,key):
        try:
            self.table.update_item(Key={"pk":key},UpdateExpression="SET #v=:one REMOVE expires",
                ConditionExpression="expires <= :now",ExpressionAttributeNames={"#v":"value"},
                ExpressionAttributeValues={":one":1,":now":int(time.time())})
            return 1
        except self.table.meta.client.exceptions.ConditionalCheckFailedException:
            pass
        result=self.table.update_item(Key={"pk":key},UpdateExpression="ADD #v :one",
            ExpressionAttributeNames={"#v":"value"},ExpressionAttributeValues={":one":1},ReturnValues="UPDATED_NEW")
        return int(result["Attributes"]["value"])

    def expire(self,key,seconds):
        self.table.update_item(Key={"pk":key},UpdateExpression="SET expires=:at",ExpressionAttributeValues={":at":int(time.time())+seconds})

    def delete(self,*keys):
        for key in keys:
            self.table.delete_item(Key={"pk":key})

    def ping(self):
        self.table.get_item(Key={"pk":"health"})
        return True

    @contextmanager
    def lock(self,key,timeout=30,blocking_timeout=5,**_):
        token=uuid.uuid4().hex
        deadline=time.monotonic()+blocking_timeout
        while not self.set("lease:"+key,token,nx=True,ex=timeout):
            if time.monotonic()>=deadline:
                raise RuntimeError("Workspace operation is busy; retry shortly")
            time.sleep(.1)
        try:
            yield
        finally:
            try:
                self.table.delete_item(Key={"pk":"lease:"+key},ConditionExpression="#v=:token",
                    ExpressionAttributeNames={"#v":"value"},ExpressionAttributeValues={":token":token})
            except self.table.meta.client.exceptions.ConditionalCheckFailedException:
                pass
