# GitHub Actions CI/CD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every PR to `main` runs the tests, the Terraform checks, the frontend build, and a read-only plan posted as a comment. Every push to `main` deploys with `terraform apply` and then the frontend deploy, using GitHub OIDC roles and S3 remote state.

**Architecture:**
- A one-time `bootstrap/` Terraform stack (local state) creates the S3 state bucket, the GitHub OIDC provider and two IAM roles (plan, deploy).
- `infra/` moves to the S3 backend with native locking.
- Three workflows: a reusable `checks.yml` called by `ci.yml` (PR) and by `deploy.yml` (push to main).

**Tech Stack:** GitHub Actions, Terraform 1.15 (hashicorp/aws ~> 6.0), AWS IAM OIDC, actionlint.

**Spec:** `docs/superpowers/specs/2026-10-23-github-pipeline-design.md` (read it first; its "Claude's calls" 1–13 are binding).

## Global Constraints

- AWS account `609417966933`, region `us-east-1`. Local commands use `AWS_PROFILE=manara-free`. Run `aws sts get-caller-identity` and confirm `609417966933` before every apply or state operation.
- State bucket `manara-todo-tfstate-609417966933`, key `infra/terraform.tfstate`, `use_lockfile = true`. `infra/` requires Terraform `>= 1.10`.
- Role names `manara-todo-gha-plan` and `manara-todo-gha-deploy`, with these OIDC trust subjects:
  - plan: `repo:mustafa-premiera/api:pull_request`
  - deploy: `repo:mustafa-premiera/api:ref:refs/heads/main`
  - Both require audience `sts.amazonaws.com`.
- Plan role permissions: `ReadOnlyAccess` plus `s3:GetObject`/`s3:ListBucket` on the state bucket. No lock-file writes, because PR plans run with `-lock=false`.
- Deploy role permissions: `AdministratorAccess`.
- GitHub repository variables: `AWS_PLAN_ROLE_ARN`, `AWS_DEPLOY_ROLE_ARN`, `ALERT_EMAIL`, `ENABLE_WAF`, `ENABLE_API_CACHE`. The bool variables default to `'false'` in the workflows.
- Action versions:
  - `actions/checkout@v4`
  - `actions/setup-python@v5` (3.12)
  - `actions/setup-node@v4` (22)
  - `hashicorp/setup-terraform@v3` (`terraform_version: 1.15.4`, `terraform_wrapper: false`)
  - `aws-actions/configure-aws-credentials@v4`
  - `actions/github-script@v7`
- No AWS keys anywhere. Never print `api_key_value` or any sensitive output.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Work on branch `github-pipeline-workflow`. Don't push; the controller and the user handle pushes in Task 5.

## Review Focus

1. **Empty remote state.** The deploy job must fail before `terraform init` if `s3://manara-todo-tfstate-609417966933/infra/terraform.tfstate` is missing, and must never plan to recreate the stack. Pinned in Task 3 (guard step) and verified in Task 5.
2. **Fork PRs.** They have no OIDC token, so the plan step must be skipped (with condition `github.event.pull_request.head.repo.full_name == github.repository`). The checks still run. Pinned in Task 3.
3. **Unset bool variables.** `TF_VAR_enable_waf` and `TF_VAR_enable_api_cache` must come through as `false`, not `""`. Pinned in Task 3.
4. **Secrets leaking into the PR comment or the logs.** The plan comment must contain only `terraform show -no-color` output, which redacts sensitive values. Nothing may echo outputs other than `frontend_bucket`, `distribution_id` and `app_url`. Pinned in Task 3 (reviewed) and Task 5 (inspect the real comment).
5. **Mac and Linux zip drift.** After the state migration, a local `plan` must show no Lambda changes once the deterministic zip has been applied. Pinned in Task 2.

---

### Task 1: Bootstrap stack (state bucket, OIDC provider, roles)

**Files:**
- Create: `bootstrap/versions.tf`, `bootstrap/main.tf`, `bootstrap/outputs.tf`, `bootstrap/README.md` (5 lines: purpose, `AWS_PROFILE=manara-free terraform -chdir=bootstrap init && … apply`, and that state is local and gitignored)

**Interfaces:**
- Produces outputs `state_bucket`, `plan_role_arn`, `deploy_role_arn`.

- [ ] **Step 1: Write the stack.**
  - Provider: region `us-east-1`, `allowed_account_ids = ["609417966933"]`, default tag `Project=manara-todo`. No `profile` argument; local runs use the `AWS_PROFILE` environment variable.
  - Bucket: versioning enabled, SSE-S3 (AES256), a full public access block, `force_destroy = false`, and `lifecycle { prevent_destroy = true }`.
  - `aws_iam_openid_connect_provider` for `https://token.actions.githubusercontent.com`, with `client_id_list = ["sts.amazonaws.com"]`. AWS no longer validates thumbprints for this provider; supply the provider's documented thumbprint anyway if the resource requires one.
  - The two roles, with trust and permissions per Global Constraints. Trust conditions: `StringEquals` on `token.actions.githubusercontent.com:aud` and `StringEquals` on `token.actions.githubusercontent.com:sub`.
  - `max_session_duration = 3600`.
- [ ] **Step 2: Run `terraform -chdir=bootstrap init`, `terraform fmt -check -recursive` and `validate`.** Expected: the configuration is valid.
- [ ] **Step 3: Confirm the identity is 609417966933, then run `AWS_PROFILE=manara-free terraform -chdir=bootstrap apply -auto-approve`.**
- [ ] **Step 4: Verify:**
  - `aws s3api get-bucket-versioning --bucket manara-todo-tfstate-609417966933` returns `Enabled`.
  - `aws iam get-role --role-name manara-todo-gha-deploy --query Role.AssumeRolePolicyDocument` shows the main-branch `sub`.
  - The same check on the plan role shows the `pull_request` `sub`.
- [ ] **Step 5: Commit** `bootstrap/*.tf` and `bootstrap/README.md`. Check first that `.gitignore` already covers the state files. Use the message `feat(ci): bootstrap stack for Terraform state bucket and GitHub OIDC roles`.

### Task 2: Move `infra/` to the S3 backend and make it CI-ready

**Files:**
- Create: `infra/backend.tf`
- Modify: `infra/versions.tf` (`required_version = ">= 1.10"`), `infra/variables.tf` (`aws_profile` default `null`), `infra/lambda.tf` (`archive_file` gets `output_file_mode = "0644"`), `scripts/deploy_frontend.sh` (set `AWS_PROFILE` to the default only when `GITHUB_ACTIONS` is not `true`)

**Interfaces:**
- Consumes: the bucket from Task 1.
- Produces: the remote state at `s3://manara-todo-tfstate-609417966933/infra/terraform.tfstate`, which Tasks 3 and 5 use.

- [ ] **Step 1: Back up the state.** Run `cp infra/terraform.tfstate "$SCRATCH/infra-terraform.tfstate.pre-migration"` (the controller supplies the scratch path; outside the repo). Record `terraform -chdir=infra state list | wc -l`, which should be 81.
- [ ] **Step 2: Write `backend.tf`** (`backend "s3"` with bucket, key, `region = "us-east-1"`, `use_lockfile = true`, `encrypt = true`) and make the other modifications above.
- [ ] **Step 3: Migrate.** Run `AWS_PROFILE=manara-free terraform -chdir=infra init -migrate-state -force-copy`. Expected: "Successfully configured the backend "s3"". Then:
  - `aws s3 ls s3://manara-todo-tfstate-609417966933/infra/` lists `terraform.tfstate`.
  - `terraform -chdir=infra state list | wc -l` matches Step 1.
- [ ] **Step 4: Settle the zip drift.** Run `AWS_PROFILE=manara-free terraform -chdir=infra plan -no-color`. Expected: changes only to the `aws_lambda_function` entries, from the new zip hash, plus the known pending CloudFront-related creates (the distribution, bucket policy, `config.json`, the Cognito client URLs).
  - Apply only the Lambda changes: `terraform apply -target=aws_lambda_function.api -target=aws_lambda_function.stream_processor -auto-approve`. CloudFront is blocked, so a full apply would fail.
  - Re-run `plan` and confirm no `aws_lambda_function` changes remain.
- [ ] **Step 5: Check the deploy script.** `bash -n scripts/deploy_frontend.sh` passes, and `GITHUB_ACTIONS=true bash -c 'source <(sed -n "1,6p" scripts/deploy_frontend.sh); echo "${AWS_PROFILE:-unset}"'` prints `unset`.
- [ ] **Step 6: Delete the local state.** Remove `infra/terraform.tfstate` and `infra/terraform.tfstate.backup`, which are now superseded. The backup from Step 1 stays in scratch. Then confirm `terraform -chdir=infra state list` still works.
- [ ] **Step 7: Commit** with the message `feat(infra): S3 remote state with native locking; CI-friendly provider and deterministic Lambda zip`.

### Task 3: Workflows

**Files:**
- Create: `.github/workflows/checks.yml`, `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`

**Interfaces:**
- `checks.yml` uses `on: workflow_call` and has three jobs:
  - `backend-tests`: `pip install -r backend/requirements-dev.txt`, then `cd backend && python -m pytest -q -W error`.
  - `frontend-build`: `npm --prefix frontend ci && npm --prefix frontend run build`.
  - `terraform-static`: `terraform fmt -check -recursive` on `infra` and `bootstrap`; `terraform -chdir=infra init -backend=false`; `validate`; the same for `bootstrap`.
- `ci.yml` runs `on: pull_request` with `branches: [main]`. Permissions are `contents: read`, `pull-requests: write` and `id-token: write`. Its jobs:
  - `checks`, which uses `./.github/workflows/checks.yml`.
  - `plan`, which needs `checks` and runs only if `github.event.pull_request.head.repo.full_name == github.repository`. It assumes `vars.AWS_PLAN_ROLE_ARN` and sets the env vars `TF_VAR_alert_email: ${{ vars.ALERT_EMAIL }}`, `TF_VAR_enable_waf: ${{ vars.ENABLE_WAF || 'false' }}` and `TF_VAR_enable_api_cache: ${{ vars.ENABLE_API_CACHE || 'false' }}`. It runs `init`, then `plan -lock=false -no-color -input=false -out=tfplan`, then `terraform show -no-color tfplan > plan.txt`. Finally it creates or updates one PR comment, found by the marker `<!-- terraform-plan -->`, containing the `Plan:` summary line and the full plan in a `<details>` block, truncated to 60,000 characters.
- `deploy.yml` runs `on: push` (`branches: [main]`) and `workflow_dispatch`, with `concurrency: { group: deploy-main, cancel-in-progress: false }`. Its jobs:
  - `checks` (reusable).
  - `deploy`, which needs `checks` and has permissions `id-token: write` and `contents: read`. It assumes `vars.AWS_DEPLOY_ROLE_ARN` and uses the same `TF_VAR_*` env vars. Its steps:
    - The guard: `aws s3api head-object --bucket manara-todo-tfstate-609417966933 --key infra/terraform.tfstate || { echo "::error::Remote state missing — run the bootstrap and state migration first"; exit 1; }`.
    - `terraform init -input=false`.
    - `terraform apply -auto-approve -input=false`.
    - `./scripts/deploy_frontend.sh` (with `GITHUB_ACTIONS` set by the runner).
    - `echo "App: $(terraform -chdir=infra output -raw app_url)" >> $GITHUB_STEP_SUMMARY`.

- [ ] **Step 1: Write the three workflow files.** Use pip and npm caching via the setup actions, and give every job `timeout-minutes` (checks 15, plan 15, deploy 45).
- [ ] **Step 2: Lint them.** Run `brew install actionlint` (and `shellcheck`), then `actionlint`. Expected: no output, exit 0.
- [ ] **Step 3: Run the check commands locally** exactly as written in `checks.yml`: the backend tests, the frontend build, and the Terraform `fmt`/`init -backend=false`/`validate` for both dirs. Expected: all pass. Afterwards run `rm -rf infra/.terraform` only if `init -backend=false` broke the S3 backend config, then re-run `init` with `AWS_PROFILE`.
- [ ] **Step 4: Commit** with the message `feat(ci): GitHub Actions PR checks with Terraform plan comment and main-branch deploy`.

### Task 4: Docs

**Files:**
- Modify: `README.md`, `docs/architecture/diagram.py`, `docs/architecture/architecture.png`

- [ ] **Step 1: Update the README.**
  - Add badges at the top for `ci.yml` and `deploy.yml`, using `https://github.com/mustafa-premiera/api/actions/workflows/<file>/badge.svg`.
  - Add a "CI/CD" section with:
    - the PR flow and the main-branch flow, as a numbered list
    - the two OIDC roles and their trust, plus a one-line rationale for `AdministratorAccess`
    - a table of repo variables
    - the bootstrap and migration commands
    - the branch protection recommendation (Settings → Branches → require the `checks` jobs)
    - the note that the PR plan reflects only repo variables and defaults
    - the one-line note that deploys fail at CloudFront until the AWS account is verified
  - Update the Deploy section: Terraform 1.10+, and `export AWS_PROFILE=...` for local runs.
- [ ] **Step 2: Update the diagram.** Add a small "GitHub Actions" node with an edge labelled "OIDC → deploy role" pointing to the AWS side, plus the S3 state bucket. Re-render, then check the PNG visually.
- [ ] **Step 3: Commit** with the message `docs: CI/CD section, workflow badges, pipeline in architecture diagram`.

### Task 5: Cut-over and live verification (controller and user)

- [ ] **Step 1: The user sets the repository variables** in GitHub (Settings → Secrets and variables → Actions → Variables):
  - `AWS_PLAN_ROLE_ARN` and `AWS_DEPLOY_ROLE_ARN`, from the bootstrap outputs
  - `ALERT_EMAIL`
  - `ENABLE_WAF=false`, `ENABLE_API_CACHE=false`
- [ ] **Step 2: Push the branch and open a PR to `main`.** This needs push access as mustafa-premiera. Expected:
  - the `checks` jobs are green
  - the `plan` job is green
  - the PR shows a `<!-- terraform-plan -->` comment with no sensitive values, and the only planned creates are the known CloudFront-blocked ones
- [ ] **Step 3: Merge.** Expected for the `deploy` run:
  - checks green
  - the guard passes
  - `apply` runs, and then fails at `aws_cloudfront_distribution.main` with "account must be verified". That failure is accepted per the design.
- [ ] **Step 4: Confirm locally** that `terraform -chdir=infra plan` (with the S3 backend) is consistent with CI, meaning no unexpected drift.
