from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_script_location_loads() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["0009_integrations"]
