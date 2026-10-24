from dataclasses import dataclass


class UnsupportedLlmProvider(Exception):
    """The agent config named an LLM provider this worker does not run."""

    def __init__(self, provider: str) -> None:
        super().__init__(provider)
        self.provider = provider


_LANGUAGE = {
    "hi": "hi-IN",
    "en": "en-IN",
    "hi-in": "hi-IN",
    "en-in": "en-IN",
}


@dataclass(frozen=True)
class AgentConfig:
    greeting: str
    prompt: str
    language: str
    languages: tuple[str, ...]
    voice: str
    llm_provider: str
    tools: tuple[str, ...]

    @property
    def code_mix(self) -> bool:
        return "hi-IN" in self.languages and "en-IN" in self.languages


def _language(value: object) -> str:
    code = str(value).strip()
    mapped = _LANGUAGE.get(code.lower())
    if mapped is None:
        raise ValueError(f"unsupported language {code}")
    return mapped


def _provider(raw: dict[str, object]) -> str:
    nested = raw.get("llm")
    if isinstance(nested, dict) and nested.get("provider"):
        return str(nested["provider"]).strip().lower()
    if raw.get("llm_provider"):
        return str(raw["llm_provider"]).strip().lower()
    raise UnsupportedLlmProvider("")


def load_agent_config(raw: dict[str, object]) -> AgentConfig:
    provider = _provider(raw)
    if provider != "sarvam":
        raise UnsupportedLlmProvider(provider)
    language = _language(raw.get("language", "hi-IN"))
    listed = raw.get("languages")
    if isinstance(listed, list) and listed:
        languages = tuple(dict.fromkeys(_language(item) for item in listed))
    else:
        languages = (language,)
    tools = raw.get("tools")
    tool_names = tuple(str(item) for item in tools) if isinstance(tools, list) else ()
    return AgentConfig(
        greeting=str(raw.get("greeting", "")).strip(),
        prompt=str(raw.get("prompt", "")).strip(),
        language=language if language in languages else languages[0],
        languages=languages,
        voice=str(raw.get("voice", "")).strip(),
        llm_provider=provider,
        tools=tool_names,
    )
