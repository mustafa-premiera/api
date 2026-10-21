output "todos_table_name" {
  value = aws_dynamodb_table.todos.name
}

output "activity_table_name" {
  value = aws_dynamodb_table.activity.name
}
