"""Private control Redis, separate from managed graph permissions."""
import os


def connect(port):
    if os.environ.get("BATON_CONTROL_DYNAMODB_TABLE"):
        from .dynamo_control import DynamoControl
        return DynamoControl(os.environ["BATON_CONTROL_DYNAMODB_TABLE"])
    if os.environ.get("BATON_CONTROL_REDIS_URL"):
        import redis
        return redis.Redis.from_url(os.environ["BATON_CONTROL_REDIS_URL"], decode_responses=True, socket_connect_timeout=3)
    from baton.graph import connect as graph_connect
    return graph_connect(port).connection
