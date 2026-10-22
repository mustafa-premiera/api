"""Render the architecture diagram.

    brew install graphviz
    pip install -r docs/architecture/requirements.txt
    python docs/architecture/diagram.py   # writes docs/architecture/architecture.png
"""
from pathlib import Path

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.cost import Budgets
from diagrams.aws.compute import Lambda
from diagrams.aws.database import Dynamodb, DynamodbStreams
from diagrams.aws.devtools import XRay
from diagrams.aws.management import Cloudwatch
from diagrams.aws.network import APIGateway, CloudFront
from diagrams.aws.security import Cognito, WAF
from diagrams.aws.storage import S3, SimpleStorageServiceS3Bucket
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.client import Users

out = Path(__file__).resolve().parent / "architecture"

graph_attr = {"fontsize": "26", "pad": "0.5", "nodesep": "0.25", "ranksep": "0.9", "newrank": "true", "splines": "spline"}

with Diagram(
    "Manara To-Do — Serverless Architecture",
    filename=str(out),
    outformat="png",
    direction="LR",
    show=False,
    graph_attr=graph_attr,
):
    users = Users("Users\n(browser)")
    cognito = Cognito("Cognito User Pool\n+ Hosted UI\n(sign-up, ID token)")

    with Cluster("CloudFront distribution"):
      waf = WAF("WAF web ACL\n1 geo block (4 countries)\n2 rate limit 300/5 min/IP\n3 IP reputation\n4 Common (OWASP)\n5 Known bad inputs\n6 SQLi")
      cf = CloudFront("CloudFront\n/* -> S3\n/api/* -> API GW\n(injects x-api-key)")

    with Cluster("Static frontend"):
        s3 = S3("S3 (private, OAC)\nReact SPA")

    apigw = APIGateway("API Gateway REST\nstage 'api'\nCognito authorizer\nusage plan + API key\n0.5 GB cache, 60 s")

    with Cluster("Lambda (python3.12, Powertools)"):
        fns = [
            Lambda("list_todos"),
            Lambda("get_todo"),
            Lambda("list_activity"),
            Lambda("create_todo"),
            Lambda("update_todo"),
            Lambda("delete_todo"),
        ]

    with Cluster("DynamoDB (on-demand)"):
        todos = Dynamodb("todos\nGSI StatusDueIndex\nGSI DueDateIndex")
        stream = DynamodbStreams("Streams\nNEW_AND_OLD_IMAGES")
        activity = Dynamodb("activity\n(TTL 30 days)")

    stream_fn = Lambda("stream_processor")

    xray = XRay("X-Ray\nactive tracing")
    logs = Cloudwatch("CloudWatch Logs\n(14-day retention)")
    budget = Budgets("AWS Budgets\n$10/month alert")

    with Cluster("CI/CD"):
        gha = GithubActions("GitHub Actions\nPR: plan | main: apply")
        tfstate = SimpleStorageServiceS3Bucket("Terraform state (S3)")

    gha >> Edge(label="OIDC → deploy role\nterraform apply", color="royalblue") >> apigw
    gha >> Edge(style="dashed", color="royalblue") >> tfstate

    users >> Edge(label="HTTPS") >> cf
    waf >> Edge(label="attached\nweb ACL", style="dashed", color="firebrick") >> cf
    cf >> Edge(label="default") >> s3
    cf >> Edge(label="/api/*") >> apigw
    users >> Edge(label="sign in (PKCE)\nID token", color="darkgreen") >> cognito
    apigw >> Edge(label="verify token", color="darkgreen", style="dotted") >> cognito

    for fn in fns:
        apigw >> fn
    for fn in fns:
        fn >> Edge(color="steelblue") >> todos
    todos >> Edge(color="darkorange") >> stream >> stream_fn >> Edge(color="darkorange", label="audit item") >> activity

    for node in (apigw, fns[1], stream_fn, todos):
        node >> Edge(style="dashed", color="purple") >> xray
    apigw >> Edge(style="dashed", color="gray") >> logs
    stream_fn >> Edge(style="dashed", color="gray") >> logs
