import os

import boto3
from aws_lambda_powertools import Tracer

from todo_app.http import bad_request, json_response, parse_json_body, user_id
from todo_app.models import ValidationError, parse_create, to_public
from todo_app.repository import TodoRepository

tracer = Tracer()
repo = TodoRepository(boto3.resource("dynamodb").Table(os.environ["TODOS_TABLE"]))


@tracer.capture_lambda_handler
def handler(event, context):
    try:
        fields = parse_create(parse_json_body(event))
    except ValidationError as e:
        return bad_request(e)
    item = repo.create(user_id(event), fields)
    return json_response(201, to_public(item))
