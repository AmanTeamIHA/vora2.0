#!/usr/bin/env python3
"""Apply infra/livekit/inbound-trunk.json to dev LiveKit.

Credentials stay in the environment. The script never prints them. Re-running
when the listed trunk already matches does not create or update.
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

from trunk import (
    Change,
    InboundTrunk,
    ListedTrunk,
    TrunkApplyError,
    TrunkConfigError,
    TrunkConflictError,
    load_template,
    parse_list_payload,
    plan_change,
    render_trunk,
    require_livekit_env,
    scrub,
    secret_values,
)

Runner = Callable[[list[str]], str]


class SipClient(Protocol):
    def list_inbound(self) -> list[ListedTrunk]: ...

    def create_inbound(self, trunk: InboundTrunk) -> None: ...

    def update_inbound(self, trunk_id: str, trunk: InboundTrunk) -> None: ...


def apply_trunk(desired: InboundTrunk, client: SipClient, *, dry_run: bool = False) -> Change:
    change = plan_change(desired, client.list_inbound())
    if dry_run or change.action == "noop":
        return change
    if change.action == "create":
        client.create_inbound(desired)
    elif change.action == "update":
        if not change.sip_trunk_id:
            raise TrunkApplyError("update is missing a trunk id")
        client.update_inbound(change.sip_trunk_id, desired)
    else:
        raise TrunkApplyError("unknown action")
    follow = plan_change(desired, client.list_inbound())
    if follow.action != "noop":
        fields = ",".join(follow.changed_fields) or follow.action
        raise TrunkApplyError(f"apply did not converge: {fields}")
    return change


class LkClient:
    """Talks to LiveKit through the lk CLI. Secrets stay in the environment."""

    def __init__(self, runner: Runner | None = None) -> None:
        self._run = runner or default_run

    def list_inbound(self) -> list[ListedTrunk]:
        payload = self._run(["lk", "sip", "inbound", "list", "--json"])
        return parse_list_payload(payload)

    def create_inbound(self, trunk: InboundTrunk) -> None:
        self._run_json(["lk", "sip", "inbound", "create"], trunk.create_request())

    def update_inbound(self, trunk_id: str, trunk: InboundTrunk) -> None:
        self._run_json(
            ["lk", "sip", "inbound", "update", "--id", trunk_id],
            trunk.trunk_info(),
        )

    def _run_json(self, args: list[str], body: dict) -> None:
        fd, path = tempfile.mkstemp(prefix="vora2-sip-", suffix=".json")
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
        raise TrunkApplyError(scrub(detail, secret_values(os.environ)))
    return proc.stdout


def main(
    argv: list[str] | None = None,
    *,
    client: SipClient | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Apply the dev inbound SIP trunk.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    values = os.environ if env is None else env
    try:
        desired = render_trunk(load_template(args.config), values)
        sip = client
        if sip is None:
            require_livekit_env(values)
            sip = LkClient()
        change = apply_trunk(desired, sip, dry_run=args.dry_run)
    except (TrunkConfigError, TrunkConflictError, TrunkApplyError, OSError) as exc:
        print(scrub(str(exc), secret_values(values)), file=sys.stderr)
        return 1
    print(change.line(dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
