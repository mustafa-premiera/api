data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

locals {
  iam_roles = ["read", "write", "stream"]
}

resource "aws_iam_role" "lambda" {
  for_each           = toset(local.iam_roles)
  name               = "${var.project}-lambda-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "basic" {
  for_each   = aws_iam_role.lambda
  role       = each.value.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "xray" {
  for_each   = aws_iam_role.lambda
  role       = each.value.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

data "aws_iam_policy_document" "read" {
  statement {
    actions = ["dynamodb:Query", "dynamodb:GetItem"]
    resources = [
      aws_dynamodb_table.todos.arn,
      "${aws_dynamodb_table.todos.arn}/index/*",
    ]
  }
  statement {
    actions   = ["dynamodb:Query"]
    resources = [aws_dynamodb_table.activity.arn]
  }
}

resource "aws_iam_role_policy" "read" {
  name   = "dynamodb-read"
  role   = aws_iam_role.lambda["read"].id
  policy = data.aws_iam_policy_document.read.json
}

data "aws_iam_policy_document" "write" {
  statement {
    actions = [
      "dynamodb:Query",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
    ]
    resources = [aws_dynamodb_table.todos.arn]
  }
}

resource "aws_iam_role_policy" "write" {
  name   = "dynamodb-write"
  role   = aws_iam_role.lambda["write"].id
  policy = data.aws_iam_policy_document.write.json
}

data "aws_iam_policy_document" "stream" {
  statement {
    actions = [
      "dynamodb:GetRecords",
      "dynamodb:GetShardIterator",
      "dynamodb:DescribeStream",
      "dynamodb:ListStreams",
    ]
    resources = [aws_dynamodb_table.todos.stream_arn]
  }
  statement {
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.activity.arn]
  }
}

resource "aws_iam_role_policy" "stream" {
  name   = "stream-and-activity"
  role   = aws_iam_role.lambda["stream"].id
  policy = data.aws_iam_policy_document.stream.json
}
