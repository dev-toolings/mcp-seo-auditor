"""Configuration loading safety tests."""

from app.core.config import Settings


def test_dotenv_values_are_not_executed_as_shell(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    marker = tmp_path / "executed"
    env_file = tmp_path / ".env.seo"
    value = f"$(touch {marker})"
    env_file.write_text(f"MCP_AUTH_TOKEN='{value}'\n", encoding="utf-8")

    loaded = Settings(_env_file=env_file)

    assert loaded.MCP_AUTH_TOKEN.get_secret_value() == value
    assert not marker.exists()
