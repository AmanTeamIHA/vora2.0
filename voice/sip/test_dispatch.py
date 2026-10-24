import json
import os
import stat
import uuid
from pathlib import Path

import pytest

from apply_dispatch import LkDispatchClient, apply_settings, main
from dispatch import (
    AGENT_NAME,
    ENV_AGENT_ID,
    ENV_TENANT_ID,
    PLACEHOLDER_AGENT_ID,
    PLACEHOLDER_TENANT_ID,
    ROOM_PREFIX,
    RULE_NAME,
    SOFTPHONE_NUMBER,
    TENANT_NAME,
    TRUNK_NAME,
    WORKER_AGENT_NAME,
    DispatchApplyError,
    DispatchConfigError,
    DispatchConflictError,
    ListedRule,
    individual_room_name,
    load_template,
    lookup_number,
    parse_dispatch_payload,
    plan_change,
    read_settings,
    render_settings,
    rules_for,
)
from trunk import InboundTrunk, ListedTrunk

CONFIG = Path(__file__).resolve().parents[2] / "infra" / "livekit" / "dispatch-rule.json"
APPLY_SCRIPT = Path(__file__).resolve().parents[2] / "infra" / "livekit" / "apply-dispatch-rule.sh"

TENANT_ID = "11111111-1111-4111-8111-111111111111"
AGENT_ID = "22222222-2222-4222-8222-222222222222"
SAMPLE_ENV = {ENV_TENANT_ID: TENANT_ID, ENV_AGENT_ID: AGENT_ID}


def settings(env: dict | None = None):
    return render_settings(load_template(CONFIG), SAMPLE_ENV if env is None else env)


def desired_rule():
    return rules_for(settings())[0]


def trunk(trunk_id: str = "ST_trunk") -> ListedTrunk:
    return ListedTrunk(
        trunk_id,
        InboundTrunk(TRUNK_NAME, (SOFTPHONE_NUMBER,), ("203.0.113.10/32",), "user", "password-value", "meta"),
        True,
    )


def listed_from(rule, rule_id: str = "SDR_test") -> ListedRule:
    payload = {
        "items": [
            {
                "sipDispatchRuleId": rule_id,
                "name": rule.name,
                "metadata": rule.rule_metadata,
                "trunkIds": list(rule.trunk_ids),
                "numbers": [rule.number],
                "rule": {
                    "dispatchRuleIndividual": {
                        "roomPrefix": rule.room_prefix,
                        "noRandomness": rule.no_randomness,
                    }
                },
                "roomConfig": {
                    "metadata": json.dumps(rule.room_metadata, separators=(",", ":"), sort_keys=True),
                    "emptyTimeout": rule.empty_timeout,
                    "departureTimeout": rule.departure_timeout,
                    "agents": [{"agentName": rule.worker_agent_name}],
                },
            }
        ]
    }
    return parse_dispatch_payload(json.dumps(payload))[0]


class MemoryDispatch:
    def __init__(self, trunks: list[ListedTrunk] | None = None) -> None:
        self.trunks = [trunk()] if trunks is None else list(trunks)
        self.rules: list[ListedRule] = []
        self.creates = 0
        self.updates = 0

    def list_trunks(self) -> list[ListedTrunk]:
        return list(self.trunks)

    def list_dispatch(self) -> list[ListedRule]:
        return list(self.rules)

    def create_dispatch(self, rule) -> None:
        self.creates += 1
        self.rules.append(ListedRule("SDR_created", rule))

    def update_dispatch(self, rule_id: str, rule) -> None:
        self.updates += 1
        self.rules = [
            ListedRule(rule_id, rule) if item.sip_dispatch_rule_id == rule_id else item
            for item in self.rules
        ]


def test_shipped_map_seeds_the_softphone_number() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    raw = load_template(CONFIG)
    stored = read_settings(raw)
    assert stored.trunk_name == TRUNK_NAME
    assert stored.worker_agent_name == WORKER_AGENT_NAME
    assert stored.room_prefix == ROOM_PREFIX
    assert stored.departure_timeout == 10
    assert len(stored.routes) == 1
    route = stored.routes[0]
    assert route.name == RULE_NAME
    assert route.number == SOFTPHONE_NUMBER
    assert route.tenant_name == TENANT_NAME
    assert route.agent_name == AGENT_NAME
    assert route.tenant_id == PLACEHOLDER_TENANT_ID
    assert route.agent_id == PLACEHOLDER_AGENT_ID
    assert "VORA2-47" in stored.rule_metadata
    assert TENANT_ID not in text
    assert AGENT_ID not in text
    assert "AKIA" not in text


def test_known_number_returns_the_seed_tenant_and_agent() -> None:
    hit = lookup_number(read_settings(load_template(CONFIG)), SOFTPHONE_NUMBER)
    assert hit is not None
    assert hit.tenant_name == TENANT_NAME
    assert hit.agent_name == AGENT_NAME
    assert hit.number == SOFTPHONE_NUMBER


def test_unknown_number_is_rejected_and_logged(caplog) -> None:
    unknown = "+919876543210"
    with caplog.at_level("INFO", logger="vora.sip"):
        hit = lookup_number(read_settings(load_template(CONFIG)), unknown)
    assert hit is None
    assert f"rejected unknown called number {unknown}" in caplog.text
    assert "no room created" in caplog.text


def test_known_number_does_not_log_a_rejection(caplog) -> None:
    with caplog.at_level("INFO", logger="vora.sip"):
        lookup_number(settings(), SOFTPHONE_NUMBER)
    assert "rejected" not in caplog.text


def test_render_fills_uuid_placeholders_into_room_metadata() -> None:
    rule = desired_rule()
    assert rule.tenant_id == TENANT_ID
    assert rule.agent_id == AGENT_ID
    assert rule.room_metadata == {"tenant_id": TENANT_ID, "agent_id": AGENT_ID}
    body = rule.info()
    metadata = json.loads(body["room_config"]["metadata"])
    assert metadata == {"agent_id": AGENT_ID, "tenant_id": TENANT_ID}
    assert body["numbers"] == [SOFTPHONE_NUMBER]
    assert "inbound_numbers" not in body
    assert body["rule"]["dispatch_rule_individual"]["room_prefix"] == ROOM_PREFIX
    assert body["rule"]["dispatch_rule_individual"]["no_randomness"] is False
    assert body["room_config"]["agents"] == [{"agent_name": ""}]
    assert body["room_config"]["departure_timeout"] == 10
    assert body["trunk_ids"] == []
    for token in (PLACEHOLDER_TENANT_ID, PLACEHOLDER_AGENT_ID):
        assert token not in json.dumps(body)


def test_render_rejects_a_missing_or_invalid_id_without_echoing_it() -> None:
    with pytest.raises(DispatchConfigError, match=ENV_TENANT_ID):
        settings({ENV_AGENT_ID: AGENT_ID})
    bad = "not-a-real-tenant"
    with pytest.raises(DispatchConfigError, match="tenant_id must be a UUID") as caught:
        settings({ENV_TENANT_ID: bad, ENV_AGENT_ID: AGENT_ID})
    assert bad not in str(caught.value)


def test_each_call_gets_its_own_room_and_a_suffix_is_never_reused() -> None:
    caller = "+919876543210"
    names = {individual_room_name(caller=caller, suffix=uuid.uuid4().hex) for _ in range(50)}
    assert len(names) == 50
    for name in names:
        assert name.startswith(f"{ROOM_PREFIX}_{caller}_")
        assert SOFTPHONE_NUMBER not in name
    again = individual_room_name(caller=caller, suffix="once")
    assert again == individual_room_name(caller=caller, suffix="once")
    assert again != individual_room_name(caller=caller, suffix="twice")
    with pytest.raises(DispatchConfigError, match="unique suffix"):
        individual_room_name(caller=caller, suffix="")


def test_unknown_number_is_not_on_the_rule() -> None:
    rule = desired_rule()
    assert rule.numbers == (SOFTPHONE_NUMBER,)
    assert "+919876543210" not in rule.numbers


def test_create_request_matches_the_livekit_cli_shape() -> None:
    rule = desired_rule()
    request = rule.create_request()
    assert request["dispatch_rule"] == rule.info()
    assert "sip_dispatch_rule_id" not in request["dispatch_rule"]


def test_empty_list_plans_a_create() -> None:
    rule = desired_rule()
    change = plan_change(rule, [])
    assert change.action == "create"
    assert change.sip_dispatch_rule_id is None


def test_matching_list_plans_noop_when_randomness_and_agents_are_omitted() -> None:
    rule = desired_rule()
    bound = rule.__class__(**{**rule.__dict__, "trunk_ids": ("ST_trunk",)})
    payload = {
        "sip_dispatch_rule_id": "SDR_snake",
        "name": bound.name,
        "metadata": bound.rule_metadata,
        "trunk_ids": ["ST_trunk"],
        "numbers": [bound.number],
        "rule": {"dispatch_rule_individual": {"room_prefix": ROOM_PREFIX}},
        "room_config": {
            "metadata": json.dumps({"tenant_id": TENANT_ID, "agent_id": AGENT_ID}),
            "empty_timeout": bound.empty_timeout,
            "departure_timeout": bound.departure_timeout,
        },
    }
    parsed = parse_dispatch_payload("noise before json " + json.dumps(payload))
    change = plan_change(bound, parsed)
    assert change.action == "noop"
    assert change.line() == f"{RULE_NAME} noop SDR_snake"


def test_metadata_or_number_change_plans_an_update() -> None:
    rule = desired_rule()
    current = listed_from(rule)
    stale = current.rule.__class__(**{**current.rule.__dict__, "number": "+915555555555"})
    change = plan_change(rule, [ListedRule(current.sip_dispatch_rule_id, stale)])
    assert change.action == "update"
    assert "number" in change.changed_fields or "numbers" in change.changed_fields
    assert TENANT_ID not in change.line()


def test_duplicate_name_is_a_conflict() -> None:
    rule = desired_rule()
    with pytest.raises(DispatchConflictError, match="SDR_a, SDR_b"):
        plan_change(rule, [listed_from(rule, "SDR_a"), listed_from(rule, "SDR_b")])


def test_second_apply_makes_no_changes() -> None:
    client = MemoryDispatch()
    first = apply_settings(rules_for(settings()), client)
    assert first[0].action == "create"
    assert client.creates == 1
    assert client.rules[0].rule.trunk_ids == ("ST_trunk",)
    second = apply_settings(rules_for(settings()), client)
    assert second[0].action == "noop"
    assert client.creates == 1
    assert client.updates == 0


def test_dry_run_does_not_write() -> None:
    client = MemoryDispatch()
    change = apply_settings(rules_for(settings()), client, dry_run=True)
    assert change[0].action == "create"
    assert client.creates == 0


def test_missing_trunk_does_not_create_a_rule() -> None:
    client = MemoryDispatch(trunks=[])
    with pytest.raises(DispatchApplyError, match="apply-inbound-trunk.sh"):
        apply_settings(rules_for(settings()), client)
    assert client.creates == 0
    assert client.rules == []


def test_update_then_second_apply_is_noop() -> None:
    rule = desired_rule()
    client = MemoryDispatch()
    stale = rule.__class__(**{**rule.__dict__, "trunk_ids": ("ST_trunk",), "empty_timeout": 300})
    client.rules.append(ListedRule("SDR_existing", stale))
    first = apply_settings(rules_for(settings()), client)
    assert first[0].action == "update"
    assert first[0].changed_fields == ("empty_timeout",)
    second = apply_settings(rules_for(settings()), client)
    assert second[0].action == "noop"
    assert client.updates == 1


def test_lk_client_writes_create_json_without_putting_ids_on_the_command() -> None:
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

    client = LkDispatchClient(runner)
    rule = desired_rule()
    bound = rule.__class__(**{**rule.__dict__, "trunk_ids": ("ST_trunk",)})
    client.create_dispatch(bound)
    client.update_dispatch("SDR_existing", bound)
    create_args, create_body = seen[0]
    update_args, update_body = seen[1]
    assert create_args[:4] == ["lk", "sip", "dispatch", "create"]
    assert create_body == bound.create_request()
    assert TENANT_ID not in " ".join(create_args)
    assert update_args[:6] == ["lk", "sip", "dispatch", "update", "--id", "SDR_existing"]
    assert "dispatch_rule" not in update_body
    assert update_body["room_config"]["metadata"].find(TENANT_ID) >= 0
    assert not Path(create_args[-1]).exists()
    assert not Path(update_args[-1]).exists()


def test_main_dry_run_does_not_print_ids(capsys) -> None:
    code = main(["--config", str(CONFIG), "--dry-run"], client=MemoryDispatch(), env=SAMPLE_ENV)
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == f"dry-run {RULE_NAME} create"
    assert TENANT_ID not in captured.out
    assert AGENT_ID not in captured.err


def test_main_second_run_reports_noop(capsys) -> None:
    client = MemoryDispatch()
    assert main(["--config", str(CONFIG)], client=client, env=SAMPLE_ENV) == 0
    capsys.readouterr()
    assert main(["--config", str(CONFIG)], client=client, env=SAMPLE_ENV) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"{RULE_NAME} noop SDR_created"
    assert client.creates == 1
    assert client.updates == 0


def test_main_scrubs_a_livekit_secret_from_the_error(capsys) -> None:
    class Failing:
        def list_trunks(self):
            raise DispatchApplyError("lk said super-secret-livekit-value")

        def list_dispatch(self):
            raise AssertionError("list")

        def create_dispatch(self, rule):
            raise AssertionError("create")

        def update_dispatch(self, rule_id, rule):
            raise AssertionError("update")

    env = dict(SAMPLE_ENV)
    env["LIVEKIT_API_SECRET"] = "super-secret-livekit-value"
    code = main(["--config", str(CONFIG)], client=Failing(), env=env)
    captured = capsys.readouterr()
    assert code == 1
    assert "super-secret-livekit-value" not in captured.err
    assert "***" in captured.err


def test_duplicate_trunk_name_is_a_conflict() -> None:
    client = MemoryDispatch(trunks=[trunk("ST_a"), trunk("ST_b")])
    with pytest.raises(DispatchConflictError, match="ST_a, ST_b"):
        apply_settings(rules_for(settings()), client)
    assert client.creates == 0


def test_apply_script_points_at_the_dispatch_config() -> None:
    text = APPLY_SCRIPT.read_text(encoding="utf-8")
    assert "voice/sip/apply_dispatch.py" in text
    assert "infra/livekit/dispatch-rule.json" in text
    assert stat.S_IMODE(APPLY_SCRIPT.stat().st_mode) & stat.S_IXUSR
