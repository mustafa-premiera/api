# Serverless To-Do API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A live serverless to-do app with a React SPA, a Cognito-protected REST API, DynamoDB with GSIs and Streams, WAF, X-Ray and API caching, all behind one CloudFront distribution and deployed with Terraform. The public GitHub repo's README carries the architecture diagram.

**Architecture:** One CloudFront distribution, protected by a CLOUDFRONT-scope WAF, serves two things:
- the SPA from a private S3 bucket (OAC), and
- `/api/*` from a regional REST API (stage `api`). CloudFront injects the API key; Cognito ID tokens authorize each call.

The API runs one Python Lambda per operation against the DynamoDB table `manara-todo-todos`. That table's stream drives a Lambda that writes audit items to `manara-todo-activity`.

**Tech Stack:** Terraform 1.15 (hashicorp/aws ~> 6.0, archive, random), Python 3.12 + AWS Lambda Powertools v3 layer, pytest + moto, Vite + React 18 + react-oidc-context, Python `diagrams` + graphviz.

**Spec:** `docs/superpowers/specs/2026-10-21-serverless-todo-design.md` (read it first; every value below comes from it).

## Global Constraints

- AWS account `609417966933`, profile `AWS_PROFILE=manara-free`, region `us-east-1`. Before any `terraform apply`, run `aws sts get-caller-identity` and confirm it shows `609417966933`; stop if it doesn't.
- Never touch account `599633425453`.
- Name prefix `manara-todo` for every AWS resource. Tag every resource with `Project=manara-todo` (set via provider `default_tags`).
- Lambda runtime is `python3.12`. Use layer `arn:aws:lambda:us-east-1:017000801446:layer:AWSLambdaPowertoolsPythonV3-python312-x86_64:30`. Tracing is `Active`.
- Don't set reserved concurrency (the account's concurrency quota is 10).
- Lambda env vars: `TODOS_TABLE`, `ACTIVITY_TABLE`, `POWERTOOLS_SERVICE_NAME=manara-todo`.
- Never commit `*.tfstate*`, `.terraform/`, `terraform.tfvars`, `node_modules/`, `dist/`, `.venv/` or `build/`.
- Local Python is `/opt/homebrew/bin/python3.12`; the backend venv is `backend/.venv`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Commit locally only; pushing happens in Task 9 after the user confirms.

## Review Focus

1. **Cross-user leakage through the API Gateway cache:** user B must never get user A's cached list. The cache keys include `Authorization`. Task 8 tests this with two users.
2. **Accessing another user's to-do by id:** GET, PUT and DELETE return 404, never the item and never 403. Task 2 tests this.
3. **Malformed bodies:** invalid JSON, a JSON array or string, an empty update or unknown fields return 400 with `{"message": ...}`, never 500. Task 2 tests this.
4. **Stale list after a write (cache TTL 60 s):** a list with a new `v` value returns the new item at once. Task 8 tests this, and the Task 7 frontend always bumps `v`.
5. **Impossible or misformatted `dueDate`:** values like `2026-02-30`, `30-10-2026` or `""` return 400. An explicit `null` in an update clears the due date. Task 1 tests this.

---

### Task 1: Repo scaffold, domain model and repository

**Files:**
- Create: `.gitignore`, `backend/requirements-dev.txt`, `backend/pytest.ini`
- Create: `backend/src/todo_app/__init__.py`, `backend/src/todo_app/models.py`, `backend/src/todo_app/repository.py`
- Test: `backend/tests/conftest.py`, `backend/tests/test_models.py`, `backend/tests/test_repository.py`

**Interfaces:**
- Produces, in `todo_app.models`:
  - `class ValidationError(Exception)`
  - `parse_create(body: dict) -> dict`, which returns `{"title", "description", "status", "dueDate"}`; `dueDate` may be `None`.
  - `parse_update(body: dict) -> dict`, a non-empty subset of the same keys. A `dueDate` of `None` means "clear".
  - `status_due(status: str, due_date: str | None) -> str`
  - `to_public(item: dict) -> dict`, which keeps only `todoId`, `title`, `description`, `status`, `dueDate` (`None` when absent), `createdAt` and `updatedAt`.
- Produces, in `todo_app.repository`: `class TodoRepository(table)` (a boto3 `Table`) with these methods:
  - `list(user_id: str, status: str | None = None) -> list[dict]`
  - `get(user_id, todo_id) -> dict | None`
  - `create(user_id, fields: dict) -> dict`
  - `update(user_id, todo_id, fields: dict) -> dict | None`
  - `delete(user_id, todo_id) -> bool`

  All of them return raw items. Each method's behavior:
  - `list` without a status queries the base table by `userId`. With a status, it queries `StatusDueIndex` with `begins_with(statusDue, "<status>#")`.
  - `create` sets `todoId` (uuid4), `createdAt`, `updatedAt` and `statusDue`. It doesn't store `dueDate` when it is `None`, which keeps `DueDateIndex` sparse.
  - `update` uses `ConditionExpression=attribute_exists(todoId)` and returns `None` on `ConditionalCheckFailedException`. It always recomputes `statusDue` and `updatedAt`, and uses `REMOVE dueDate` when `dueDate` is `None`.
  - `delete` uses the same condition, returns `False` when the item isn't found, and uses `ReturnValues=ALL_OLD`.

- [ ] **Step 1: Scaffold.**
  - `.gitignore` covers the Global Constraints list plus `__pycache__/` and `.pytest_cache/`.
  - `requirements-dev.txt` pins `boto3`, `moto[dynamodb]>=5`, `pytest` and `aws-lambda-powertools[tracer]>=3.17`.
  - `pytest.ini` sets `pythonpath = src` and `testpaths = tests`.
  - Create the venv: `/opt/homebrew/bin/python3.12 -m venv backend/.venv && backend/.venv/bin/pip install -q -r backend/requirements-dev.txt`.
- [ ] **Step 2: Write `conftest.py`.**
  - Set the env vars `AWS_DEFAULT_REGION=us-east-1`, fake credentials, `POWERTOOLS_TRACE_DISABLED=true`, `TODOS_TABLE=todos-test` and `ACTIVITY_TABLE=activity-test`.
  - Add a fixture `tables` that, under `moto.mock_aws()`, creates both tables exactly as the spec describes: keys, the GSIs `StatusDueIndex` (ALL projection) and `DueDateIndex` (KEYS_ONLY), and PAY_PER_REQUEST billing. It yields `(todos_table, activity_table)`.
- [ ] **Step 3: Write failing tests in `test_models.py`:**
  - `parse_create({"title": "  Buy milk "})` returns `{"title": "Buy milk", "description": "", "status": "OPEN", "dueDate": None}`.
  - `parse_create` raises `ValidationError` for each of:
    - a missing title, `""`, or a 201-character title
    - a 2001-character description
    - status `"DOING"`
    - dueDate `"2026-02-30"`, `"30-10-2026"`, `""` or `123`
    - an unknown key `{"title": "a", "owner": "x"}`
  - `parse_update({})` raises. `parse_update({"status": "DONE"})` returns `{"status": "DONE"}`. `parse_update({"dueDate": None})` returns `{"dueDate": None}`.
  - `status_due("OPEN", None)` returns `"OPEN#9999-12-31"`. `status_due("DONE", "2026-11-01")` returns `"DONE#2026-11-01"`.
  - `to_public` drops `userId` and `statusDue` and fills in a missing `dueDate` with `None`.
- [ ] **Step 4: Write failing tests in `test_repository.py`** (using the `tables` fixture):
  - create, then get, round-trips.
  - `list("u1")` excludes items belonging to `"u2"`.
  - `list("u1", "OPEN")` returns only OPEN items, ordered by due date, with undated items last.
  - `update("u1", <u2's id>, {...})` returns `None` and leaves u2's item unchanged.
  - `update(..., {"dueDate": None})` removes the attribute.
  - `delete` of a missing item returns `False`. `delete` of an existing item returns `True`, and a following `get` returns `None`.
- [ ] **Step 5: Run `cd backend && .venv/bin/pytest -q`.** Expected: the tests fail with ImportError.
- [ ] **Step 6: Implement `models.py` and `repository.py`** to the interfaces above. Validate `dueDate` with `datetime.date.fromisoformat` plus a `^\d{4}-\d{2}-\d{2}$` regex. Timestamps use `datetime.now(timezone.utc).isoformat(timespec="seconds")`.
- [ ] **Step 7: Run `.venv/bin/pytest -q`.** Expected: all tests pass.
- [ ] **Step 8: Commit** with the message `feat(backend): todo model validation and DynamoDB repository`.

### Task 2: API Lambda handlers

**Files:**
- Create: `backend/src/todo_app/http.py`, `backend/src/todo_app/activity.py`
- Create: `backend/src/todo_app/handlers/__init__.py`, plus `list_todos.py`, `get_todo.py`, `create_todo.py`, `update_todo.py`, `delete_todo.py` and `list_activity.py` in the same `handlers/` folder
- Test: `backend/tests/test_handlers.py`

**Interfaces:**
- Consumes: Task 1's `models` and `TodoRepository`.
- Produces, in `todo_app.http`:
  - `user_id(event) -> str`, which reads `event["requestContext"]["authorizer"]["claims"]["sub"]`.
  - `json_response(status: int, body: dict | None) -> dict`, which sets `Content-Type: application/json` and `Cache-Control: no-store`. A `body` of `None` produces an empty string.
  - `parse_json_body(event) -> dict`, which raises `ValidationError` unless the body decodes to a JSON object.
- Produces, in `todo_app.activity`: `class ActivityRepository(table)` with:
  - `list(user_id, limit=50) -> list[dict]`, newest first, which drops `userId` and `ttl` from each item.
  - `record(item: dict) -> None`
- Each handler module exposes `handler(event, context)`, decorated with Powertools `@tracer.capture_lambda_handler`. Tables come from env vars, resolved at module import.
- Responses:
  - `list_todos` returns 200 `{"items": [...]}`. Its `status` query parameter is optional; any value other than OPEN or DONE returns 400.
  - `get_todo` returns 200 with the item, or 404 `{"message": "Todo not found"}`.
  - `create_todo` returns 201 with the item.
  - `update_todo` returns 200 with the item, or 404.
  - `delete_todo` returns 204, or 404.
  - `list_activity` returns 200 `{"items": [...]}`.
  - A `ValidationError` returns 400 `{"message": str(e)}`.

- [ ] **Step 1: Write failing tests in `test_handlers.py`.**
  - Use a helper `event(sub, body=None, path=None, query=None)` that builds an API Gateway proxy event, and import each handler inside the `tables` fixture.
  - Assert:
    - The create-then-list flow returns the new item, without `userId` in the body.
    - A GET by user u2 of u1's id returns 404, and so do a PUT and a DELETE by u2.
    - A body of `"not json"` returns 400, a body of `"[1]"` returns 400, a PUT with `"{}"` returns 400, and `?status=foo` returns 400.
    - DELETE returns 204 with an empty body.
    - `list_activity` returns the items seeded directly into the activity table, newest first.
- [ ] **Step 2: Run `.venv/bin/pytest -q tests/test_handlers.py`.** Expected: the tests fail.
- [ ] **Step 3: Implement `http.py`, `activity.py` and the six handler modules.**
- [ ] **Step 4: Run `.venv/bin/pytest -q`.** Expected: all tests pass.
- [ ] **Step 5: Commit** with the message `feat(backend): CRUD and activity Lambda handlers`.

### Task 3: DynamoDB Streams processor

**Files:**
- Create: `backend/src/todo_app/stream.py`, `backend/src/todo_app/handlers/stream_processor.py`
- Test: `backend/tests/test_stream.py`

**Interfaces:**
- Consumes: `ActivityRepository.record` from Task 2.
- Produces:
  - `todo_app.stream.to_activity(record: dict, now: datetime) -> dict | None`. It reads a DynamoDB Streams record with typed images, deserialized via `boto3.dynamodb.types.TypeDeserializer`, and returns `{"userId", "sk", "action", "todoId", "title", "ttl"}`. `sk` is `f"{now.isoformat(timespec='seconds')}#{record['eventID']}"` and `ttl` is `int(now.timestamp()) + 30*86400`.
  - The action is chosen like this:
    - `INSERT` gives `CREATED`.
    - `MODIFY` gives `COMPLETED` when the old status is not `DONE` and the new status is `DONE`; any other `MODIFY` gives `UPDATED`.
    - `REMOVE` gives `DELETED`, taking `title` from the old image.
  - `handler(event, context)` records every non-`None` result and returns `{"batchItemFailures": [...]}` (partial batch response). An exception on one record adds that record's `eventID` as `itemIdentifier`.

- [ ] **Step 1: Write failing tests:** one per action (CREATED, UPDATED, COMPLETED, DELETED) with hand-built typed images. Add one handler test where the second record is malformed (no `Keys`), and assert that `batchItemFailures` lists only that record's `eventID` while the first record lands in the activity table.
- [ ] **Step 2: Run the tests.** Expected: they fail.
- [ ] **Step 3: Implement `stream.py` and `stream_processor.py`.**
- [ ] **Step 4: Run `.venv/bin/pytest -q`.** Expected: all tests pass.
- [ ] **Step 5: Commit** with the message `feat(backend): DynamoDB Streams activity processor`.

### Task 4: Terraform foundation — DynamoDB, Lambda, IAM, budget

**Files:**
- Create: `infra/versions.tf`, `infra/providers.tf`, `infra/variables.tf`, `infra/locals.tf`, `infra/dynamodb.tf`, `infra/iam.tf`, `infra/lambda.tf`, `infra/budget.tf`, `infra/outputs.tf`, `infra/terraform.tfvars.example`

**Interfaces:**
- Variables (default in brackets):
  - `aws_profile` [`manara-free`]
  - `region` [`us-east-1`]
  - `project` [`manara-todo`]
  - `alert_email` (no default)
  - `enable_waf` [true]
  - `enable_api_cache` [true]
  - `api_cache_ttl_seconds` [60]
  - `geo_block_countries` [`["KP","CU","IR","SY"]`]
  - `waf_rate_limit` [300]
- Produces `local.api_functions`, a map of operation key to `{handler, role}` with these keys: `list_todos`, `get_todo`, `list_activity` (role `read`), and `create_todo`, `update_todo`, `delete_todo` (role `write`). Handler strings look like `todo_app.handlers.list_todos.handler`.
- Produces `aws_lambda_function.api[<key>]` (later tasks use its `invoke_arn` and `function_name`), plus `aws_dynamodb_table.todos` and `aws_dynamodb_table.activity`.
- The provider sets `allowed_account_ids = ["609417966933"]`.

- [ ] **Step 1: Write the code.**
  - `dynamodb.tf`: both tables per the spec. Turn on Streams `NEW_AND_OLD_IMAGES` on `todos`, TTL on `ttl` in `activity`, and point-in-time recovery on `todos`.
  - `lambda.tf`: one `archive_file` of `../backend/src`, excluding `__pycache__`, into `build/lambda.zip`. Add `aws_lambda_function.api` (`for_each` over `local.api_functions`, 256 MB, 10 s timeout), `aws_lambda_function.stream_processor`, and an `aws_lambda_event_source_mapping` with `function_response_types = ["ReportBatchItemFailures"]`, batch size 10, `starting_position LATEST`, and `maximum_retry_attempts` 3. Give each function a log group with 14-day retention.
  - `iam.tf`: three roles.
    - `read`: Query/GetItem on `todos` and its indexes, Query on `activity`.
    - `write`: Query/GetItem/PutItem/UpdateItem/DeleteItem on `todos`.
    - `stream`: the stream read actions on the `todos` stream ARN, plus PutItem on `activity`.
    - Each role also gets `AWSLambdaBasicExecutionRole` and `AWSXRayDaemonWriteAccess`.
  - `budget.tf`: a $10 monthly COST budget with ACTUAL notifications at 50 and 100 percent to `var.alert_email`.
  - Outputs: the table names.
- [ ] **Step 2: Create `infra/terraform.tfvars`** (gitignored) with `alert_email`. Ask the user which address to use. Then run `cd infra && terraform init && terraform fmt -check && terraform validate`. Expected: "Success! The configuration is valid."
- [ ] **Step 3: Confirm the identity is 609417966933, then run `AWS_PROFILE=manara-free terraform apply`.**
- [ ] **Step 4: Verify the deployment:**
  - Invoke `manara-todo-create_todo` with a test event via `aws lambda invoke` and confirm a 201 payload.
  - Within about 15 seconds, run `aws dynamodb query` on `manara-todo-activity` for that sub and confirm one `CREATED` item, which proves the stream works.
  - Delete the test item.
- [ ] **Step 5: Commit** with the message `feat(infra): DynamoDB, Lambda functions, IAM roles, budget`.

### Task 5: Terraform — Cognito and API Gateway

**Files:**
- Create: `infra/cognito.tf`, `infra/apigateway.tf`
- Modify: `infra/outputs.tf`

**Interfaces:**
- Consumes: `aws_lambda_function.api` from Task 4.
- Produces:
  - `aws_cognito_user_pool.main`, `aws_cognito_user_pool_client.web`, `aws_cognito_user_pool_client.smoke`, `aws_cognito_user_pool_domain.main`
  - `aws_api_gateway_stage.api` (stage name `api`), `aws_api_gateway_api_key.cloudfront`
  - outputs `user_pool_id`, `web_client_id`, `smoke_client_id`, `hosted_ui_domain`, `api_invoke_url`
- `aws_cognito_user_pool_client.web`'s callback and logout URLs are added in Task 6. In this task they're `["http://localhost:5173/"]`.

- [ ] **Step 1: Write `cognito.tf`.**
  - Pool: email username, `auto_verified_attributes = ["email"]`, password policy min 8 with upper, lower and number required, `deletion_protection = "INACTIVE"`.
  - Domain prefix: `manara-todo-${random_string.suffix.result}` (6 characters, lowercase, no special characters).
  - `web` client: no secret, `allowed_oauth_flows = ["code"]`, scopes `openid`, `email` and `profile`, `supported_identity_providers = ["COGNITO"]`, `prevent_user_existence_errors = "ENABLED"`.
  - `smoke` client: `explicit_auth_flows = ["ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]`.
- [ ] **Step 2: Write `apigateway.tf`.**
  - A REGIONAL REST API with resources `/todos`, `/todos/{id}` and `/activity`.
  - Methods: GET and POST on `/todos`; GET, PUT and DELETE on `/todos/{id}`; GET on `/activity`. Each uses authorization `COGNITO_USER_POOLS` (an authorizer on the pool, identity source `method.request.header.Authorization`) and `api_key_required = true`.
  - Declare request parameters `method.request.header.Authorization`, `method.request.querystring.status` and `method.request.querystring.v` (on `/todos` GET) and `method.request.path.id` (on `/todos/{id}`).
  - Integrations are AWS_PROXY. The GET integrations set `cache_key_parameters` to every declared parameter.
  - Add `aws_lambda_permission` resources.
  - Deployment `triggers` hash the methods and integrations, with `create_before_destroy`.
  - Stage:
    - `cache_cluster_enabled = var.enable_api_cache`, `cache_cluster_size = "0.5"`
    - `xray_tracing_enabled = true`
    - access logs as JSON to a log group with 14-day retention
  - Method settings:
    - `*/*`: metrics on, logging `ERROR`, throttling 20 rps / 40 burst, caching off.
    - `todos/GET` and `todos/{id}/GET`: `caching_enabled = var.enable_api_cache`, `cache_ttl_in_seconds = var.api_cache_ttl_seconds`, `require_authorization_for_cache_control = true`, `unauthorized_cache_control_header_strategy = "SUCCEED_WITH_RESPONSE_HEADER"`.
  - `aws_api_gateway_account` with a CloudWatch role.
  - Usage plan `manara-todo-cloudfront` with throttle 20/40 and a quota of 10,000/DAY, linked to API key `manara-todo-cloudfront`.
- [ ] **Step 3: Run `terraform fmt -check && terraform validate`, confirm the identity, then `terraform apply`.**
- [ ] **Step 4: Verify** with a scratch script:
  - Create a Cognito user via `admin-create-user` plus `admin-set-user-password --permanent`, and get an ID token via `admin-initiate-auth` on the smoke client.
  - curl `api_invoke_url/todos`:
    - with no key: expect 403
    - with the key but no token: expect 401
    - with both: expect 200 `{"items":[]}`
  - Delete the user.
- [ ] **Step 5: Commit** with the message `feat(infra): Cognito user pool and REST API with authorizer, usage plan, cache, X-Ray`.

### Task 6: Terraform — S3 frontend bucket, CloudFront, WAF

**Files:**
- Create: `infra/frontend.tf`, `infra/cloudfront.tf`, `infra/waf.tf`
- Modify: `infra/cognito.tf` (URLs), `infra/outputs.tf`

**Interfaces:**
- Consumes: the stage, the API key and the Cognito resources from Task 5.
- Produces: outputs `app_url` (`https://<distribution domain>/`), `frontend_bucket` and `distribution_id`. Produces the S3 object `config.json`, with content `{"apiBase": "/api", "authority": "https://cognito-idp.us-east-1.amazonaws.com/<poolId>", "clientId": "<web>", "cognitoDomain": "https://<prefix>.auth.us-east-1.amazoncognito.com", "redirectUri": "<app_url>"}` and `cache_control = "no-cache"`.

- [ ] **Step 1: Write `frontend.tf`:** a private bucket (public access fully blocked, BucketOwnerEnforced) and a bucket policy that allows `s3:GetObject` only to `cloudfront.amazonaws.com` with `AWS:SourceArn` set to the distribution.
- [ ] **Step 2: Write `cloudfront.tf`.**
  - OAC for S3, with `default_root_object = "index.html"`, `price_class = "PriceClass_100"`, and `web_acl_id = var.enable_waf ? aws_wafv2_web_acl.main[0].arn : null`.
  - Default behavior: S3 origin, Managed-CachingOptimized, redirect-to-https.
  - Ordered behavior `/api/*`: the API origin is the stage invoke host without a path, so `/api/todos` maps to stage `api`, resource `/todos`. Allow all methods, use Managed-CachingDisabled (`4135ea2d-6df8-44a3-9df3-4b5a84be39ad`) and Managed-AllViewerExceptHostHeader (`b689b0a8-53d0-40ab-baf2-68738e2966ac`), and add the origin custom header `x-api-key` set to the API key value.
  - Don't add distribution-wide custom error responses, because they would rewrite API errors.
- [ ] **Step 3: Write `waf.tf`.** Create `aws_wafv2_web_acl.main` with `count = var.enable_waf ? 1 : 0`, scope CLOUDFRONT, default allow, and CloudWatch metrics on every rule.
  - Rules, in the spec's order:
    - **Priority 0:** geo match on `var.geo_block_countries`, action block.
    - **Priority 1:** rate-based, limit `var.waf_rate_limit`, 300-second window, aggregated by IP, scope-down on `uri_path` STARTS_WITH `/api/`. The action blocks with a custom response: code 429, body key `rate-limited`, content type APPLICATION_JSON, content `{"message":"Too many requests"}`.
    - **Priorities 2–5:** the managed groups, with `override_action none`.
  - Change `cognito.tf`: `web` client callback and logout URLs become `[app_url, "http://localhost:5173/"]`.
- [ ] **Step 4: Run `terraform validate`, confirm the identity, then `terraform apply`.** CloudFront takes about 5–10 minutes.
- [ ] **Step 5: Verify:**
  - `curl -s -o /dev/null -w '%{http_code}' $APP_URL/config.json` returns 200, and the body has the pool id.
  - `$APP_URL/api/todos` without a token returns 401, which proves CloudFront injects the key.
  - `$APP_URL/api/todos?q=1%27%20OR%20%271%27=%271` returns 403 from WAF.
- [ ] **Step 6: Commit** with the message `feat(infra): S3 frontend bucket, CloudFront with API origin, WAF web ACL`.

### Task 7: React frontend and deploy script

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.js`, `frontend/index.html`, `frontend/src/main.jsx`, `frontend/src/App.jsx`, `frontend/src/api.js`, `frontend/src/styles.css`, `frontend/public/config.json` (local-dev sample, excluded from deploy)
- Create: `scripts/deploy_frontend.sh`

**Interfaces:**
- Consumes: the `config.json` shape and outputs from Task 6.
- `api.js` exports `createApi(getToken: () => string)`, which returns `{listTodos(status?), createTodo(fields), updateTodo(id, fields), deleteTodo(id), listActivity()}`.
  - It tracks a module-level `version`, starting at `Date.now()`, which increments after every successful write. It sends `?v=<version>` (and `&status=`) on list GETs and `?v=` on single GETs.
  - It sends the header `Authorization: <id_token>` with no `Bearer` prefix, because the Cognito authorizer takes the raw token.
  - It throws `Error(message)` on a response that isn't 2xx, using the body's `message`.

- [ ] **Step 1: Scaffold.** Run `npm create vite@latest frontend -- --template react`, then `npm i react-oidc-context oidc-client-ts`.
- [ ] **Step 2: Wire up `main.jsx`.** Fetch `/config.json`, then render `<AuthProvider authority clientId redirect_uri scope="openid email profile" onSigninCallback={() => history.replaceState({}, "", "/")}>`.
- [ ] **Step 3: Build `App.jsx`.**
  - Signed out: an intro paragraph about the project and a "Sign in / Sign up" button that calls `signinRedirect()`.
  - Signed in:
    - a header with the user's email and a "Sign out" button, which calls `removeUser()` and then navigates to `${cognitoDomain}/logout?client_id=..&logout_uri=${redirectUri}`
    - an add form (title, optional due date)
    - a filter (All / Open / Done)
    - a list where each to-do has a done checkbox, an inline title edit and a delete button
    - a "Recent activity (DynamoDB Streams)" panel that reloads 3 seconds after each write
  - Errors show in a dismissible banner. Keep it to one page and plain CSS.
- [ ] **Step 4: Write `scripts/deploy_frontend.sh`** (`set -euo pipefail`).
  - Read `frontend_bucket` and `distribution_id` from `terraform -chdir=infra output -raw`.
  - Run `npm --prefix frontend ci && npm --prefix frontend run build`.
  - Run `aws s3 sync frontend/dist s3://$BUCKET --delete --exclude config.json`.
  - Run `aws cloudfront create-invalidation --paths '/*'`.
  - Use `AWS_PROFILE=${AWS_PROFILE:-manara-free}`.
- [ ] **Step 5: Run `npm --prefix frontend run build`** (expect a clean build), then `./scripts/deploy_frontend.sh`.
- [ ] **Step 6: Verify in a browser:** open `app_url`, sign up with a real address, verify the email code, then add, complete, edit and delete a to-do, and watch the activity panel show CREATED, COMPLETED, UPDATED and DELETED. If no browser tool is available, ask the user to do this check.
- [ ] **Step 7: Commit** with the message `feat(frontend): React SPA with Cognito Hosted UI login`.

### Task 8: End-to-end smoke test and WAF rate test

**Files:**
- Create: `scripts/smoke_test.py`, `scripts/waf_rate_test.sh`

**Interfaces:**
- Consumes: the Terraform outputs `app_url`, `api_invoke_url`, `user_pool_id` and `smoke_client_id`.
- `smoke_test.py` uses stdlib `urllib` plus boto3 from the backend venv. It prints `PASS <name>` or `FAIL <name>: <detail>` for each check, exits non-zero on any failure, and always deletes its users in a `finally` block.

- [ ] **Step 1: Write `smoke_test.py`** with these checks, all through `app_url`:
  1. No token returns 401.
  2. A garbage token returns 401.
  3. A call direct to `api_invoke_url` with a valid token but no key returns 403.
  4. User A: create returns 201, then list with a fresh `v` includes the item (stale-cache guard).
  5. User B: list returns `[]`, even right after A's list (cache isolation); GET of A's id returns 404.
  6. A PUT of `{"status": "DONE"}` returns 200; a DELETE returns 204.
  7. Within 20 seconds, `/api/activity` for A shows CREATED, COMPLETED and DELETED.
  8. A SQLi query string returns 403 (skip with a note when `enable_waf` is false).
  9. Two identical GETs of A's list with the same `v`: then report the API Gateway `CacheHitCount` for the stage from CloudWatch over the last 15 minutes. This is informational, because the metric lags by a few minutes.
- [ ] **Step 2: Run `backend/.venv/bin/python scripts/smoke_test.py`.** Expected: every check prints PASS and the exit code is 0.
- [ ] **Step 3: Write `waf_rate_test.sh`.** It fires 400 sequential `curl` GETs at `$APP_URL/api/todos`, prints a count of the status codes, and notes that WAF evaluates the limit with a delay of about 30–60 seconds. Run it. Expected: some 401s, then 429 responses once WAF kicks in.
- [ ] **Step 4: Capture evidence** into `docs/evidence/`: the smoke test output (`smoke_test.txt`), the rate test output (`waf_rate_test.txt`), and the X-Ray trace summary from `aws xray get-trace-summaries`, showing the API Gateway → Lambda → DynamoDB segments for one request (`xray_traces.json`, trimmed).
- [ ] **Step 5: Commit** with the message `test: end-to-end smoke test, WAF rate test, captured evidence`.

### Task 9: Architecture diagram, README, publish

**Files:**
- Create: `docs/architecture/diagram.py`, `docs/architecture/architecture.png`
- Modify: `README.md`

- [ ] **Step 1: Install the diagram tools:** `brew install graphviz` and `backend/.venv/bin/pip install diagrams`.
- [ ] **Step 2: Write `diagram.py`** with the `diagrams` AWS nodes. Show users → CloudFront (with WAF attached), which splits into S3 (the SPA) and API Gateway (with the cache, the Cognito authorizer and the usage plan). API Gateway calls the six Lambdas, which use DynamoDB `todos` (with its GSIs). Its stream feeds the stream Lambda, which writes to DynamoDB `activity`. Draw X-Ray spanning API Gateway, Lambda and DynamoDB, plus CloudWatch Logs and Budgets. Render it with `.venv/bin/python docs/architecture/diagram.py` and check the PNG visually.
- [ ] **Step 3: Write `README.md`**, for Manara reviewers, with these sections:
  - title and live app URL
  - diagram
  - "How to review in 5 minutes": sign up, use the app, and what to look for
  - architecture walkthrough: the request path
  - one section per service with "how to verify", using the evidence files
  - DynamoDB access patterns table (pattern → key/index)
  - security notes: why the ID token, the cache key isolation, why the API key is CloudFront-only
  - cost table and the `enable_waf`/`enable_api_cache` switches
  - deploy and destroy instructions
  - repo layout
- [ ] **Step 4: Commit** with the message `docs: architecture diagram and reviewer README`.
- [ ] **Step 5: Ask the user to confirm before pushing to the public repo,** then `git push origin main`. Check that the README renders on github.com.
