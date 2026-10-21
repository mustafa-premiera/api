provider "aws" {
  profile             = var.aws_profile
  region              = var.region
  allowed_account_ids = ["609417966933"]

  default_tags {
    tags = {
      Project = "manara-todo"
    }
  }
}
