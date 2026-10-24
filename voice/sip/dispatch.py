"""Dev SIP dispatch: called number → room metadata and an agent job.

The map lives in infra/livekit/dispatch-rule.json. Tenant and agent ids are
placeholders filled from the environment, because seed_demo assigns them in
Postgres and this lane does not read the database. A second apply that already
matches does not call create or update.

livekit-server v1.13.10 names an individual-rule room
``{room_prefix}_{caller}_{random}``. With room_prefix ``call-`` that is
``call-_<caller>_<random>``. The random suffix is new on every call, so the
room is never reused. That server has no ``call-{uuid}`` template.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from trunk import NAME_RE, NUMBER_RE

logger = logging.getLogger("vora.sip")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "infra" / "livekit" / "dispatch-rule.json"

TRUNK_NAME = "vora2-dev-softphone"
RULE_NAME = "vora2-dev-softphone"
ROOM_PREFIX = "call-"
SOFTPHONE_NUMBER = "+910000000000"
TENANT_NAME = "Vora Test"
AGENT_NAME = "Demo receptionist"
WORKER_AGENT_NAME = ""

PLACEHOLDER_TENANT_ID = "__VORA_TEST_TENANT_ID__"
PLACEHOLDER_AGENT_ID = "__VORA_TEST_AGENT_ID__"
ENV_TENANT_ID = "VORA_TEST_TENANT_ID"
ENV_AGENT_ID = "VORA_TEST_AGENT_ID"

TOKEN_RE = re.compile(r"__[A-Z0-9_]+__")
WORKER_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{0,64}$")

TEMPLATE_KEYS = {
    "trunk_name",
    "worker_agent_name",
    "room_prefix",
    "empty_timeout",
    "departure_timeout",
    "metadata",
    "routes",
}
ROUTE_KEYS = {
    "name",
    "number",
    "tenant_name",
    "agent_name",
    "tenant_id",
    "agent_id",
}
COMPARE_FIELDS = (
    "kind",
    "trunk_ids",
    "numbers",
    "room_prefix",
    "no_randomness",
    "room_metadata",
    "worker_agent_name",
    "empty_timeout",
    "departure_timeout",
    "rule_metadata",
)


class DispatchConfigError(ValueError):
    """The dispatch file or its environment is not safe to apply."""


class DispatchConflictError(RuntimeError):
    """More than one LiveKit rule or trunk uses this name."""


class DispatchApplyError(RuntimeError):
    """LiveKit rejected the apply, or the result still differs."""


@dataclass(frozen=True)
class NumberRoute:
    name: str
    number: str
    tenant_name: str
    agent_name: str
    tenant_id: str
    agent_id: str

    @property
    def room_metadata(self) -> dict[str, str]:
        return {"tenant_id": self.tenant_id, "agent_id": self.agent_id}


@dataclass(frozen=True)
class DispatchSettings:
    trunk_name: str
    worker_agent_name: str
    room_prefix: str
    empty_timeout: int
    departure_timeout: int
    rule_metadata: str
    routes: tuple[NumberRoute, ...]


@dataclass(frozen=True)
class DispatchRule:
    """One LiveKit dispatch rule for a single called number."""

    name: str
    trunk_name: str
    trunk_ids: tuple[str, ...]
    number: str
    room_prefix: str
    no_randomness: bool
    kind: str
    tenant_id: str
    agent_id: str
    tenant_name: str
    agent_name: str
    worker_agent_name: str
    empty_timeout: int
    departure_timeout: int
    rule_metadata: str
    metadata_blob: str = ""

    @property
    def numbers(self) -> tuple[str, ...]:
        return (self.number,)

    @property
    def room_metadata(self) -> dict[str, str]:
        return {"tenant_id": self.tenant_id, "agent_id": self.agent_id}

    def create_request(self) -> dict:
        return {"dispatch_rule": self.info()}

    def info(self) -> dict:
        # `numbers` is the called number. `inbound_numbers` would filter the
        # caller instead, so it stays unset and every caller of this number matches.
        return {
            "name": self.name,
            "metadata": self.rule_metadata,
            "trunk_ids": list(self.trunk_ids),
            "numbers": [self.number],
            "rule": {
                "dispatch_rule_individual": {
                    "room_prefix": self.room_prefix,
                    "no_randomness": self.no_randomness,
                }
            },
            "room_config": {
                "metadata": _metadata_json(self.room_metadata),
                "empty_timeout": self.empty_timeout,
                "departure_timeout": self.departure_timeout,
                "agents": [{"agent_name": self.worker_agent_name}],
            },
        }


@dataclass(frozen=True)
class ListedRule:
    sip_dispatch_rule_id: str
    rule: DispatchRule


@dataclass(frozen=True)
class Change:
    action: str
    name: str
    sip_dispatch_rule_id: str | None
    changed_fields: tuple[str, ...]

    def line(self, *, dry_run: bool = False) -> str:
        prefix = "dry-run " if dry_run else ""
        if self.action == "create":
            return f"{prefix}{self.name} create"
        if self.action == "noop":
            return f"{prefix}{self.name} noop {self.sip_dispatch_rule_id}"
        fields = ",".join(self.changed_fields)
        return f"{prefix}{self.name} update {self.sip_dispatch_rule_id} {fields}"


def load_template(path: Path) -> dict:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DispatchConfigError(f"{path.name} is not valid JSON") from exc
    if not isinstance(loaded, dict):
        raise DispatchConfigError(f"{path.name} must be a JSON object")
    _exact_keys(loaded, TEMPLATE_KEYS, path.name)
    routes = loaded.get("routes")
    if not isinstance(routes, list) or not routes:
        raise DispatchConfigError(f"{path.name}: routes must list at least one number")
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            raise DispatchConfigError(f"{path.name}: routes[{index}] must be an object")
        _exact_keys(route, ROUTE_KEYS, f"{path.name} routes[{index}]")
    return loaded


def read_settings(template: Mapping) -> DispatchSettings:
    """The static map, including id placeholders. Lookup uses this."""
    routes = []
    for raw in template["routes"]:
        routes.append(
            NumberRoute(
                name=_route_name(raw),
                number=_number(raw),
                tenant_name=_label(raw, "tenant_name"),
                agent_name=_label(raw, "agent_name"),
                tenant_id=_id_field(raw, "tenant_id"),
                agent_id=_id_field(raw, "agent_id"),
            )
        )
    _unique(routes)
    return DispatchSettings(
        trunk_name=_name(_text(template, "trunk_name"), "trunk_name"),
        worker_agent_name=_worker_name(template.get("worker_agent_name")),
        room_prefix=_room_prefix(_text(template, "room_prefix")),
        empty_timeout=_timeout(template, "empty_timeout"),
        departure_timeout=_timeout(template, "departure_timeout"),
        rule_metadata=_rule_metadata(_text(template, "metadata")),
        routes=tuple(routes),
    )


def render_settings(template: Mapping, env: Mapping[str, str]) -> DispatchSettings:
    settings = read_settings(template)
    rendered = tuple(_render_route(route, env) for route in settings.routes)
    return DispatchSettings(
        settings.trunk_name,
        settings.worker_agent_name,
        settings.room_prefix,
        settings.empty_timeout,
        settings.departure_timeout,
        settings.rule_metadata,
        rendered,
    )


def lookup_number(settings: DispatchSettings, number: str) -> NumberRoute | None:
    """Return the route for a called number.

    An unknown number is logged and returns None. No room is allocated.
    """
    for route in settings.routes:
        if route.number == number:
            return route
    logger.info("rejected unknown called number %s; no room created", number)
    return None


def rules_for(settings: DispatchSettings) -> tuple[DispatchRule, ...]:
    return tuple(_rule_from(settings, route, trunk_ids=()) for route in settings.routes)


def bind_trunk(
    rules: tuple[DispatchRule, ...] | list[DispatchRule],
    trunks: list,
) -> tuple[DispatchRule, ...]:
    bound = []
    for rule in rules:
        matches = [item for item in trunks if item.trunk.name == rule.trunk_name]
        if len(matches) > 1:
            ids = ", ".join(item.sip_trunk_id for item in matches)
            raise DispatchConflictError(f"multiple inbound trunks named {rule.trunk_name}: {ids}")
        if not matches:
            raise DispatchApplyError(
                f"inbound trunk {rule.trunk_name} is not on this LiveKit; "
                "run apply-inbound-trunk.sh first"
            )
        trunk_id = matches[0].sip_trunk_id
        if not trunk_id:
            raise DispatchApplyError(f"inbound trunk {rule.trunk_name} is missing an id")
        bound.append(_replace_trunk(rule, (trunk_id,)))
    return tuple(bound)


def individual_room_name(*, caller: str, suffix: str, prefix: str = ROOM_PREFIX) -> str:
    """The room name livekit-server v1.13.10 actually creates.

    Formula in protocol sip.EvaluateDispatchRule: ``{prefix}_{caller}_{suffix}``
    when the prefix is set and randomness is on. The suffix has to be new per
    call. An empty suffix would put later calls in the same room.
    """
    if prefix != ROOM_PREFIX:
        raise DispatchConfigError(f"room prefix must be {ROOM_PREFIX}")
    if not caller or not suffix:
        raise DispatchConfigError("a call room needs a caller and a unique suffix")
    return f"{prefix}_{caller}_{suffix}"


def plan_change(desired: DispatchRule, existing: list[ListedRule]) -> Change:
    matches = [item for item in existing if item.rule.name == desired.name]
    if len(matches) > 1:
        ids = ", ".join(item.sip_dispatch_rule_id for item in matches)
        raise DispatchConflictError(f"multiple dispatch rules named {desired.name}: {ids}")
    if not matches:
        return Change("create", desired.name, None, ())
    current = matches[0]
    fields = _differing_fields(desired, current.rule)
    if not fields:
        return Change("noop", desired.name, current.sip_dispatch_rule_id, ())
    return Change("update", desired.name, current.sip_dispatch_rule_id, fields)


def parse_dispatch_payload(payload: str) -> list[ListedRule]:
    loaded = _json_payload(payload)
    if isinstance(loaded, list):
        items = loaded
    elif isinstance(loaded, dict):
        if "items" in loaded:
            items = loaded["items"] or []
        elif _looks_like_rule(loaded):
            items = [loaded]
        else:
            items = []
    else:
        raise DispatchConfigError("lk dispatch list returned an unexpected JSON type")
    if not isinstance(items, list):
        raise DispatchConfigError("lk dispatch list items must be a list")
    parsed: list[ListedRule] = []
    for item in items:
        if item is None:
            continue
        if not isinstance(item, dict):
            raise DispatchConfigError("lk dispatch list item must be an object")
        parsed.append(_listed_rule(item))
    return parsed


def _render_route(route: NumberRoute, env: Mapping[str, str]) -> NumberRoute:
    return NumberRoute(
        route.name,
        route.number,
        route.tenant_name,
        route.agent_name,
        _render_uuid(route.tenant_id, env, "tenant_id"),
        _render_uuid(route.agent_id, env, "agent_id"),
    )


def _render_uuid(value: str, env: Mapping[str, str], field: str) -> str:
    if TOKEN_RE.fullmatch(value):
        var = value[2:-2]
        raw = env.get(var, "")
        if raw == "":
            raise DispatchConfigError(f"set {var} to replace {value}")
        if TOKEN_RE.search(raw):
            raise DispatchConfigError("unrendered placeholder")
        return _uuid(raw, field)
    if TOKEN_RE.search(value):
        raise DispatchConfigError("unrendered placeholder")
    return _uuid(value, field)


def _rule_from(
    settings: DispatchSettings,
    route: NumberRoute,
    trunk_ids: tuple[str, ...],
) -> DispatchRule:
    return DispatchRule(
        name=route.name,
        trunk_name=settings.trunk_name,
        trunk_ids=trunk_ids,
        number=route.number,
        room_prefix=settings.room_prefix,
        no_randomness=False,
        kind="individual",
        tenant_id=route.tenant_id,
        agent_id=route.agent_id,
        tenant_name=route.tenant_name,
        agent_name=route.agent_name,
        worker_agent_name=settings.worker_agent_name,
        empty_timeout=settings.empty_timeout,
        departure_timeout=settings.departure_timeout,
        rule_metadata=settings.rule_metadata,
    )


def _replace_trunk(rule: DispatchRule, trunk_ids: tuple[str, ...]) -> DispatchRule:
    return DispatchRule(
        rule.name,
        rule.trunk_name,
        trunk_ids,
        rule.number,
        rule.room_prefix,
        rule.no_randomness,
        rule.kind,
        rule.tenant_id,
        rule.agent_id,
        rule.tenant_name,
        rule.agent_name,
        rule.worker_agent_name,
        rule.empty_timeout,
        rule.departure_timeout,
        rule.rule_metadata,
    )


def _unique(routes: list[NumberRoute]) -> None:
    names = [route.name for route in routes]
    numbers = [route.number for route in routes]
    if len(names) != len(set(names)):
        raise DispatchConfigError("routes contains a duplicate name")
    if len(numbers) != len(set(numbers)):
        raise DispatchConfigError("routes contains a duplicate number")


def _route_name(raw: Mapping) -> str:
    return _name(_text(raw, "name"), "name")


def _name(value: str, field: str) -> str:
    if TOKEN_RE.search(value):
        raise DispatchConfigError("unrendered placeholder")
    if not NAME_RE.fullmatch(value):
        raise DispatchConfigError(f"{field} must be lowercase letters, digits, and hyphens")
    return value


def _number(raw: Mapping) -> str:
    value = _text(raw, "number")
    if TOKEN_RE.search(value):
        raise DispatchConfigError("unrendered placeholder")
    if not NUMBER_RE.fullmatch(value):
        raise DispatchConfigError(f"number must be E.164, got {value}")
    return value


def _label(raw: Mapping, field: str) -> str:
    value = _text(raw, field).strip()
    if not value or len(value) > 200:
        raise DispatchConfigError(f"{field} must be 1 to 200 characters")
    if TOKEN_RE.search(value):
        raise DispatchConfigError("unrendered placeholder")
    return value


def _id_field(raw: Mapping, field: str) -> str:
    value = _text(raw, field).strip()
    if not value:
        raise DispatchConfigError(f"{field} must be a UUID or a placeholder")
    if TOKEN_RE.fullmatch(value):
        return value
    if TOKEN_RE.search(value):
        raise DispatchConfigError("unrendered placeholder")
    return _uuid(value, field)


def _uuid(value: str, field: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise DispatchConfigError(f"{field} must be a UUID") from exc
    return str(parsed)


def _worker_name(value: object) -> str:
    if not isinstance(value, str) or not WORKER_NAME_RE.fullmatch(value):
        raise DispatchConfigError("worker_agent_name must be empty or letters, digits, or ._-")
    if TOKEN_RE.search(value):
        raise DispatchConfigError("unrendered placeholder")
    return value


def _room_prefix(value: str) -> str:
    if value != ROOM_PREFIX:
        raise DispatchConfigError(f"room_prefix must be {ROOM_PREFIX}")
    return value


def _timeout(raw: Mapping, field: str) -> int:
    value = raw.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise DispatchConfigError(f"{field} must be an integer")
    if not 1 <= value <= 300:
        raise DispatchConfigError(f"{field} must be 1 to 300 seconds")
    return value


def _rule_metadata(value: str) -> str:
    if TOKEN_RE.search(value):
        raise DispatchConfigError("unrendered placeholder")
    if not value or len(value) > 512:
        raise DispatchConfigError("metadata must be 1 to 512 characters")
    return value


def _text(raw: Mapping, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise DispatchConfigError(f"{key} must be a string")
    return value


def _exact_keys(raw: Mapping, allowed: set[str], where: str) -> None:
    unknown = sorted(set(raw) - allowed)
    missing = sorted(allowed - set(raw))
    if unknown or missing:
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if unknown:
            detail.append("unknown " + ", ".join(unknown))
        raise DispatchConfigError(f"{where}: " + "; ".join(detail))


def _metadata_json(metadata: Mapping[str, str]) -> str:
    return json.dumps(dict(metadata), separators=(",", ":"), sort_keys=True)


def _differing_fields(desired: DispatchRule, listed: DispatchRule) -> tuple[str, ...]:
    changed = []
    for field in COMPARE_FIELDS:
        if _compare_value(desired, field) != _compare_value(listed, field):
            changed.append(field)
    return tuple(changed)


def _compare_value(rule: DispatchRule, field: str):
    if field == "room_metadata":
        if rule.metadata_blob:
            return rule.metadata_blob
        return _metadata_json(rule.room_metadata)
    if field == "trunk_ids":
        return tuple(sorted(rule.trunk_ids))
    if field == "numbers":
        return tuple(sorted(rule.numbers))
    if field == "worker_agent_name":
        return (rule.worker_agent_name,)
    return getattr(rule, field)


def _json_payload(payload: str):
    text = payload.strip()
    start_candidates = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not start_candidates:
        raise DispatchConfigError("lk dispatch list returned no JSON")
    try:
        return json.loads(text[min(start_candidates) :])
    except json.JSONDecodeError as exc:
        raise DispatchConfigError("lk dispatch list returned invalid JSON") from exc


def _looks_like_rule(item: Mapping) -> bool:
    keys = ("sipDispatchRuleId", "sip_dispatch_rule_id", "name", "rule")
    return any(key in item for key in keys)


def _listed_rule(item: Mapping) -> ListedRule:
    rule_id = item.get("sipDispatchRuleId", item.get("sip_dispatch_rule_id"))
    if not isinstance(rule_id, str) or not rule_id:
        raise DispatchConfigError("listed dispatch rule is missing sipDispatchRuleId")
    kind, prefix, randomness = _listed_kind(item)
    metadata = _listed_room_metadata(item)
    timeouts = _listed_timeouts(item)
    rule = DispatchRule(
        name=_as_text(item, "name"),
        trunk_name="",
        trunk_ids=tuple(sorted(_as_strings(item, "trunkIds", "trunk_ids"))),
        number=_listed_number(item),
        room_prefix=prefix,
        no_randomness=randomness,
        kind=kind,
        tenant_id=metadata.get("tenant_id", ""),
        agent_id=metadata.get("agent_id", ""),
        tenant_name="",
        agent_name="",
        worker_agent_name=_listed_worker(item),
        empty_timeout=timeouts[0],
        departure_timeout=timeouts[1],
        rule_metadata=_as_text(item, "metadata"),
        metadata_blob=_listed_metadata_blob(item),
    )
    return ListedRule(rule_id, rule)


def _listed_kind(item: Mapping) -> tuple[str, str, bool]:
    rule = item.get("rule")
    if not isinstance(rule, dict):
        return "unknown", "", True
    individual = rule.get("dispatchRuleIndividual", rule.get("dispatch_rule_individual"))
    if isinstance(individual, dict):
        prefix = individual.get("roomPrefix", individual.get("room_prefix", ""))
        if not isinstance(prefix, str):
            prefix = ""
        randomness = individual.get("noRandomness", individual.get("no_randomness", False))
        return "individual", prefix, bool(randomness)
    direct = rule.get("dispatchRuleDirect", rule.get("dispatch_rule_direct"))
    if isinstance(direct, dict):
        room = direct.get("roomName", direct.get("room_name", ""))
        return "direct", room if isinstance(room, str) else "", True
    return "unknown", "", True


def _listed_metadata_blob(item: Mapping) -> str:
    config = item.get("roomConfig", item.get("room_config"))
    if not isinstance(config, dict):
        return "{}"
    raw = config.get("metadata", "")
    if not isinstance(raw, str) or not raw:
        return "{}"
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return "invalid"
    if not isinstance(loaded, dict):
        return "invalid"
    for key, value in loaded.items():
        if not isinstance(key, str) or not isinstance(value, str):
            return "invalid"
    return _metadata_json(loaded)


def _listed_room_metadata(item: Mapping) -> dict[str, str]:
    blob = _listed_metadata_blob(item)
    if blob in {"{}", "invalid"}:
        return {}
    loaded = json.loads(blob)
    tenant = loaded.get("tenant_id", "")
    agent = loaded.get("agent_id", "")
    if not isinstance(tenant, str) or not isinstance(agent, str):
        return {}
    return {"tenant_id": tenant, "agent_id": agent}


def _listed_timeouts(item: Mapping) -> tuple[int, int]:
    config = item.get("roomConfig", item.get("room_config"))
    if not isinstance(config, dict):
        return 0, 0
    return _as_int(config, "emptyTimeout", "empty_timeout"), _as_int(
        config, "departureTimeout", "departure_timeout"
    )


def _listed_worker(item: Mapping) -> str:
    config = item.get("roomConfig", item.get("room_config"))
    if not isinstance(config, dict) or "agents" not in config or config.get("agents") in (None, []):
        # livekit-server dispatches one unnamed worker when agents is empty.
        return ""
    agents = config["agents"]
    if not isinstance(agents, list) or not agents or not isinstance(agents[0], dict):
        return "invalid"
    if len(agents) != 1:
        names = []
        for agent in agents:
            if isinstance(agent, dict):
                name = agent.get("agentName", agent.get("agent_name", ""))
                names.append(name if isinstance(name, str) else "invalid")
            else:
                names.append("invalid")
        return ",".join(names)
    name = agents[0].get("agentName", agents[0].get("agent_name", ""))
    if not isinstance(name, str):
        return "invalid"
    return name


def _listed_number(item: Mapping) -> str:
    numbers = _as_strings(item, "numbers")
    if len(numbers) != 1:
        return ",".join(numbers)
    return numbers[0]


def _as_text(item: Mapping, *names: str) -> str:
    for name in names:
        if name in item:
            value = item[name]
            if not isinstance(value, str):
                raise DispatchConfigError(f"{name} must be a string")
            return value
    return ""


def _as_strings(item: Mapping, *names: str) -> list[str]:
    for name in names:
        if name not in item or item[name] is None:
            continue
        value = item[name]
        if not isinstance(value, list) or any(not isinstance(entry, str) for entry in value):
            raise DispatchConfigError(f"{name} must be a list of strings")
        return value
    return []


def _as_int(item: Mapping, *names: str) -> int:
    for name in names:
        if name not in item or item[name] is None:
            continue
        value = item[name]
        if isinstance(value, bool) or not isinstance(value, int):
            raise DispatchConfigError(f"{name} must be an integer")
        return value
    return 0
