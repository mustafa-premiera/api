# Serverless To-Do API — Design

Manara "Becoming a Solutions Architect", Project 3: Serverless REST API with Cognito Auth, DynamoDB & WAF.

## Intent

The Manara team grades the project from the public repo `mustafa-premiera/api`. They need:
- a README with a Solution Architecture Diagram, and
- a **live app** they can use themselves: open a CloudFront URL, sign up through the Cognito Hosted UI, and manage their own to-dos.

The README must show where each required service fits and how a reviewer can check that it works.

## Goals
- Every service and learning outcome in the brief is implemented and can be checked on the live app: API Gateway (REST, Cognito authorizer, usage plan, caching), Cognito (User Pool, Hosted UI, JWT), Lambda (CRUD, env vars, IAM roles), DynamoDB (GSIs, on-demand, Streams), WAF (rate-based, geo, OWASP managed rules), CloudFront, X-Ray, and S3 + CloudFront for the frontend.
- Each user sees only their own to-dos.
- One `terraform apply` plus one frontend deploy script brings everything up, and `terraform destroy` tears it all down.

## Non-goals
- No custom domain; the default `*.cloudfront.net` URL is used.
- No multi-region setup, no CI/CD pipeline, and no remote Terraform state (state stays local and gitignored).
- No WAF Bot Control managed rule group, because it costs about $10/month on top of the rest. The README covers bot protection through the IP reputation and known-bad-inputs groups instead.

## Anti-goals
- Never deploy to account 599633425453 (the management account).
- Reviewers must never see another user's to-dos, including through the API Gateway cache.
- Don't commit secrets, state, or `terraform.tfvars`.

## Constraints
- AWS account **609417966933**, CLI profile **`manara-free`** (SSO), region **us-east-1**.
- The account's credit balance is unconfirmed, so keep costs low. The two paid-only features are WAF and API Gateway caching. Each gets a Terraform switch (`enable_waf`, `enable_api_cache`), and both default to `true`.
- The new account's Lambda concurrency quota is **10**, so no reserved concurrency can be set.
- Local tooling: Terraform 1.15, Node 26, Python 3.12 (`/opt/homebrew/bin/python3.12`). Lambda runtime is **python3.12**.

## Decided with the user
- To-do app, built by Claude, with Terraform, deployed to 609417966933.
- Public repo with a README and an architecture diagram, plus a live app for the reviewers.

## Claude's calls (the user can override)
- **Lambda:** Python 3.12 with the AWS Lambda Powertools v3 public layer, which provides the X-Ray Tracer and structured logging.
- **One CloudFront distribution, two origins.** The default behavior serves S3 (the React SPA, via Origin Access Control). The `/api/*` behavior goes to the regional REST API, whose stage is named `api`, so `/api/todos` maps straight through. Benefits: same origin, no CORS, and one WAF web ACL (CLOUDFRONT scope) covers both.
- **Caching at two layers.** CloudFront caches static assets and has caching disabled for `/api/*`. API Gateway caches GET responses: 0.5 GB cluster, TTL 60 s. The cache keys include the `Authorization` header (so users stay isolated) and a `v` query parameter. After every write, the frontend bumps `v`, which forces a fresh read without needing IAM-authorized cache invalidation.
- **The usage plan requires an API key, and CloudFront injects it** as the `x-api-key` origin header. The browser never sees the key, and direct calls to `execute-api` without it get 403. That forces all traffic through CloudFront and WAF. Usage plan limits: 20 rps rate, 40 burst, 10,000 requests/day quota.
- **Authorization uses the Cognito ID token** (the `COGNITO_USER_POOLS` authorizer). The user id is `requestContext.authorizer.claims.sub`.
- **DynamoDB**, table `manara-todo-todos`, on-demand:
  - PK `userId` (Cognito sub), SK `todoId` (UUID4).
  - Attributes: `title` (1–200 chars), `description` (0–2000), `status` (`OPEN`|`DONE`), `dueDate` (`YYYY-MM-DD` or absent), `createdAt`, `updatedAt` (ISO-8601 UTC), and `statusDue` = `"<status>#<dueDate or 9999-12-31>"`.
  - GSI `StatusDueIndex` (PK `userId`, SK `statusDue`) serves "my OPEN/DONE to-dos ordered by due date".
  - GSI `DueDateIndex` (PK `dueDate`, SK `userId`, keys-only projection) serves a future "everything due on day X" reminder job. It's sparse: only items with a due date appear.
  - Streams use `NEW_AND_OLD_IMAGES`.
- **Streams consumer.** A Lambda writes one audit item per change to table `manara-todo-activity`: PK `userId`, SK `"<ISO timestamp>#<eventId>"`, plus `action` (`CREATED`|`UPDATED`|`COMPLETED`|`DELETED`), `todoId`, `title`, and `ttl` set to 30 days. The `GET /api/activity` endpoint shows it, so reviewers can watch Streams work live.
- **API** (all routes require a Cognito token and an API key):
  - `GET /todos?status=OPEN|DONE`
  - `POST /todos`
  - `GET /todos/{id}`
  - `PUT /todos/{id}` (partial update of title, description, status, dueDate)
  - `DELETE /todos/{id}`
  - `GET /activity`
  - Each operation is its own Lambda function, all from one code package. Read functions get a read-only IAM role, and write functions a read/write role on the todos table only.
- **WAF**, in this rule order:
  1. Geo block on a sample country list (`KP`, `CU`, `IR`, `SY`), never Egypt or the Gulf.
  2. Rate limit: 300 requests per 5 minutes per IP on `/api/`, answered with a custom 429 JSON body.
  3. `AWSManagedRulesAmazonIpReputationList`
  4. `AWSManagedRulesCommonRuleSet` (OWASP Top 10)
  5. `AWSManagedRulesKnownBadInputsRuleSet`
  6. `AWSManagedRulesSQLiRuleSet`
- **Cognito.** Email is the username, self sign-up is on, and emails are verified with Cognito's default sender. The Hosted UI domain prefix is `manara-todo-<random 6>`. The app client is public (no secret) and uses the authorization code flow with PKCE and scopes `openid email profile`. Its callback and logout URL is the CloudFront URL. A second `smoke-test` client allows only `ADMIN_USER_PASSWORD_AUTH`, for the scripted end-to-end test.
- **Frontend:** Vite + React + `react-oidc-context`/`oidc-client-ts`. Runtime config is `/config.json`, written by Terraform into the S3 bucket, so a frontend build doesn't depend on Terraform outputs.
- **Observability:** X-Ray active tracing on the API Gateway stage and on every Lambda; API Gateway access logs; CloudWatch log retention of 14 days.
- **Cost guard:** an AWS Budget of $10/month, emailing `alert_email` at 50% and 100% of actual spend.
- **Diagram:** the Python `diagrams` library (needs `brew install graphviz`). It renders `docs/architecture/architecture.png`, and the source is committed next to the image.
