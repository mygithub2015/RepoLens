import pytest


@pytest.fixture
def source_root(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    for name, text in {
        "app.py": "def hello():\n    return 'hello'\n",
        "Example.java": "class Example {}\n",
        "app.js": "function fetchUser() { return 1; }\n",
    }.items():
        (root / name).write_text(text)
    return root
