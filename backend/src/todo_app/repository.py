"""DynamoDB access for to-do items."""
import uuid
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from .models import status_due


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TodoRepository:
    def __init__(self, table):
        self.table = table

    def list(self, user_id, status=None):
        kwargs = {}
        if status is None:
            cond = Key("userId").eq(user_id)
        else:
            cond = Key("userId").eq(user_id) & Key("statusDue").begins_with(f"{status}#")
            kwargs["IndexName"] = "StatusDueIndex"
        items = []
        while True:
            resp = self.table.query(KeyConditionExpression=cond, **kwargs)
            items.extend(resp["Items"])
            if "LastEvaluatedKey" not in resp:
                return items
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    def get(self, user_id, todo_id):
        return self.table.get_item(Key={"userId": user_id, "todoId": todo_id}).get("Item")

    def create(self, user_id, fields):
        now = _now()
        item = {
            "userId": user_id,
            "todoId": str(uuid.uuid4()),
            "title": fields["title"],
            "description": fields["description"],
            "status": fields["status"],
            "createdAt": now,
            "updatedAt": now,
            "statusDue": status_due(fields["status"], fields.get("dueDate")),
        }
        if fields.get("dueDate") is not None:
            item["dueDate"] = fields["dueDate"]
        self.table.put_item(Item=item)
        return item

    def update(self, user_id, todo_id, fields):
        current = self.get(user_id, todo_id)
        if current is None:
            return None
        status = fields.get("status", current["status"])
        due = fields["dueDate"] if "dueDate" in fields else current.get("dueDate")

        names = {}
        values = {":statusDue": status_due(status, due), ":updatedAt": _now()}
        sets = ["statusDue = :statusDue", "updatedAt = :updatedAt"]
        removes = []
        for key, value in fields.items():
            if key == "dueDate" and value is None:
                removes.append("#dueDate")
                names["#dueDate"] = "dueDate"
                continue
            names[f"#{key}"] = key
            values[f":{key}"] = value
            sets.append(f"#{key} = :{key}")
        expr = "SET " + ", ".join(sets)
        if removes:
            expr += " REMOVE " + ", ".join(removes)
        kwargs = {"ExpressionAttributeNames": names} if names else {}
        try:
            resp = self.table.update_item(
                Key={"userId": user_id, "todoId": todo_id},
                UpdateExpression=expr,
                ConditionExpression="attribute_exists(todoId)",
                ExpressionAttributeValues=values,
                ReturnValues="ALL_NEW",
                **kwargs,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise
        return resp["Attributes"]

    def delete(self, user_id, todo_id):
        try:
            self.table.delete_item(
                Key={"userId": user_id, "todoId": todo_id},
                ConditionExpression="attribute_exists(todoId)",
                ReturnValues="ALL_OLD",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True
