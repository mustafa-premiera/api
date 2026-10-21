locals {
  api_routes = {
    list_todos    = { resource = "todos", http_method = "GET" }
    create_todo   = { resource = "todos", http_method = "POST" }
    get_todo      = { resource = "todo_id", http_method = "GET" }
    update_todo   = { resource = "todo_id", http_method = "PUT" }
    delete_todo   = { resource = "todo_id", http_method = "DELETE" }
    list_activity = { resource = "activity", http_method = "GET" }
  }

  # Cache keys must include the Authorization header so cached responses are per user.
  api_request_parameters = {
    list_todos = {
      "method.request.header.Authorization" = true
      "method.request.querystring.status"   = false
      "method.request.querystring.v"        = false
    }
    get_todo = {
      "method.request.header.Authorization" = true
      "method.request.path.id"              = true
      "method.request.querystring.v"        = false
    }
    create_todo   = {}
    update_todo   = { "method.request.path.id" = true }
    delete_todo   = { "method.request.path.id" = true }
    list_activity = {}
  }

  api_resource_paths = {
    todos    = "/todos"
    todo_id  = "/todos/*"
    activity = "/activity"
  }

  api_cached_routes = toset(["list_todos", "get_todo"])
}

resource "aws_api_gateway_rest_api" "main" {
  name = var.project

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "todos" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "todos"
}

resource "aws_api_gateway_resource" "todo_id" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.todos.id
  path_part   = "{id}"
}

resource "aws_api_gateway_resource" "activity" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "activity"
}

locals {
  api_resource_ids = {
    todos    = aws_api_gateway_resource.todos.id
    todo_id  = aws_api_gateway_resource.todo_id.id
    activity = aws_api_gateway_resource.activity.id
  }
}

resource "aws_api_gateway_authorizer" "cognito" {
  name            = "${var.project}-cognito"
  rest_api_id     = aws_api_gateway_rest_api.main.id
  type            = "COGNITO_USER_POOLS"
  provider_arns   = [aws_cognito_user_pool.main.arn]
  identity_source = "method.request.header.Authorization"
}

resource "aws_api_gateway_method" "api" {
  for_each = local.api_routes

  rest_api_id          = aws_api_gateway_rest_api.main.id
  resource_id          = local.api_resource_ids[each.value.resource]
  http_method          = each.value.http_method
  authorization        = "COGNITO_USER_POOLS"
  authorizer_id        = aws_api_gateway_authorizer.cognito.id
  authorization_scopes = []
  api_key_required     = true
  request_parameters   = local.api_request_parameters[each.key]
}

resource "aws_api_gateway_integration" "api" {
  for_each = local.api_routes

  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = local.api_resource_ids[each.value.resource]
  http_method             = aws_api_gateway_method.api[each.key].http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.api[each.key].invoke_arn

  cache_key_parameters = contains(local.api_cached_routes, each.key) ? keys(local.api_request_parameters[each.key]) : null
}

resource "aws_lambda_permission" "apigw" {
  for_each = local.api_routes

  statement_id  = "AllowAPIGatewayInvoke-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api[each.key].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/${each.value.http_method}${local.api_resource_paths[each.value.resource]}"
}

resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  triggers = {
    redeployment = sha1(jsonencode([
      [for r in [aws_api_gateway_resource.todos, aws_api_gateway_resource.todo_id, aws_api_gateway_resource.activity] : r.id],
      [aws_api_gateway_authorizer.cognito.id, aws_api_gateway_authorizer.cognito.type, aws_api_gateway_authorizer.cognito.identity_source, aws_api_gateway_authorizer.cognito.provider_arns],
      { for k, m in aws_api_gateway_method.api : k => [m.id, m.http_method, m.authorization, m.authorizer_id, m.authorization_scopes, m.api_key_required, local.api_request_parameters[k]] },
      { for k, i in aws_api_gateway_integration.api : k => [i.id, i.type, i.integration_http_method, aws_lambda_function.api[k].invoke_arn, contains(local.api_cached_routes, k) ? keys(local.api_request_parameters[k]) : [], i.timeout_milliseconds, i.passthrough_behavior, i.content_handling, i.credentials, i.request_templates] },
      # Catch-all: any edit to this file redeploys the stage.
      filesha1("${path.module}/apigateway.tf"),
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [aws_api_gateway_integration.api, aws_lambda_permission.apigw]
}

resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/aws/apigateway/${var.project}-access"
  retention_in_days = 14
}

data "aws_iam_policy_document" "apigw_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apigw_cloudwatch" {
  name               = "${var.project}-apigw-cloudwatch"
  assume_role_policy = data.aws_iam_policy_document.apigw_assume.json
}

resource "aws_iam_role_policy_attachment" "apigw_cloudwatch" {
  role       = aws_iam_role.apigw_cloudwatch.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

resource "aws_api_gateway_account" "main" {
  cloudwatch_role_arn = aws_iam_role.apigw_cloudwatch.arn

  depends_on = [aws_iam_role_policy_attachment.apigw_cloudwatch]
}

resource "aws_api_gateway_stage" "api" {
  rest_api_id           = aws_api_gateway_rest_api.main.id
  deployment_id         = aws_api_gateway_deployment.main.id
  stage_name            = "api"
  cache_cluster_enabled = var.enable_api_cache
  cache_cluster_size    = var.enable_api_cache ? "0.5" : null
  xray_tracing_enabled  = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId          = "$context.requestId"
      ip                 = "$context.identity.sourceIp"
      requestTime        = "$context.requestTime"
      httpMethod         = "$context.httpMethod"
      resourcePath       = "$context.resourcePath"
      status             = "$context.status"
      responseLength     = "$context.responseLength"
      integrationLatency = "$context.integrationLatency"
      xrayTraceId        = "$context.xrayTraceId"
      user               = "$context.authorizer.claims.sub"
    })
  }

  depends_on = [aws_api_gateway_account.main]
}

resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  stage_name  = aws_api_gateway_stage.api.stage_name
  method_path = "*/*"

  settings {
    metrics_enabled        = true
    logging_level          = "ERROR"
    throttling_rate_limit  = 20
    throttling_burst_limit = 40
    caching_enabled        = false
  }
}

resource "aws_api_gateway_method_settings" "cached" {
  for_each = {
    "todos/GET"      = true
    "todos/{id}/GET" = true
  }

  rest_api_id = aws_api_gateway_rest_api.main.id
  stage_name  = aws_api_gateway_stage.api.stage_name
  method_path = each.key

  settings {
    metrics_enabled                            = true
    logging_level                              = "ERROR"
    throttling_rate_limit                      = 20
    throttling_burst_limit                     = 40
    caching_enabled                            = var.enable_api_cache
    cache_ttl_in_seconds                       = var.api_cache_ttl_seconds
    require_authorization_for_cache_control    = true
    unauthorized_cache_control_header_strategy = "SUCCEED_WITH_RESPONSE_HEADER"
  }

  depends_on = [aws_api_gateway_method_settings.all]
}

resource "aws_api_gateway_api_key" "cloudfront" {
  name    = "${var.project}-cloudfront"
  enabled = true
}

resource "aws_api_gateway_usage_plan" "main" {
  name = "${var.project}-cloudfront"

  api_stages {
    api_id = aws_api_gateway_rest_api.main.id
    stage  = aws_api_gateway_stage.api.stage_name
  }

  throttle_settings {
    rate_limit  = 20
    burst_limit = 40
  }

  quota_settings {
    limit  = 10000
    period = "DAY"
  }
}

resource "aws_api_gateway_usage_plan_key" "cloudfront" {
  key_id        = aws_api_gateway_api_key.cloudfront.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.main.id
}
