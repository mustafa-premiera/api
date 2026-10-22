data "archive_file" "lambda" {
  type             = "zip"
  source_dir       = "${path.module}/../backend/src"
  output_path      = "${path.module}/build/lambda.zip"
  output_file_mode = "0644"
  excludes         = ["__pycache__", "**/__pycache__", "**/*.pyc"]
}

resource "aws_cloudwatch_log_group" "api" {
  for_each          = local.api_functions
  name              = "/aws/lambda/${var.project}-${each.key}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "stream_processor" {
  name              = "/aws/lambda/${var.project}-stream_processor"
  retention_in_days = 14
}

resource "aws_lambda_function" "api" {
  for_each = local.api_functions

  function_name    = "${var.project}-${each.key}"
  role             = aws_iam_role.lambda[each.value.role].arn
  runtime          = "python3.12"
  handler          = each.value.handler
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  memory_size      = 256
  timeout          = 10
  layers           = [local.powertools_layer_arn]

  environment {
    variables = local.lambda_env
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [
    aws_cloudwatch_log_group.api,
    aws_iam_role_policy_attachment.basic,
    aws_iam_role_policy_attachment.xray,
    aws_iam_role_policy.read,
    aws_iam_role_policy.write,
  ]
}

resource "aws_lambda_function" "stream_processor" {
  function_name    = "${var.project}-stream_processor"
  role             = aws_iam_role.lambda["stream"].arn
  runtime          = "python3.12"
  handler          = "todo_app.handlers.stream_processor.handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  memory_size      = 256
  timeout          = 10
  layers           = [local.powertools_layer_arn]

  environment {
    variables = local.lambda_env
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [
    aws_cloudwatch_log_group.stream_processor,
    aws_iam_role_policy_attachment.basic,
    aws_iam_role_policy_attachment.xray,
    aws_iam_role_policy.stream,
  ]
}

resource "aws_lambda_event_source_mapping" "todos_stream" {
  event_source_arn        = aws_dynamodb_table.todos.stream_arn
  function_name           = aws_lambda_function.stream_processor.arn
  starting_position       = "LATEST"
  batch_size              = 10
  maximum_retry_attempts  = 3
  function_response_types = ["ReportBatchItemFailures"]
}
