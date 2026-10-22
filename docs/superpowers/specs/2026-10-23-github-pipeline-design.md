# GitHub Actions CI/CD Pipeline — Design

Adds CI/CD to the Manara Project 3 repo `mustafa-premiera/api` (branch `github-pipeline-workflow`). The existing app is described in `2026-10-21-serverless-todo-design.md`.

## Intent

- **For the Manara reviewers:** show a professional delivery setup they can read and follow.
- **For the user:** ship changes without running Terraform on their Mac.

So the pipeline has to really work, and it has to be easy to follow.

## Goals (user)

- **Every pull request to `main`:**
  - run the backend tests
  - check Terraform formatting and configuration
  - build the frontend
  - show what Terraform would change
- **Every merge (push) to `main`:** deploy straight away with no manual approval. That means `terraform apply`, then a frontend build, a sync to S3, and a CloudFront invalidation.

## Non-goals

- Multiple environments (dev/stage/prod). There is one account and one stack.
- Running pipelines for pull requests from forks with AWS access. Fork PRs get the checks only, never AWS credentials.
- Running the end-to-end smoke test in CI. That script doesn't exist yet; it's Task 8 of the main plan.

## Anti-goals

- **No long-lived AWS keys** in GitHub, whether as secrets, variables or files.
- **Never deploy to any account other than `609417966933`.** The provider's `allowed_account_ids` guard stays.
- **Pull requests must not be able to change AWS.** The PR role is read-only, apart from the state lock file.
- **No secrets in logs or PR comments.** The API key is a sensitive Terraform output and must not be printed.

## Constraints

- AWS account `609417966933`, region `us-east-1`. The local CLI profile is `manara-free` (SSO).
- The repo is public, and the default branch is `main`.
- Terraform state is currently **local** in `infra/terraform.tfstate`, with 81 resources. CI can't reach it there, so it has to move to S3.
- **CloudFront is blocked** for this account until AWS Support verifies it. The deploy job will fail at `aws_cloudfront_distribution.main` until then. That's expected and documented, not hidden.
- WAF and the API cache are currently switched off (`enable_waf = false`, `enable_api_cache = false` in the local, gitignored `terraform.tfvars`) to save credits. CI has to honour the same settings.

## Decided with the user

- CI and CD both run on GitHub Actions.
- A merge to `main` deploys immediately.
- **While CloudFront is blocked, deploys are allowed to fail (option A).** There is no temporary CloudFront switch and no special-casing. The deploy job fails at the CloudFront resource, and the frontend step doesn't run. The README explains this in one line. Once AWS verifies the account, the next merge succeeds with no code change.

## Claude's calls (the user can override)

1. **Remote state:**
   - Bucket: S3 `manara-todo-tfstate-609417966933`, with versioning, SSE-S3 encryption and all public access blocked.
   - Key: `infra/terraform.tfstate`.
   - Locking: Terraform's native S3 lock (`use_lockfile = true`), so no DynamoDB lock table is needed. This raises the `infra/` requirement to Terraform >= 1.10.
   - Migrate the existing local state once from the Mac with `terraform init -migrate-state`, keeping a backup copy of the local state file outside the repo.
2. **Bootstrap stack `bootstrap/`** (Terraform, local state, gitignored). The user runs it once from the Mac. It creates:
   - the state bucket
   - the GitHub OIDC identity provider (`token.actions.githubusercontent.com`, audience `sts.amazonaws.com`)
   - role **`manara-todo-gha-plan`**: trust limited to `repo:mustafa-premiera/api:pull_request`. Permissions are AWS-managed `ReadOnlyAccess`, plus Get/Put/Delete on `infra/terraform.tfstate.tflock` and Get/List on the state object in the state bucket.
   - role **`manara-todo-gha-deploy`**: trust limited to `repo:mustafa-premiera/api:ref:refs/heads/main`. Permissions are `AdministratorAccess`, because Terraform creates IAM roles, WAF, CloudFront and the rest, and a hand-built least-privilege policy for all of that would be large and fragile. The safety comes from the trust policy (main branch of this repo only) plus the provider's account guard. The README states this trade-off.
3. **Provider changes:**
   - `var.aws_profile` default becomes `null`. Local runs set `AWS_PROFILE=manara-free`; CI uses the OIDC credentials from the environment.
   - The backend block uses no profile, so it uses the same credential chain.
   - `scripts/deploy_frontend.sh` must stop forcing `AWS_PROFILE=manara-free` when running in GitHub Actions (`GITHUB_ACTIONS=true`).
4. **Workflows:**
   - `.github/workflows/ci.yml`, on `pull_request` to `main`, with three parallel jobs:
     - `backend-tests`: Python 3.12, `pip install -r backend/requirements-dev.txt`, then `pytest -q -W error`.
     - `frontend-build`: Node 22, `npm ci`, `npm run build`.
     - `terraform`: `fmt -check -recursive`, `init -backend=false`, `validate`. For PRs from the same repo only, it then assumes the plan role, runs `init` and `plan -lock=false -no-color`, and posts or updates one sticky PR comment with the plan summary line and the plan in a collapsed block. Sensitive values are already redacted by Terraform.
   - `.github/workflows/deploy.yml`, on `push` to `main` and `workflow_dispatch`:
     - It runs the same three checks first.
     - Then a `deploy` job assumes the deploy role, runs `terraform init` and `terraform apply -auto-approve`, then runs `scripts/deploy_frontend.sh`.
     - It uses `concurrency: deploy-main` with `cancel-in-progress: false`.
   - Shared checks should not be copy-pasted. Use a reusable workflow (`.github/workflows/checks.yml`, `on: workflow_call`) called by both workflows.
   - Pin actions to major versions: `actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`, `hashicorp/setup-terraform@v3` (Terraform 1.15.x), `aws-actions/configure-aws-credentials@v4`.
5. **Settings as GitHub repository variables** (not secrets, since none of them is secret). The user sets them in the browser:
   - `AWS_PLAN_ROLE_ARN`, `AWS_DEPLOY_ROLE_ARN`
   - `ALERT_EMAIL`
   - `ENABLE_WAF`, `ENABLE_API_CACHE` (start as `false` while CloudFront is blocked)

   Workflows pass them as `TF_VAR_alert_email`, `TF_VAR_enable_waf` and `TF_VAR_enable_api_cache`.
6. **Docs:**
   - The README gets a "CI/CD" section: the flow, the two roles and their trust, the variables, and how to bootstrap.
   - The architecture diagram gets a small "GitHub Actions → (OIDC) → AWS" addition.
   - Status badges for both workflows go at the top of the README.

7. **The PR plan never locks.** It runs with `-lock=false`, so the plan role gets **no** Put/Delete on the lock file, only Get/List on the state bucket on top of `ReadOnlyAccess`. This supersedes the lock-file grant in call 2. As a result, a PR plan can never block a deploy.
8. **Cut-over order (the controller does this from the Mac before this branch merges):**
   1. Apply `bootstrap/`.
   2. Back up the local state outside the repo.
   3. Add the S3 backend and bump `infra/` to Terraform `>= 1.10`.
   4. Run `terraform init -migrate-state`.
   5. Run `terraform plan` and confirm it shows only the expected drift.
   6. Have the user set the repo variables.
   7. Merge.

   **Guard:** before `init`, the deploy job checks that `s3://manara-todo-tfstate-609417966933/infra/terraform.tfstate` exists and fails with a clear message if it doesn't. A misconfigured run can then never try to recreate the stack from empty state.
9. **Bool variables default to `false` in the workflow** (`${{ vars.ENABLE_WAF || 'false' }}`). An unset variable can then neither break `terraform apply` nor turn billing on.
10. **Deterministic Lambda zip:** `archive_file` with `output_file_mode = "0644"`, so Mac and Linux produce identical hashes.
11. **The README recommends branch protection on `main`** (require the checks to pass) as a manual GitHub setting. It isn't automated.
12. **No GitHub Environment.** The deploy role's trust is pinned to `refs/heads/main` of this repo.
13. **The PR plan reflects only repo variables plus defaults.** Local `terraform.tfvars` overrides are invisible to CI, and the README says so.

## Left to the builder

- Exact step names, caching (`setup-python` pip cache, `setup-node` npm cache, `.terraform` plugin cache) and job timeouts.
- How the PR comment is posted, either `actions/github-script` or a well-known sticky-comment action pinned by major version.
- Any cosmetic Lambda updates caused by zip differences between the Mac and Linux runners. `archive_file` output can differ by platform. Make the zip deterministic if it's cheap to do; otherwise document it.
