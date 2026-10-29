#!/usr/bin/env python3
"""End-to-end smoke test for the live to-do app. Run with backend/.venv/bin/python.

Config comes from env vars (APP_URL, API_INVOKE_URL, USER_POOL_ID, SMOKE_CLIENT_ID,
API_KEY_VALUE, ENABLE_WAF) or, when unset, from `terraform -chdir=infra output`.
"""
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import boto3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = []


def tf(name):
    return subprocess.check_output(
        ["terraform", f"-chdir={ROOT}/infra", "output", "-raw", name], text=True
    ).strip()


def cfg(env, tf_name):
    return os.environ.get(env) or tf(tf_name)


def report(name, ok, detail=""):
    if ok:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}: {detail}")
        failures.append(name)


def call(method, url, token=None, body=None, headers=None):
    h = dict(headers or {})
    if token:
        h["Authorization"] = token
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            code = r.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        code = e.code
    try:
        return code, json.loads(raw) if raw else None
    except ValueError:
        return code, raw.decode(errors="replace")


def main():
    app = cfg("APP_URL", "app_url").rstrip("/")
    api_direct = cfg("API_INVOKE_URL", "api_invoke_url").rstrip("/")
    pool = cfg("USER_POOL_ID", "user_pool_id")
    client = cfg("SMOKE_CLIENT_ID", "smoke_client_id")
    waf_on = (os.environ.get("ENABLE_WAF", "true")).lower() == "true"
    region = os.environ.get("AWS_REGION", "us-east-1")
    idp = boto3.client("cognito-idp", region_name=region)
    ddb = boto3.client("dynamodb", region_name=region)
    cw = boto3.client("cloudwatch", region_name=region)
    todos_tbl, act_tbl = tf("todos_table_name"), tf("activity_table_name")

    users = {}  # label -> (username, sub, token)

    def make_user(label):
        email = f"smoke-{label}+{secrets.token_hex(4)}@example.com"
        pw = "Aa1!" + secrets.token_urlsafe(18)
        idp.admin_create_user(
            UserPoolId=pool, Username=email, MessageAction="SUPPRESS",
            UserAttributes=[{"Name": "email", "Value": email},
                            {"Name": "email_verified", "Value": "true"}])
        users[label] = {"username": email, "sub": None, "token": None}
        idp.admin_set_user_password(UserPoolId=pool, Username=email, Password=pw, Permanent=True)
        users[label]["sub"] = next(a["Value"] for a in idp.admin_get_user(
            UserPoolId=pool, Username=email)["UserAttributes"] if a["Name"] == "sub")
        r = idp.admin_initiate_auth(
            UserPoolId=pool, ClientId=client, AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": pw})
        users[label]["token"] = r["AuthenticationResult"]["IdToken"]
        return users[label]["token"]

    try:
        ta = make_user("a")
        tb = make_user("b")

        # 1, 2
        c, _ = call("GET", f"{app}/api/todos")
        report("1 no token -> 401", c == 401, f"got {c}")
        c, _ = call("GET", f"{app}/api/todos", token="not.a.token")
        report("2 garbage token -> 401", c == 401, f"got {c}")

        # 3: direct to API Gateway, valid token, no API key
        c, _ = call("GET", f"{api_direct}/todos", token=ta)
        report("3 direct to API GW without key -> 403", c == 403, f"got {c}")

        # 4
        c, item = call("POST", f"{app}/api/todos", ta, {"title": "smoke todo"})
        tid = item.get("todoId") if isinstance(item, dict) else None
        report("4a A create -> 201", c == 201 and tid, f"got {c} {item}")
        v = secrets.token_hex(3)
        c, lst = call("GET", f"{app}/api/todos?v={v}", ta)
        ids = [i.get("todoId") for i in (lst or {}).get("items", [])] if isinstance(lst, dict) else []
        report("4b A list (fresh v) includes item", c == 200 and tid in ids, f"got {c} {ids}")

        # 5
        c, lb = call("GET", f"{app}/api/todos?v={v}", tb)
        report("5a B list is empty (cache isolation)",
               c == 200 and isinstance(lb, dict) and lb.get("items") == [], f"got {c} {lb}")
        c, _ = call("GET", f"{app}/api/todos/{tid}", tb)
        report("5b B GET of A's id -> 404", c == 404, f"got {c}")

        # 6
        c, upd = call("PUT", f"{app}/api/todos/{tid}", ta, {"status": "DONE"})
        report("6a A PUT status DONE -> 200", c == 200, f"got {c} {upd}")
        c, _ = call("DELETE", f"{app}/api/todos/{tid}", ta)
        report("6b A DELETE -> 204", c == 204, f"got {c}")

        # 7
        want = {"CREATED", "COMPLETED", "DELETED"}
        seen = set()
        deadline = time.time() + 20
        while time.time() < deadline:
            c, act = call("GET", f"{app}/api/activity", ta)
            if c == 200 and isinstance(act, dict):
                seen = {i.get("action") for i in act.get("items", [])}
                if want <= seen:
                    break
            time.sleep(2)
        report("7 activity shows CREATED, COMPLETED, DELETED within 20s",
               want <= seen, f"saw {sorted(seen)}")

        # 8
        if waf_on:
            c, _ = call("GET", f"{app}/api/todos?id=1%27%20OR%20%271%27%3D%271", ta)
            report("8 SQLi query string -> 403", c == 403, f"got {c}")
        else:
            print("SKIP 8 SQLi probe (enable_waf is false)")

        # 9 (informational)
        v2 = secrets.token_hex(3)
        c1, _ = call("GET", f"{app}/api/todos?v={v2}", ta)
        c2, _ = call("GET", f"{app}/api/todos?v={v2}", ta)
        report("9 two identical GETs same v -> 200", c1 == 200 and c2 == 200, f"got {c1},{c2}")
        try:
            end = datetime.now(timezone.utc)
            stats = cw.get_metric_statistics(
                Namespace="AWS/ApiGateway", MetricName="CacheHitCount",
                Dimensions=[{"Name": "ApiName", "Value": "manara-todo"},
                            {"Name": "Stage", "Value": "api"}],
                StartTime=end - timedelta(minutes=15), EndTime=end,
                Period=300, Statistics=["Sum"])
            pts = stats.get("Datapoints", [])
            if pts:
                print(f"INFO 9 CacheHitCount (last 15m) = {int(sum(p['Sum'] for p in pts))}")
            else:
                print("INFO 9 CacheHitCount not yet available (CloudWatch lag)")
        except Exception as e:  # informational only
            print(f"INFO 9 CacheHitCount lookup failed: {type(e).__name__}")
    finally:
        print("-- cleanup")
        subs = [u["sub"] for u in users.values() if u["sub"]]
        for sub in subs:
            try:
                for it in ddb.query(TableName=todos_tbl, KeyConditionExpression="userId = :u",
                                    ExpressionAttributeValues={":u": {"S": sub}})["Items"]:
                    ddb.delete_item(TableName=todos_tbl, Key={"userId": it["userId"], "todoId": it["todoId"]})
            except Exception as e:
                print(f"cleanup todos failed: {type(e).__name__}")
        if subs:
            time.sleep(15)  # let stream events land before removing activity rows
        for sub in subs:
            try:
                n = 0
                for it in ddb.query(TableName=act_tbl, KeyConditionExpression="userId = :u",
                                    ExpressionAttributeValues={":u": {"S": sub}})["Items"]:
                    ddb.delete_item(TableName=act_tbl, Key={"userId": it["userId"], "sk": it["sk"]})
                    n += 1
                print(f"deleted {n} activity rows for a smoke user")
            except Exception as e:
                print(f"cleanup activity failed: {type(e).__name__}")
        for u in users.values():
            try:
                idp.admin_delete_user(UserPoolId=pool, Username=u["username"])
            except Exception as e:
                print(f"delete user failed: {type(e).__name__}")
        print(f"deleted {len(users)} smoke users")

    if failures:
        print(f"\n{len(failures)} check(s) FAILED: {failures}")
        sys.exit(1)
    print("\nAll checks passed")


if __name__ == "__main__":
    main()
