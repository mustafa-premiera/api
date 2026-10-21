output "todos_table_name" {
  value = aws_dynamodb_table.todos.name
}

output "activity_table_name" {
  value = aws_dynamodb_table.activity.name
}

output "user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "web_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "smoke_client_id" {
  value = aws_cognito_user_pool_client.smoke.id
}

output "hosted_ui_domain" {
  value = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.region}.amazoncognito.com"
}

output "api_invoke_url" {
  value = aws_api_gateway_stage.api.invoke_url
}

output "api_key_value" {
  value     = aws_api_gateway_api_key.cloudfront.value
  sensitive = true
}
