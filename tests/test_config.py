import json
from pathlib import Path

import pytest

from career_ai.cli import main
from career_ai.config import ConfigError, load_config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("CAREER_DATA_DIR", raising=False)


def make_repo(tmp_path: Path, env_value: str) -> Path:
    repo = tmp_path / "career-ai"
    repo.mkdir()
    (repo / ".env").write_text(f"CAREER_DATA_DIR={env_value}\n", encoding="utf-8")
    return repo


def test_relative_path_resolves_from_repo_root_not_cwd(tmp_path, monkeypatch):
    data = tmp_path / "career-ai-data"
    data.mkdir()
    repo = make_repo(tmp_path, "../career-ai-data")
    elsewhere = repo / "src" / "deep"
    elsewhere.mkdir(parents=True)
    monkeypatch.chdir(elsewhere)

    assert load_config(repo).data_dir == data.resolve()


def test_environment_variable_wins_over_dotenv(tmp_path, monkeypatch):
    other = tmp_path / "other-data"
    other.mkdir()
    repo = make_repo(tmp_path, "../career-ai-data")
    monkeypatch.setenv("CAREER_DATA_DIR", str(other))

    assert load_config(repo).data_dir == other.resolve()


def test_missing_setting_raises_with_guidance(tmp_path):
    repo = tmp_path / "career-ai"
    repo.mkdir()
    with pytest.raises(ConfigError, match=".env.example"):
        load_config(repo)


def test_missing_folder_raises_with_init_hint(tmp_path):
    repo = make_repo(tmp_path, "../없는-폴더")
    with pytest.raises(ConfigError, match="init-data"):
        load_config(repo)


def test_config_command_prints_data_dir(tmp_path, monkeypatch, capsys):
    data = tmp_path / "데이터"
    data.mkdir()
    monkeypatch.setenv("CAREER_DATA_DIR", str(data))

    assert main(["config"]) == 0
    assert json.loads(capsys.readouterr().out)["data_dir"] == str(data.resolve())
