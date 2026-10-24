import json
import os
import stat
from pathlib import Path

import pytest

from apply import LkClient, apply_trunk, main
from trunk import (
    DEV_LIVEKIT_HOST,
    ENV_CIDRS,
    ENV_PASSWORD,
    ENV_USERNAME,
    PLACEHOLDER_CIDRS,
    PLACEHOLDER_PASSWORD,
    PLACEHOLDER_USERNAME,
    SOFTPHONE_NUMBER,
    TRUNK_NAME,
    InboundTrunk,
    ListedTrunk,
    TrunkConfigError,
    TrunkConflictError,
    load_template,
    parse_list_payload,
    plan_change,
    render_trunk,
    require_livekit_env,
)

CONFIG = Path(__file__).resolve().parents[2] / "infra" / "livekit" / "inbound-trunk.json"
APPLY_SCRIPT = Path(__file__).resolve().parents[2] / "infra" / "livekit" / "apply-inbound-trunk.sh"

SAMPLE_ENV = {
    ENV_USERNAME: "vora-softphone",
    ENV_PASSWORD: "softphone-test-secret",
    ENV_CIDRS: "203.0.113.10/32, 198.51.100.0/24",
}


def desired() -> InboundTrunk:
    return render_trunk(load_template(CONFIG), SAMPLE_ENV)


def listed(trunk: InboundTrunk, trunk_id: str = "ST_test", password_known: bool = True) -> ListedTrunk:
    return ListedTrunk(trunk_id, trunk, password_known)


class MemorySip:
    def __init__(self) -> None:
        self.trunks: list[ListedTrunk] = []
        self.creates = 0
        self.updates = 0

    def list_inbound(self) -> list[ListedTrunk]:
        return list(self.trunks)

    def create_inbound(self, trunk: InboundTrunk) -> None:
        self.creates += 1
        self.trunks.append(listed(trunk, "ST_created"))

    def update_inbound(self, trunk_id: str, trunk: InboundTrunk) -> None:
        self.updates += 1
        self.trunks = [listed(trunk, trunk_id) if item.sip_trunk_id == trunk_id else item for item in self.trunks]


def test_shipped_config_keeps_secrets_as_placeholders() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    raw = load_template(CONFIG)
    assert raw["name"] == TRUNK_NAME
    assert raw["numbers"] == [SOFTPHONE_NUMBER]
    assert raw["auth_username"] == PLACEHOLDER_USERNAME
    assert raw["auth_password"] == PLACEHOLDER_PASSWORD
    assert raw["allowed_addresses"] == [PLACEHOLDER_CIDRS]
    assert "VORA2-46" in raw["metadata"]
    assert "softphone-test-secret" not in text
    assert "AKIA" not in text
    assert "BEGIN " not in text


def test_render_fills_placeholders_and_sorts_cidrs() -> None:
    trunk = desired()
    assert trunk.name == TRUNK_NAME
    assert trunk.numbers == (SOFTPHONE_NUMBER,)
    assert trunk.allowed_addresses == ("198.51.100.0/24", "203.0.113.10/32")
    assert trunk.auth_username == "vora-softphone"
    assert trunk.auth_password == "softphone-test-secret"
    blob = json.dumps(trunk.create_request())
    for token in (PLACEHOLDER_USERNAME, PLACEHOLDER_PASSWORD, PLACEHOLDER_CIDRS):
        assert token not in blob


def test_render_rejects_missing_or_empty_secret() -> None:
    raw = load_template(CONFIG)
    with pytest.raises(TrunkConfigError, match=ENV_PASSWORD):
        render_trunk(raw, {ENV_USERNAME: "vora-softphone", ENV_CIDRS: "203.0.113.10/32"})
    env = dict(SAMPLE_ENV)
    env[ENV_PASSWORD] = ""
    with pytest.raises(TrunkConfigError, match=ENV_PASSWORD):
        render_trunk(raw, env)


def test_render_rejects_a_short_password_without_echoing_it() -> None:
    env = dict(SAMPLE_ENV)
    env[ENV_PASSWORD] = "short-pass"
    with pytest.raises(TrunkConfigError, match="12 to 128") as caught:
        render_trunk(load_template(CONFIG), env)
    assert "short-pass" not in str(caught.value)


def test_render_rejects_open_and_non_ipv4_prefixes() -> None:
    raw = load_template(CONFIG)
    for cidr in ("0.0.0.0/0", "2001:db8::/64", "not-a-cidr"):
        env = dict(SAMPLE_ENV)
        env[ENV_CIDRS] = cidr
        with pytest.raises(TrunkConfigError):
            render_trunk(raw, env)


def test_render_rejects_a_leftover_placeholder() -> None:
    raw = load_template(CONFIG)
    raw["metadata"] = "still __SIP_OTHER__ here"
    with pytest.raises(TrunkConfigError, match="unrendered placeholder"):
        render_trunk(raw, SAMPLE_ENV)


def test_render_rejects_a_non_e164_number() -> None:
    raw = load_template(CONFIG)
    raw["numbers"] = ["910000000000"]
    with pytest.raises(TrunkConfigError, match="E.164"):
        render_trunk(raw, SAMPLE_ENV)


def test_create_request_matches_the_livekit_cli_shape() -> None:
    trunk = desired()
    assert trunk.create_request()["trunk"] == trunk.trunk_info()
    info = trunk.trunk_info()
    assert "sip_trunk_id" not in info
    assert info["numbers"] == [SOFTPHONE_NUMBER]
    assert info["auth_username"] == "vora-softphone"


def test_empty_list_plans_a_create() -> None:
    change = plan_change(desired(), [])
    assert change.action == "create"
    assert change.sip_trunk_id is None


def test_matching_list_plans_noop_including_reversed_cidrs() -> None:
    trunk = desired()
    flipped = InboundTrunk(
        trunk.name,
        trunk.numbers,
        tuple(reversed(trunk.allowed_addresses)),
        trunk.auth_username,
        trunk.auth_password,
        trunk.metadata,
    )
    change = plan_change(trunk, [listed(flipped)])
    assert change.action == "noop"
    assert change.changed_fields == ()
    assert change.line() == f"{TRUNK_NAME} noop ST_test"


def test_field_change_plans_an_update_without_the_secret() -> None:
    trunk = desired()
    current = InboundTrunk(
        trunk.name,
        ("+915555555555",),
        trunk.allowed_addresses,
        trunk.auth_username,
        "previous-password-value",
        trunk.metadata,
    )
    change = plan_change(trunk, [listed(current)])
    assert change.action == "update"
    assert change.changed_fields == ("numbers", "auth_password")
    assert "previous-password-value" not in change.line()
    assert "softphone-test-secret" not in change.line()


def test_hidden_password_does_not_force_an_update() -> None:
    trunk = desired()
    stored = InboundTrunk(
        trunk.name,
        trunk.numbers,
        trunk.allowed_addresses,
        trunk.auth_username,
        "",
        trunk.metadata,
    )
    change = plan_change(trunk, [listed(stored, password_known=False)])
    assert change.action == "noop"


def test_duplicate_name_is_a_conflict() -> None:
    trunk = desired()
    with pytest.raises(TrunkConflictError, match="ST_a, ST_b"):
        plan_change(trunk, [listed(trunk, "ST_a"), listed(trunk, "ST_b")])


def test_second_apply_makes_no_changes() -> None:
    client = MemorySip()
    first = apply_trunk(desired(), client)
    assert first.action == "create"
    assert client.creates == 1
    second = apply_trunk(desired(), client)
    assert second.action == "noop"
    assert client.creates == 1
    assert client.updates == 0


def test_dry_run_does_not_write() -> None:
    client = MemorySip()
    change = apply_trunk(desired(), client, dry_run=True)
    assert change.action == "create"
    assert client.creates == 0
    assert client.updates == 0


def test_update_then_second_apply_is_noop() -> None:
    trunk = desired()
    stale = InboundTrunk(
        trunk.name,
        trunk.numbers,
        ("203.0.113.10/32",),
        trunk.auth_username,
        trunk.auth_password,
        trunk.metadata,
    )
    client = MemorySip()
    client.trunks.append(listed(stale, "ST_existing"))
    first = apply_trunk(trunk, client)
    assert first.action == "update"
    assert first.changed_fields == ("allowed_addresses",)
    assert client.updates == 1
    second = apply_trunk(trunk, client)
    assert second.action == "noop"
    assert client.updates == 1


def test_parse_list_accepts_camel_case_snake_case_and_empty() -> None:
    trunk = desired()
    camel = {
        "items": [
            {
                "sipTrunkId": "ST_camel",
                "name": trunk.name,
                "metadata": trunk.metadata,
                "numbers": list(trunk.numbers),
                "allowedAddresses": list(trunk.allowed_addresses),
                "authUsername": trunk.auth_username,
                "authPassword": trunk.auth_password,
            }
        ]
    }
    parsed = parse_list_payload(json.dumps(camel))
    assert plan_change(trunk, parsed).action == "noop"

    snake = {
        "items": [
            {
                "sip_trunk_id": "ST_snake",
                "name": trunk.name,
                "metadata": trunk.metadata,
                "numbers": list(reversed(trunk.numbers)),
                "allowed_addresses": ["203.0.113.10"],
                "auth_username": trunk.auth_username,
                "auth_password": trunk.auth_password,
            }
        ]
    }
    snake_parsed = parse_list_payload("noise before json " + json.dumps(snake))
    assert snake_parsed[0].trunk.allowed_addresses == ("203.0.113.10/32",)
    assert parse_list_payload("{}") == []
    redacted = dict(camel["items"][0])
    redacted["authPassword"] = "****"
    hidden = parse_list_payload(json.dumps({"items": [redacted, None]}))
    assert hidden[0].password_known is False


def test_lk_client_writes_create_json_without_putting_the_secret_on_the_command() -> None:
    seen: list[tuple[list[str], dict | None]] = []

    def runner(args: list[str]) -> str:
        body = None
        if args[-1].endswith(".json"):
            path = args[-1]
            assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
            body = json.loads(Path(path).read_text(encoding="utf-8"))
        seen.append((args, body))
        if args[3] == "list":
            return "{}"
        return ""

    client = LkClient(runner)
    trunk = desired()
    client.create_inbound(trunk)
    client.update_inbound("ST_existing", trunk)
    create_args, create_body = seen[0]
    update_args, update_body = seen[1]
    assert create_args[:4] == ["lk", "sip", "inbound", "create"]
    assert create_body == trunk.create_request()
    assert "softphone-test-secret" not in " ".join(create_args)
    assert update_args[:6] == ["lk", "sip", "inbound", "update", "--id", "ST_existing"]
    assert "trunk" not in update_body
    assert "sip_trunk_id" not in update_body
    assert update_body["auth_password"] == trunk.auth_password
    assert not Path(create_args[-1]).exists()
    assert not Path(update_args[-1]).exists()


def test_lk_apply_second_run_only_lists() -> None:
    calls: list[str] = []
    state: dict = {"items": []}

    def runner(args: list[str]) -> str:
        calls.append(args[3])
        if args[3] == "list":
            return json.dumps(state)
        body = json.loads(Path(args[-1]).read_text(encoding="utf-8"))
        info = body["trunk"] if "trunk" in body else body
        state["items"] = [
            {
                "sipTrunkId": "ST_live",
                "name": info["name"],
                "metadata": info["metadata"],
                "numbers": info["numbers"],
                "allowedAddresses": info["allowed_addresses"],
                "authUsername": info["auth_username"],
                "authPassword": info["auth_password"],
            }
        ]
        return ""

    client = LkClient(runner)
    first = apply_trunk(desired(), client)
    second = apply_trunk(desired(), client)
    assert first.action == "create"
    assert second.action == "noop"
    assert calls == ["list", "create", "list", "list"]


def test_main_dry_run_does_not_print_the_password(capsys) -> None:
    code = main(["--config", str(CONFIG), "--dry-run"], client=MemorySip(), env=SAMPLE_ENV)
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == f"dry-run {TRUNK_NAME} create"
    assert "softphone-test-secret" not in captured.out
    assert "softphone-test-secret" not in captured.err


def test_main_second_run_reports_noop(capsys) -> None:
    client = MemorySip()
    assert main(["--config", str(CONFIG)], client=client, env=SAMPLE_ENV) == 0
    capsys.readouterr()
    assert main(["--config", str(CONFIG)], client=client, env=SAMPLE_ENV) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"{TRUNK_NAME} noop ST_created"
    assert client.creates == 1
    assert client.updates == 0


def test_main_scrubs_a_secret_from_the_error(capsys) -> None:
    from trunk import TrunkApplyError

    class Failing:
        def list_inbound(self):
            raise TrunkApplyError("lk said softphone-test-secret")

        def create_inbound(self, trunk):
            raise AssertionError("create")

        def update_inbound(self, trunk_id, trunk):
            raise AssertionError("update")

    code = main(["--config", str(CONFIG)], client=Failing(), env=SAMPLE_ENV)
    captured = capsys.readouterr()
    assert code == 1
    assert "softphone-test-secret" not in captured.err
    assert "***" in captured.err


def test_livekit_env_is_the_dev_host() -> None:
    with pytest.raises(TrunkConfigError, match="LIVEKIT_URL"):
        require_livekit_env({})
    with pytest.raises(TrunkConfigError, match=DEV_LIVEKIT_HOST):
        require_livekit_env(
            {
                "LIVEKIT_URL": "wss://livekit.example.com",
                "LIVEKIT_API_KEY": "key",
                "LIVEKIT_API_SECRET": "secret",
            }
        )
    require_livekit_env(
        {
            "LIVEKIT_URL": f"wss://{DEV_LIVEKIT_HOST}",
            "LIVEKIT_API_KEY": "key",
            "LIVEKIT_API_SECRET": "secret",
        }
    )


def test_apply_script_points_at_the_trunk_config() -> None:
    text = APPLY_SCRIPT.read_text(encoding="utf-8")
    assert "voice/sip/apply.py" in text
    assert "infra/livekit/inbound-trunk.json" in text
    assert stat.S_IMODE(APPLY_SCRIPT.stat().st_mode) & stat.S_IXUSR
