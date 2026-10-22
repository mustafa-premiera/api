# Bootstrap stack

Creates the Terraform state bucket, the GitHub OIDC provider and the CI plan/deploy IAM roles.
Run once: `AWS_PROFILE=manara-free terraform -chdir=bootstrap init && AWS_PROFILE=manara-free terraform -chdir=bootstrap apply`.
State for this stack is local (`bootstrap/terraform.tfstate`) and gitignored. Back up `bootstrap/terraform.tfstate`; losing it means re-importing the roles and bucket.
Account 609417966933 only; never the management account.
