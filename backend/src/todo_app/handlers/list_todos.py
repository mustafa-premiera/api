import os

import boto3
from aws_lambda_powertools import Tracer

from todo_app.http import bad_request, json_response, user_id
from todo_app.models import ValidationError, to_public
from todo_app.repository import TodoRepository

tracer = Tracer()
repo = TodoRepository(boto3.resource("dynamodb").Table(os.environ["TODOS_TABLE"]))


@tracer.capture_lambda_handler
def handler(event, context):
    status = (event.get("queryStringParameters") or {}).get("status")
    if status is not None and status not in ("OPEN", "DONE"):
        return bad_request(ValidationError("status must be OPEN or DONE"))
    items = repo.list(user_id(event), status)
    return json_response(200, {"items": [to_public(i) for i in items]})
