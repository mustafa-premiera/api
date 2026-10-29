import os
from datetime import datetime, timezone

import boto3
from aws_lambda_powertools import Logger, Tracer

from todo_app.activity import ActivityRepository
from todo_app.stream import to_activity

tracer = Tracer()
logger = Logger()
repo = ActivityRepository(boto3.resource("dynamodb").Table(os.environ["ACTIVITY_TABLE"]))


@tracer.capture_lambda_handler
def handler(event, context):
    failures = []
    for record in event.get("Records", []):
        try:
            item = to_activity(record, datetime.now(timezone.utc))
            if item is not None:
                repo.record(item)
        except Exception:
            logger.exception("failed to process stream record")
            # Streams checkpoints on SequenceNumber; a record without one cannot be reported, only logged.
            seq = (record.get("dynamodb") or {}).get("SequenceNumber")
            if seq is not None:
                failures.append({"itemIdentifier": seq})
    return {"batchItemFailures": failures}
