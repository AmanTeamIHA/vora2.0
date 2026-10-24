#!/usr/bin/env python3
"""Apply infra/livekit/dispatch-rule.json to dev LiveKit.

Tenant and agent ids stay in the environment. The script never prints them.
Re-running when the listed rule already matches does not create or update.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Mapping, Protocol

from dispatch import (
    Change,
    DispatchApplyError,
    DispatchConfigError,
    DispatchConflictError,
    DispatchRule,
    ListedRule,
    bind_trunk,
    load_template,
    parse_dispatch_payload,
    plan_change,
    render_settings,
    rules_for,
)
from trunk import (
    ListedTrunk,
    TrunkApplyError,
    TrunkConfigError,
    parse_list_payload,
    require_livekit_env,
    scrub,
    secret_values,
)

Runner = Callable[[list[str]], str]


class DispatchClient(Protocol):
    def list_trunks(self) -> list[ListedTrunk]: ...

    def list_dispatch(self) -> list[ListedRule]: ...

    def create_dispatch(self, rule: DispatchRule) -> None: ...

    def update_dispatch(self, rule_id: str, rule: DispatchRule) -> None: ...


def apply_rule(desired: DispatchRule, client: DispatchClient, *, dry_run: bool = False) -> Change:
    change = plan_change(desired, client.list_dispatch())
    if dry_run or change.action == "noop":
        return change
    if change.action == "create":
        client.create_dispatch(desired)
    elif change.action == "update":
        if not change.sip_dispatch_rule_id:
            raise DispatchApplyError("update is missing a dispatch rule id")
        client.update_dispatch(change.sip_dispatch_rule_id, desired)
    else:
        raise DispatchApplyError("unknown action")
    follow = plan_change(desired, client.list_dispatch())
    if follow.action != "noop":
        fields = ",".join(follow.changed_fields) or follow.action
        raise DispatchApplyError(f"apply did not converge: {fields}")
    return change


def apply_settings(
    rules: tuple[DispatchRule, ...],
    client: DispatchClient,
    *,
    dry_run: bool = False,
) -> list[Change]:
    bound = bind_trunk(rules, client.list_trunks())
    if not bound:
        raise DispatchConfigError("routes must list at least one number")
    for rule in bound:
        if not rule.trunk_ids:
            raise DispatchApplyError(f"{rule.name} is not bound to a trunk")
    return [apply_rule(rule, client, dry_run=dry_run) for rule in bound]


class LkDispatchClient:
    """Talks to LiveKit through the lk CLI. Secrets stay in the environment."""

    def __init__(self, runner: Runner | None = None) -> None:
        self._run = runner or default_run

    def list_trunks(self) -> list[ListedTrunk]:
        payload = self._run(["lk", "sip", "inbound", "list", "--json"])
        return parse_list_payload(payload)

    def list_dispatch(self) -> list[ListedRule]:
        payload = self._run(["lk", "sip", "dispatch", "list", "--json"])
        return parse_dispatch_payload(payload)

    def create_dispatch(self, rule: DispatchRule) -> None:
        self._run_json(["lk", "sip", "dispatch", "create"], rule.create_request())

    def update_dispatch(self, rule_id: str, rule: DispatchRule) -> None:
        self._run_json(["lk", "sip", "dispatch", "update", "--id", rule_id], rule.info())

    def _run_json(self, args: list[str], body: dict) -> None:
        fd, path = tempfile.mkstemp(prefix="vora2-sip-dispatch-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(body, handle)
                handle.write("\n")
            os.chmod(path, 0o600)
            self._run([*args, path])
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


def default_run(args: list[str]) -> str:
    require_livekit_env(os.environ)
    proc = subprocess.run(args, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "lk failed"
        raise DispatchApplyError(scrub(detail, secret_values(os.environ)))
    return proc.stdout


def main(
    argv: list[str] | None = None,
    *,
    client: DispatchClient | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Apply the dev SIP dispatch rule.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    values = os.environ if env is None else env
    try:
        settings = render_settings(load_template(args.config), values)
        sip = client
        if sip is None:
            require_livekit_env(values)
            sip = LkDispatchClient()
        changes = apply_settings(rules_for(settings), sip, dry_run=args.dry_run)
    except (
        DispatchConfigError,
        DispatchConflictError,
        DispatchApplyError,
        TrunkConfigError,
        TrunkApplyError,
        OSError,
    ) as exc:
        print(scrub(str(exc), secret_values(values)), file=sys.stderr)
        return 1
    for change in changes:
        print(change.line(dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
