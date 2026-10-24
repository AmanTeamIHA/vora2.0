"""Idempotent demo tenant for the browser talk page. Run once as an ECS task."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from vora_api.db import get_admin_engine
from vora_api.models import Agent, AgentVersion, Plan, Tenant

TENANT_NAME = "Vora Test"
AGENT_NAME = "Demo receptionist"
GREETING = "Namaste! Main Vora hoon. Aapki kya madad kar sakti hoon?"
PROMPT = (
    "You are Vora, a demo real-estate receptionist in Mumbai. "
    "Speak the way a receptionist would, mixing Hindi and English. "
    "Keep replies short. Ask which neighbourhood they want, their budget, "
    "and whether they would like a site visit. Do not invent prices."
)
CONFIG: dict[str, object] = {
    "prompt": PROMPT,
    "greeting": GREETING,
    "language": "hi-IN",
    "languages": ["hi-IN", "en-IN"],
    "voice": "priya",
    "tools": ["end_call"],
    "llm_provider": "sarvam",
    "llm": {"provider": "sarvam"},
}


def seed_demo() -> None:
    with Session(get_admin_engine()) as session:
        tenant = session.scalar(select(Tenant).where(Tenant.name == TENANT_NAME))
        if tenant is None:
            plan = session.scalar(select(Plan).where(Plan.name == "Starter"))
            if plan is None:
                raise SystemExit("Starter plan is missing")
            tenant = Tenant(
                name=TENANT_NAME,
                slug="vora-test",
                legal_name=TENANT_NAME,
                contact_name="Vora",
                contact_email="demo@hellovora.ai",
                status="active",
                plan_id=plan.id,
            )
            session.add(tenant)
            session.flush()
        agent = session.scalar(
            select(Agent).where(Agent.tenant_id == tenant.id, Agent.name == AGENT_NAME)
        )
        if agent is None:
            agent = Agent(tenant_id=tenant.id, name=AGENT_NAME)
            session.add(agent)
            session.flush()
        current = (
            None
            if agent.deployed_version_id is None
            else session.get(AgentVersion, agent.deployed_version_id)
        )
        if current is not None and current.config.get("greeting") == GREETING:
            session.commit()
            return
        if current is not None and current.state == "deployed":
            current.state = "committed"
        version = AgentVersion(
            tenant_id=tenant.id,
            agent_id=agent.id,
            state="deployed",
            config=CONFIG,
        )
        session.add(version)
        session.flush()
        agent.deployed_version_id = version.id
        session.commit()


def main() -> None:
    seed_demo()


if __name__ == "__main__":
    main()
