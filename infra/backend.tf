terraform {
  backend "s3" {
    bucket       = "manara-todo-tfstate-609417966933"
    key          = "infra/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
    encrypt      = true
  }
}
