import os

import boto3
from aws_lambda_powertools import Tracer

from todo_app.activity import ActivityRepository
from todo_app.http import json_response, user_id

tracer = Tracer()
repo = ActivityRepository(boto3.resource("dynamodb").Table(os.environ["ACTIVITY_TABLE"]))


@tracer.capture_lambda_handler
def handler(event, context):
    return json_response(200, {"items": repo.list(user_id(event))})
