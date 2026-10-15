import subprocess
import sys

from career_ai.cli import main


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "career_ai", *args],
        capture_output=True,
    )


def test_version_flag():
    result = run_cli("--version")
    assert result.returncode == 0
    assert "career-ai 0.1.0" in result.stdout.decode("utf-8")


def test_no_command_prints_help_and_returns_1(capsys):
    assert main([]) == 1
    assert "usage" in capsys.readouterr().out
