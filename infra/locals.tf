locals {
  todos_table_name    = "${var.project}-todos"
  activity_table_name = "${var.project}-activity"

  powertools_layer_arn = "arn:aws:lambda:us-east-1:017000801446:layer:AWSLambdaPowertoolsPythonV3-python312-x86_64:30"

  api_functions = {
    list_todos    = { handler = "todo_app.handlers.list_todos.handler", role = "read" }
    get_todo      = { handler = "todo_app.handlers.get_todo.handler", role = "read" }
    list_activity = { handler = "todo_app.handlers.list_activity.handler", role = "read" }
    create_todo   = { handler = "todo_app.handlers.create_todo.handler", role = "write" }
    update_todo   = { handler = "todo_app.handlers.update_todo.handler", role = "write" }
    delete_todo   = { handler = "todo_app.handlers.delete_todo.handler", role = "write" }
  }

  lambda_env = {
    TODOS_TABLE             = local.todos_table_name
    ACTIVITY_TABLE          = local.activity_table_name
    POWERTOOLS_SERVICE_NAME = var.project
  }
}
