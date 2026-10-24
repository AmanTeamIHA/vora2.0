"""Dev inbound SIP trunk: render placeholders, then create or replace once.

The desired trunk lives in infra/livekit/inbound-trunk.json. Username, password,
and signalling CIDRs are placeholders. A second apply that already matches does
not call create or update.
"""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "infra" / "livekit" / "inbound-trunk.json"

TRUNK_NAME = "vora2-dev-softphone"
SOFTPHONE_NUMBER = "+910000000000"
DEV_LIVEKIT_HOST = "livekit-dev.hellovora.ai"

PLACEHOLDER_USERNAME = "__SIP_AUTH_USERNAME__"
PLACEHOLDER_PASSWORD = "__SIP_AUTH_PASSWORD__"
PLACEHOLDER_CIDRS = "__SIP_ALLOWED_CIDRS__"

ENV_USERNAME = "VORA_SIP_AUTH_USERNAME"
ENV_PASSWORD = "VORA_SIP_AUTH_PASSWORD"
ENV_CIDRS = "VORA_SIP_ALLOWED_CIDRS"

TOKEN_RE = re.compile(r"__[A-Z0-9_]+__")
NUMBER_RE = re.compile(r"^\+[1-9]\d{7,14}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

TEMPLATE_KEYS = {
    "name",
    "metadata",
    "numbers",
    "allowed_addresses",
    "auth_username",
    "auth_password",
}
COMPARE_FIELDS = (
    "name",
    "numbers",
    "allowed_addresses",
    "auth_username",
    "auth_password",
    "metadata",
)


class TrunkConfigError(ValueError):
    """The trunk file or its environment is not safe to apply."""


class TrunkConflictError(RuntimeError):
    """More than one LiveKit trunk uses this trunk's name."""


class TrunkApplyError(RuntimeError):
    """LiveKit rejected the apply, or the result still differs."""


@dataclass(frozen=True)
class InboundTrunk:
    name: str
    numbers: tuple[str, ...]
    allowed_addresses: tuple[str, ...]
    auth_username: str
    auth_password: str
    metadata: str

    def create_request(self) -> dict:
        return {"trunk": self.trunk_info()}

    def trunk_info(self) -> dict:
        return {
            "name": self.name,
            "metadata": self.metadata,
            "numbers": list(self.numbers),
            "allowed_addresses": list(self.allowed_addresses),
            "auth_username": self.auth_username,
            "auth_password": self.auth_password,
        }


@dataclass(frozen=True)
class ListedTrunk:
    sip_trunk_id: str
    trunk: InboundTrunk
    password_known: bool


@dataclass(frozen=True)
class Change:
    action: str
    name: str
    sip_trunk_id: str | None
    changed_fields: tuple[str, ...]

    def line(self, *, dry_run: bool = False) -> str:
        prefix = "dry-run " if dry_run else ""
        if self.action == "create":
            return f"{prefix}{self.name} create"
        if self.action == "noop":
            return f"{prefix}{self.name} noop {self.sip_trunk_id}"
        fields = ",".join(self.changed_fields)
        return f"{prefix}{self.name} update {self.sip_trunk_id} {fields}"


def load_template(path: Path) -> dict:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TrunkConfigError(f"{path.name} is not valid JSON") from exc
    if not isinstance(loaded, dict):
        raise TrunkConfigError(f"{path.name} must be a JSON object")
    unknown = sorted(set(loaded) - TEMPLATE_KEYS)
    missing = sorted(TEMPLATE_KEYS - set(loaded))
    if unknown or missing:
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if unknown:
            detail.append("unknown " + ", ".join(unknown))
        raise TrunkConfigError(f"{path.name}: " + "; ".join(detail))
    return loaded


def render_trunk(template: Mapping, env: Mapping[str, str]) -> InboundTrunk:
    rendered = _render_value(template, env)
    if not isinstance(rendered, dict):
        raise TrunkConfigError("trunk template must be an object")
    return _desired_trunk(rendered)


def plan_change(desired: InboundTrunk, existing: list[ListedTrunk]) -> Change:
    matches = [item for item in existing if item.trunk.name == desired.name]
    if len(matches) > 1:
        ids = ", ".join(item.sip_trunk_id for item in matches)
        raise TrunkConflictError(f"multiple trunks named {desired.name}: {ids}")
    if not matches:
        return Change("create", desired.name, None, ())
    current = matches[0]
    fields = _differing_fields(desired, current)
    if not fields:
        return Change("noop", desired.name, current.sip_trunk_id, ())
    return Change("update", desired.name, current.sip_trunk_id, fields)


def parse_list_payload(payload: str) -> list[ListedTrunk]:
    text = payload.strip()
    start_candidates = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not start_candidates:
        raise TrunkConfigError("lk list returned no JSON")
    try:
        loaded = json.loads(text[min(start_candidates) :])
    except json.JSONDecodeError as exc:
        raise TrunkConfigError("lk list returned invalid JSON") from exc
    if isinstance(loaded, list):
        items = loaded
    elif isinstance(loaded, dict):
        if "items" in loaded:
            items = loaded["items"] or []
        elif _looks_like_trunk(loaded):
            items = [loaded]
        else:
            items = []
    else:
        raise TrunkConfigError("lk list returned an unexpected JSON type")
    if not isinstance(items, list):
        raise TrunkConfigError("lk list items must be a list")
    parsed: list[ListedTrunk] = []
    for item in items:
        if item is None:
            continue
        if not isinstance(item, dict):
            raise TrunkConfigError("lk list item must be an object")
        parsed.append(_listed_trunk(item))
    return parsed


def require_livekit_env(env: Mapping[str, str]) -> None:
    missing = [
        name
        for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
        if not env.get(name)
    ]
    if missing:
        raise TrunkConfigError("set " + ", ".join(missing))
    parsed = urlparse(env["LIVEKIT_URL"])
    if parsed.scheme not in {"wss", "ws", "https", "http"} or not parsed.hostname:
        raise TrunkConfigError("LIVEKIT_URL must be an http or websocket URL")
    if parsed.hostname != DEV_LIVEKIT_HOST:
        raise TrunkConfigError(f"LIVEKIT_URL host must be {DEV_LIVEKIT_HOST}")


def scrub(text: str, secrets: list[str]) -> str:
    redacted = text
    for secret in secrets:
        if len(secret) >= 4:
            redacted = redacted.replace(secret, "***")
    return redacted


def secret_values(env: Mapping[str, str]) -> list[str]:
    names = ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", ENV_USERNAME, ENV_PASSWORD)
    return [env[name] for name in names if env.get(name)]


def _render_value(value, env: Mapping[str, str]):
    if isinstance(value, str):
        return _render_string(value, env)
    if isinstance(value, list):
        rendered = []
        for item in value:
            child = _render_value(item, env)
            if isinstance(child, list):
                rendered.extend(child)
            else:
                rendered.append(child)
        return rendered
    if isinstance(value, dict):
        return {key: _render_value(child, env) for key, child in value.items()}
    raise TrunkConfigError("trunk template has a non-text value")


def _render_string(value: str, env: Mapping[str, str]) -> str | list[str]:
    if value == PLACEHOLDER_CIDRS:
        raw = env.get(ENV_CIDRS, "")
        if not raw.strip():
            raise TrunkConfigError(f"set {ENV_CIDRS} to replace {PLACEHOLDER_CIDRS}")
        parts = [part.strip() for part in raw.split(",")]
        if any(not part for part in parts):
            raise TrunkConfigError(f"{ENV_CIDRS} has an empty entry")
        return parts
    for token, var in (
        (PLACEHOLDER_USERNAME, ENV_USERNAME),
        (PLACEHOLDER_PASSWORD, ENV_PASSWORD),
    ):
        if value != token:
            continue
        secret = env.get(var, "")
        if secret == "":
            raise TrunkConfigError(f"set {var} to replace {token}")
        if TOKEN_RE.search(secret):
            raise TrunkConfigError("unrendered placeholder")
        return secret
    if TOKEN_RE.search(value):
        raise TrunkConfigError("unrendered placeholder")
    return value


def _desired_trunk(raw: Mapping) -> InboundTrunk:
    name = _text(raw, "name")
    if not NAME_RE.fullmatch(name):
        raise TrunkConfigError("name must be lowercase letters, digits, and hyphens")
    metadata = _text(raw, "metadata")
    if not metadata or len(metadata) > 512:
        raise TrunkConfigError("metadata must be 1 to 512 characters")
    numbers = tuple(sorted(_numbers(_string_list(raw, "numbers"))))
    if not numbers:
        raise TrunkConfigError("numbers must list at least one E.164 number")
    addresses = tuple(_cidrs(_string_list(raw, "allowed_addresses")))
    username = _text(raw, "auth_username")
    if not USERNAME_RE.fullmatch(username):
        raise TrunkConfigError("auth_username must be 1 to 64 letters, digits, or ._-")
    password = _text(raw, "auth_password")
    _check_password(password, username)
    return InboundTrunk(name, numbers, addresses, username, password, metadata)


def _check_password(password: str, username: str) -> None:
    if password == username:
        raise TrunkConfigError("auth_password must not match auth_username")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in password):
        raise TrunkConfigError("auth_password must not contain whitespace or control characters")
    if not 12 <= len(password) <= 128:
        raise TrunkConfigError("auth_password must be 12 to 128 characters")


def _numbers(values: list[str]) -> list[str]:
    parsed = []
    for value in values:
        if not NUMBER_RE.fullmatch(value):
            raise TrunkConfigError(f"number must be E.164, got {value}")
        parsed.append(value)
    if len(parsed) != len(set(parsed)):
        raise TrunkConfigError("numbers contains a duplicate")
    return parsed


def _cidrs(values: list[str]) -> list[str]:
    parsed = []
    for value in values:
        parsed.append(_cidr(value))
    if len(parsed) != len(set(parsed)):
        raise TrunkConfigError("allowed_addresses contains a duplicate")
    return sorted(parsed, key=_cidr_key)


def _cidr(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise TrunkConfigError("allowed address is empty")
    if "/" not in raw:
        raw = f"{raw}/32"
    try:
        network = ipaddress.ip_network(raw, strict=False)
    except ValueError as exc:
        raise TrunkConfigError(f"allowed address is not an IPv4 CIDR: {value}") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise TrunkConfigError("allowed address must be IPv4")
    if network.prefixlen == 0 or network.network_address == ipaddress.IPv4Address("0.0.0.0"):
        raise TrunkConfigError("allowed address must not be 0.0.0.0/0")
    return str(network)


def _cidr_key(cidr: str) -> tuple[int, int]:
    network = ipaddress.ip_network(cidr)
    return (int(network.network_address), network.prefixlen)


def _text(raw: Mapping, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise TrunkConfigError(f"{key} must be a string")
    return value


def _string_list(raw: Mapping, key: str) -> list[str]:
    value = raw.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TrunkConfigError(f"{key} must be a list of strings")
    return value


def _differing_fields(desired: InboundTrunk, listed: ListedTrunk) -> tuple[str, ...]:
    changed = []
    for field in COMPARE_FIELDS:
        if field == "auth_password" and not listed.password_known:
            continue
        if _compare_value(desired, field) != _compare_value(listed.trunk, field):
            changed.append(field)
    return tuple(changed)


def _compare_value(trunk: InboundTrunk, field: str):
    value = getattr(trunk, field)
    if field in {"numbers", "allowed_addresses"}:
        return tuple(sorted(value))
    return value


def _looks_like_trunk(item: Mapping) -> bool:
    keys = ("sipTrunkId", "sip_trunk_id", "name", "authUsername", "auth_username")
    return any(key in item for key in keys)


def _listed_trunk(item: Mapping) -> ListedTrunk:
    trunk_id = item.get("sipTrunkId", item.get("sip_trunk_id"))
    if not isinstance(trunk_id, str) or not trunk_id:
        raise TrunkConfigError("listed trunk is missing sipTrunkId")
    password, password_known = _listed_password(item)
    try:
        addresses = tuple(_cidrs(_as_strings(item, "allowedAddresses", "allowed_addresses")))
    except TrunkConfigError as exc:
        raise TrunkConfigError(f"{trunk_id}: {exc}") from exc
    trunk = InboundTrunk(
        name=_as_text(item, "name"),
        numbers=tuple(sorted(_as_strings(item, "numbers"))),
        allowed_addresses=addresses,
        auth_username=_as_text(item, "authUsername", "auth_username"),
        auth_password=password,
        metadata=_as_text(item, "metadata"),
    )
    return ListedTrunk(trunk_id, trunk, password_known)


def _listed_password(item: Mapping) -> tuple[str, bool]:
    if "authPassword" in item:
        raw = item["authPassword"]
    elif "auth_password" in item:
        raw = item["auth_password"]
    else:
        return "", False
    if not isinstance(raw, str) or raw == "****":
        return "", False
    return raw, True


def _as_text(item: Mapping, *names: str) -> str:
    for name in names:
        if name in item:
            value = item[name]
            if not isinstance(value, str):
                raise TrunkConfigError(f"{name} must be a string")
            return value
    return ""


def _as_strings(item: Mapping, *names: str) -> list[str]:
    for name in names:
        if name not in item or item[name] is None:
            continue
        value = item[name]
        if not isinstance(value, list) or any(not isinstance(entry, str) for entry in value):
            raise TrunkConfigError(f"{name} must be a list of strings")
        return value
    return []
