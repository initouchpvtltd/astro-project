import os

from app.config import load_env


def _write(tmp_path, text):
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_values_are_loaded(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_KEY", raising=False)
    load_env(_write(tmp_path, "DEMO_KEY=hello\n"))
    assert os.environ["DEMO_KEY"] == "hello"


def test_the_real_environment_always_wins(tmp_path, monkeypatch):
    """Render sets its own variables; a stale .env must never override them."""
    monkeypatch.setenv("DEMO_KEY", "from-the-host")
    applied = load_env(_write(tmp_path, "DEMO_KEY=from-the-file\n"))
    assert os.environ["DEMO_KEY"] == "from-the-host"
    assert "DEMO_KEY" not in applied


def test_comments_blank_lines_and_junk_are_skipped(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_KEY", raising=False)
    applied = load_env(
        _write(
            tmp_path,
            "# a comment\n\n   \nnot-a-pair\n=novalue\nDEMO_KEY=kept\n",
        )
    )
    assert applied == ["DEMO_KEY"]
    assert os.environ["DEMO_KEY"] == "kept"


def test_surrounding_quotes_are_stripped(tmp_path, monkeypatch):
    monkeypatch.delenv("QUOTED", raising=False)
    monkeypatch.delenv("SINGLE", raising=False)
    load_env(_write(tmp_path, 'QUOTED="with spaces"\nSINGLE=\'also fine\'\n'))
    assert os.environ["QUOTED"] == "with spaces"
    assert os.environ["SINGLE"] == "also fine"


def test_values_containing_equals_survive(tmp_path, monkeypatch):
    """Tokens and keys often contain '=', so only the first one separates."""
    monkeypatch.delenv("TOKEN", raising=False)
    load_env(_write(tmp_path, "TOKEN=abc=def==\n"))
    assert os.environ["TOKEN"] == "abc=def=="


def test_a_missing_file_is_not_an_error(tmp_path):
    """Production has no .env at all, and that must be entirely normal."""
    assert load_env(str(tmp_path / "does-not-exist")) == []
