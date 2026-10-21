import os

import boto3
from aws_lambda_powertools import Tracer

from todo_app.http import json_response, not_found, user_id
from todo_app.repository import TodoRepository

tracer = Tracer()
repo = TodoRepository(boto3.resource("dynamodb").Table(os.environ["TODOS_TABLE"]))


@tracer.capture_lambda_handler
def handler(event, context):
    if not repo.delete(user_id(event), event["pathParameters"]["id"]):
        return not_found()
    return json_response(204, None)
