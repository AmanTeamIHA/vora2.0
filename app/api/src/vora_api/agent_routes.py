import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from vora_api.auth_routes import AuthUser, require_user, require_writer
from vora_api.db import admin_transaction, get_admin_engine
from vora_api.livekit_tokens import mint_test_token
from vora_api.models import Agent, AgentVersion, Call, Tenant
from vora_api.plan_routes import require_platform
from vora_api.settings import get_settings

router = APIRouter()
_LANGUAGES = {
    "hi": "hi",
    "en": "en",
    "hi-in": "hi-IN",
    "en-in": "en-IN",
}


class AgentBody(BaseModel):
    tenant_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)


class VersionBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    greeting: str = Field(min_length=1, max_length=500)
    language: str
    voice: str = Field(min_length=1, max_length=80)
    tools: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    llm_provider: str = "sarvam"


class DeployBody(BaseModel):
    version_id: uuid.UUID


class StartCallBody(BaseModel):
    tenant_id: uuid.UUID
    agent_id: uuid.UUID


def _language(value: str) -> str:
    code = _LANGUAGES.get(value.strip().lower())
    if code is None:
        raise HTTPException(status_code=422, detail="Language must be hi, en, hi-IN, or en-IN")
    return code


def _config(body: VersionBody) -> dict[str, object]:
    language = _language(body.language)
    languages = [_language(item) for item in body.languages] or [language]
    provider = body.llm_provider.strip().lower()
    if provider != "sarvam":
        raise HTTPException(status_code=422, detail="LLM provider must be sarvam")
    return {
        "prompt": body.prompt.strip(),
        "greeting": body.greeting.strip(),
        "language": language,
        "languages": list(dict.fromkeys(languages)),
        "voice": body.voice.strip(),
        "tools": body.tools,
        "llm_provider": provider,
        "llm": {"provider": provider},
    }


def require_worker_or_platform(request: Request) -> AuthUser | None:
    """The voice worker authenticates with the internal header. Browsers use a platform session."""
    secret = get_settings().internal_auth_secret
    if secret and request.headers.get("x-vora-internal") == secret:
        return None
    return require_platform(require_user(request))


def _version_view(version: AgentVersion) -> dict[str, object]:
    return {
        "id": str(version.id),
        "agent_id": str(version.agent_id),
        "state": version.state,
        "config": version.config,
    }


def load_deployed(session: Session, agent_id: uuid.UUID) -> tuple[Agent, AgentVersion]:
    """What the worker reads at call start. Drafts are never returned."""
    agent = session.get(Agent, agent_id)
    if agent is None or agent.deployed_version_id is None:
        raise HTTPException(status_code=409, detail="This agent has no deployed version")
    version = session.get(AgentVersion, agent.deployed_version_id)
    if version is None or version.state != "deployed":
        raise HTTPException(status_code=409, detail="This agent has no deployed version")
    return agent, version


@router.post("/admin/agents", status_code=201)
def create_agent(body: AgentBody, actor: AuthUser = Depends(require_writer)) -> dict[str, str]:
    with admin_transaction(
        action="create_agent",
        actor_user_id=actor.id,
        tenant_id=body.tenant_id,
    ) as session:
        if session.get(Tenant, body.tenant_id) is None:
            raise HTTPException(status_code=404, detail="Unknown tenant")
        agent = Agent(tenant_id=body.tenant_id, name=body.name.strip())
        session.add(agent)
        session.flush()
        return {"id": str(agent.id), "name": agent.name}


@router.post("/admin/agents/{agent_id}/versions", status_code=201)
def create_version(
    agent_id: uuid.UUID,
    body: VersionBody,
    actor: AuthUser = Depends(require_writer),
) -> dict[str, object]:
    config = _config(body)
    with admin_transaction(
        action="create_agent_version",
        actor_user_id=actor.id,
        record_audit=False,
    ) as session:
        agent = session.get(Agent, agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Unknown agent")
        version = AgentVersion(
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
            state="draft",
            config=config,
        )
        session.add(version)
        session.info["audit_tenant_id"] = agent.tenant_id
        session.flush()
        return _version_view(version)


@router.post("/admin/agents/{agent_id}/versions/{version_id}/commit")
def commit_version(
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
    actor: AuthUser = Depends(require_writer),
) -> dict[str, str]:
    with admin_transaction(
        action="commit_agent_version",
        actor_user_id=actor.id,
        record_audit=False,
    ) as session:
        version = session.get(AgentVersion, version_id)
        if version is None or version.agent_id != agent_id:
            raise HTTPException(status_code=404, detail="Unknown version")
        if version.state != "draft":
            raise HTTPException(status_code=409, detail="Only a draft can be committed")
        version.state = "committed"
        session.info["audit_tenant_id"] = version.tenant_id
        session.flush()
    return {"id": str(version_id), "state": "committed"}


@router.post("/admin/agents/{agent_id}/deploy")
def deploy_version(
    agent_id: uuid.UUID,
    body: DeployBody,
    actor: AuthUser = Depends(require_writer),
) -> dict[str, str]:
    version_id = body.version_id
    with admin_transaction(
        action="deploy_agent_version",
        actor_user_id=actor.id,
        record_audit=False,
    ) as session:
        agent = session.get(Agent, agent_id)
        version = session.get(AgentVersion, version_id)
        if agent is None or version is None or version.agent_id != agent.id:
            raise HTTPException(status_code=404, detail="Unknown version")
        if version.state == "draft":
            raise HTTPException(status_code=409, detail="Commit the version before deploying it")
        if agent.deployed_version_id and agent.deployed_version_id != version.id:
            previous = session.get(AgentVersion, agent.deployed_version_id)
            if previous is not None and previous.state == "deployed":
                previous.state = "committed"
        version.state = "deployed"
        agent.deployed_version_id = version.id
        session.info["audit_tenant_id"] = agent.tenant_id
        session.flush()
    return {"agent_id": str(agent_id), "deployed_version_id": str(version_id)}


def _agent_view(agent: Agent, tenant_name: str, version: AgentVersion | None) -> dict[str, object]:
    greeting = "" if version is None else str(version.config.get("greeting", ""))
    return {
        "id": str(agent.id),
        "name": agent.name,
        "tenant_id": str(agent.tenant_id),
        "tenant_name": tenant_name,
        "deployed_version_id": None
        if agent.deployed_version_id is None
        else str(agent.deployed_version_id),
        "deployed": agent.deployed_version_id is not None,
        "created_at": agent.created_at.isoformat(),
        "greeting": greeting,
    }


@router.get("/admin/agents")
def list_agents(
    tenant_id: uuid.UUID | None = None, _: AuthUser = Depends(require_platform)
) -> dict[str, list[dict[str, object]]]:
    with Session(get_admin_engine()) as session:
        query = (
            select(Agent, Tenant.name)
            .join(Tenant, Agent.tenant_id == Tenant.id)
            .order_by(Tenant.name, Agent.name)
        )
        if tenant_id is not None:
            query = query.where(Agent.tenant_id == tenant_id)
        rows = session.execute(query).all()
        views = []
        for agent, tenant_name in rows:
            version = (
                None
                if agent.deployed_version_id is None
                else session.get(AgentVersion, agent.deployed_version_id)
            )
            views.append(_agent_view(agent, tenant_name, version))
    return {"agents": views}


@router.get("/admin/agents/{agent_id}")
def get_agent(agent_id: uuid.UUID, _: AuthUser = Depends(require_platform)) -> dict[str, object]:
    with Session(get_admin_engine()) as session:
        agent = session.get(Agent, agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Unknown agent")
        tenant = session.get(Tenant, agent.tenant_id)
        version = (
            None
            if agent.deployed_version_id is None
            else session.get(AgentVersion, agent.deployed_version_id)
        )
        return _agent_view(agent, "" if tenant is None else tenant.name, version)


@router.post("/admin/agents/{agent_id}/test-sessions", status_code=201)
def test_session(
    agent_id: uuid.UUID, actor: AuthUser = Depends(require_platform)
) -> dict[str, str]:
    settings = get_settings()
    if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
        raise HTTPException(status_code=503, detail="LiveKit is not configured")
    room = f"test-{uuid.uuid4()}"
    with admin_transaction(
        action="agent_test_session",
        actor_user_id=actor.id,
        detail=f"agent_id={agent_id} room={room}",
        record_audit=False,
    ) as session:
        agent = session.get(Agent, agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Unknown agent")
        if agent.deployed_version_id is None:
            raise HTTPException(status_code=409, detail="This agent has no deployed version")
        session.info["audit_tenant_id"] = agent.tenant_id
        token = mint_test_token(
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
            identity=actor.email,
            room=room,
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
        )
        tenant_id = str(agent.tenant_id)
    return {
        "room": room,
        "url": settings.livekit_url,
        "token": token,
        "agent_id": str(agent_id),
        "tenant_id": tenant_id,
    }


@router.post("/internal/calls/start", status_code=201)
def start_call(
    body: StartCallBody, _: AuthUser | None = Depends(require_worker_or_platform)
) -> dict[str, object]:
    with admin_transaction(action="start_call", tenant_id=body.tenant_id) as session:
        agent, version = load_deployed(session, body.agent_id)
        if agent.tenant_id != body.tenant_id:
            raise HTTPException(status_code=404, detail="Unknown agent")
        call = Call(
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
            agent_version_id=version.id,
        )
        session.add(call)
        session.flush()
        return {
            "call_id": str(call.id),
            "agent_version_id": str(version.id),
            "config": version.config,
        }


@router.get("/internal/agents/{agent_id}/deployed")
def deployed(agent_id: uuid.UUID, _: AuthUser = Depends(require_platform)) -> dict[str, object]:
    with Session(get_admin_engine()) as session:
        _agent, version = load_deployed(session, agent_id)
        return _version_view(version)


@router.get("/admin/calls")
def list_calls(
    tenant_id: uuid.UUID | None = None, _: AuthUser = Depends(require_platform)
) -> dict[str, list[dict[str, str]]]:
    with Session(get_admin_engine()) as session:
        query = (
            select(Call, Agent.name)
            .join(Agent, Agent.id == Call.agent_id)
            .order_by(Call.created_at.desc())
            .limit(50)
        )
        if tenant_id is not None:
            query = query.where(Call.tenant_id == tenant_id)
        rows = session.execute(query).all()
    return {
        "calls": [
            {
                "id": str(call.id),
                "agent_name": agent_name,
                "created_at": call.created_at.isoformat(),
            }
            for call, agent_name in rows
        ]
    }


@router.get("/admin/calls/{call_id}")
def get_call(call_id: uuid.UUID, _: AuthUser = Depends(require_platform)) -> dict[str, str]:
    with Session(get_admin_engine()) as session:
        call = session.get(Call, call_id)
        if call is None:
            raise HTTPException(status_code=404, detail="Unknown call")
        version = session.get(AgentVersion, call.agent_version_id)
        greeting = "" if version is None else str(version.config.get("greeting", ""))
        return {
            "id": str(call.id),
            "agent_version_id": str(call.agent_version_id),
            "greeting": greeting,
        }
