resource "aws_dynamodb_table" "todos" {
  name         = local.todos_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "todoId"

  attribute {
    name = "userId"
    type = "S"
  }
  attribute {
    name = "todoId"
    type = "S"
  }
  attribute {
    name = "statusDue"
    type = "S"
  }
  attribute {
    name = "dueDate"
    type = "S"
  }

  global_secondary_index {
    name            = "StatusDueIndex"
    hash_key        = "userId"
    range_key       = "statusDue"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "DueDateIndex"
    hash_key        = "dueDate"
    range_key       = "userId"
    projection_type = "KEYS_ONLY"
  }

  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  point_in_time_recovery {
    enabled = true
  }
}

resource "aws_dynamodb_table" "activity" {
  name         = local.activity_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "sk"

  attribute {
    name = "userId"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}
