import pytest

from main import load_node_tokens


def test_load_node_tokens_from_dotenv_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("THINGSBOARD_NODE_01_TOKEN", raising=False)
    (tmp_path / ".env").write_text("THINGSBOARD_NODE_01_TOKEN=test-token\n", encoding="utf-8")
    nodes = [{"id": "node-01", "token_env": "THINGSBOARD_NODE_01_TOKEN"}]

    load_node_tokens(nodes)

    assert nodes[0]["token"] == "test-token"


def test_load_node_tokens_rejects_missing_environment_variable(monkeypatch):
    monkeypatch.delenv("THINGSBOARD_NODE_01_TOKEN", raising=False)
    nodes = [{"id": "node-01", "token_env": "THINGSBOARD_NODE_01_TOKEN"}]

    with pytest.raises(ValueError, match="Missing THINGSBOARD_NODE_01_TOKEN"):
        load_node_tokens(nodes)


def test_load_node_tokens_rejects_static_token():
    nodes = [{"id": "node-01", "token": "do-not-use"}]

    with pytest.raises(ValueError, match="contains a static token"):
        load_node_tokens(nodes)
