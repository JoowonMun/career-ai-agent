from career_ai.cli import main
from career_ai.data_init import TEMPLATE_DIR, init_data


def test_template_has_expected_files():
    for rel in ["preferences.yaml", "experience/profile.md", "experience/career-master.md",
                "experience/projects/_template.md", "applications/_inbox/.gitkeep"]:
        assert (TEMPLATE_DIR / rel).is_file(), rel


def test_creates_skeleton(tmp_path):
    result = init_data(tmp_path / "career-ai-data")
    assert "experience/profile.md" in result["created"]
    assert result["skipped"] == []
    assert (tmp_path / "career-ai-data" / "companies" / ".gitkeep").exists()


def test_never_overwrites_existing_files(tmp_path):
    target = tmp_path / "career-ai-data"
    (target / "experience").mkdir(parents=True)
    mine = target / "experience" / "profile.md"
    mine.write_text("내가 쓴 내용", encoding="utf-8")

    result = init_data(target)

    assert mine.read_text(encoding="utf-8") == "내가 쓴 내용"
    assert "experience/profile.md" in result["skipped"]
    assert "experience/career-master.md" in result["created"]


def test_cli_resolves_relative_target_from_repo_root(tmp_path, monkeypatch):
    repo = tmp_path / "career-ai"
    (repo / "src").mkdir(parents=True)
    monkeypatch.setattr("career_ai.cli.REPO_ROOT", repo)
    monkeypatch.chdir(repo / "src")

    assert main(["init-data", "../career-ai-data"]) == 0
    assert (tmp_path / "career-ai-data" / "experience" / "profile.md").exists()
    assert not (repo / "career-ai-data").exists()


def test_cli(tmp_path, capsys):
    assert main(["init-data", str(tmp_path / "d")]) == 0
    assert "created" in capsys.readouterr().out
