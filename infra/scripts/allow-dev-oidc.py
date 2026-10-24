#!/usr/bin/env python3
"""Allow this repo's dev branch to assume the existing vora2 GitHub deploy role.

The role already trusts this repo. This adds refs/heads/dev next to an existing
refs/heads/main subject. It does not add another repository, a wildcard, or a
new role. It refuses to edit the role unless the role is tagged project=vora2.
"""

from __future__ import annotations

import json
import subprocess
import sys

ROLE_NAME = "vora2-github-dev"
MAIN_REF = "refs/heads/main"
DEV_REF = "refs/heads/dev"
SUB_OPS = ("StringEquals", "StringLike", "ForAnyValue:StringEquals", "ForAnyValue:StringLike")


def aws(*args: str) -> dict:
    result = subprocess.run(
        ["aws", *args, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout)


def this_repo(subject: str) -> bool:
    return "vora2.0" in subject and ("AmanTeamIHA" in subject or "133864079" in subject)


def dev_subject(subject: str) -> str | None:
    if MAIN_REF in subject and this_repo(subject):
        return subject.replace(MAIN_REF, DEV_REF)
    return None


def as_list(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        return [value]
    return list(value)


def main() -> None:
    tags = aws("iam", "list-role-tags", "--role-name", ROLE_NAME).get("Tags", [])
    project = next((tag["Value"] for tag in tags if tag["Key"].lower() == "project"), None)
    if project != "vora2":
        raise SystemExit(f"refusing to edit {ROLE_NAME}: project tag is {project!r}")

    role = aws("iam", "get-role", "--role-name", ROLE_NAME)["Role"]
    policy = role["AssumeRolePolicyDocument"]
    statements = policy.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]
    policy["Statement"] = statements
    added: list[str] = []

    for statement in statements:
        conditions = statement.get("Condition", {})
        for op in SUB_OPS:
            block = conditions.get(op)
            if not isinstance(block, dict):
                continue
            for key, value in list(block.items()):
                if not key.endswith(":sub"):
                    continue
                subjects = as_list(value)
                for subject in subjects:
                    if not isinstance(subject, str):
                        continue
                    extra = dev_subject(subject)
                    if extra and extra not in subjects:
                        subjects.append(extra)
                        added.append(extra)
                block[key] = subjects

    if not added:
        print("dev subject already present, or no main subject for this repo was found")
        print(json.dumps(policy, indent=2))
        if not any(
            isinstance(subject, str) and DEV_REF in subject and this_repo(subject)
            for statement in policy.get("Statement", [])
            for op in SUB_OPS
            for key, value in statement.get("Condition", {}).get(op, {}).items()
            if key.endswith(":sub")
            for subject in as_list(value)
        ):
            raise SystemExit("no refs/heads/main subject for this repo; not widening the trust")
        return

    document_path = "/tmp/vora2-github-dev-trust.json"
    with open(document_path, "w", encoding="utf-8") as handle:
        json.dump(policy, handle)
    subprocess.run(
        [
            "aws",
            "iam",
            "update-assume-role-policy",
            "--role-name",
            ROLE_NAME,
            "--policy-document",
            f"file://{document_path}",
        ],
        check=True,
    )
    print("added subjects:")
    for subject in added:
        print(subject)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or "")
        raise
