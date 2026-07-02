import os
from pathlib import Path

from commission_ingestion.env import find_dotenv, load_dotenv


def test_load_dotenv_sets_missing_keys(tmp_path: Path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\nNEO4J_PASSWORD=newPassword\nANTHROPIC_API_KEY=sk-test-123\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    load_dotenv(env)

    assert os.environ["NEO4J_PASSWORD"] == "newPassword"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-test-123"


def test_shell_export_wins_over_dotenv(tmp_path: Path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("NEO4J_PASSWORD=fromfile\n", encoding="utf-8")
    monkeypatch.setenv("NEO4J_PASSWORD", "fromshell")

    load_dotenv(env)

    assert os.environ["NEO4J_PASSWORD"] == "fromshell"


def test_strips_quotes_and_ignores_blank_lines(tmp_path: Path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('\n\nFOO="bar baz"\n\n', encoding="utf-8")
    monkeypatch.delenv("FOO", raising=False)

    load_dotenv(env)

    assert os.environ["FOO"] == "bar baz"


def test_find_dotenv_returns_none_when_absent(tmp_path: Path):
    assert find_dotenv(tmp_path / "nope" / "deep") is None
