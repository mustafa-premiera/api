"""DynamoDB access for the activity log."""
from boto3.dynamodb.conditions import Key


class ActivityRepository:
    def __init__(self, table):
        self.table = table

    def list(self, user_id, limit=50):
        resp = self.table.query(
            KeyConditionExpression=Key("userId").eq(user_id),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [{k: v for k, v in i.items() if k not in ("userId", "ttl")} for i in resp["Items"]]

    def record(self, item):
        self.table.put_item(Item=item)
