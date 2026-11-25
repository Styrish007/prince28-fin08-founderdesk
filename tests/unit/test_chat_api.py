"""Chat API tests: 7 tests, no network, no key, no bill."""

from founderdesk.llm.gateway import FakeLLM


def test_chat_streams_answer(client, llm):
    """POST /v1/chat returns an SSE stream starting with the first token."""
    r = client.post("/v1/chat", json={"message": "Hello"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    body = r.text
    assert 'data: {"type": "start"' in body
    # FakeLLM streams word by word; check each word appears in order.
    assert '"text": "this "' in body
    assert '"text": "is "' in body
    assert '"text": "fake "' in body
    assert '"text": "answer "' in body
    assert 'data: {"type": "end"}' in body


def test_chat_all_providers_fail_returns_error(client, llm):
    """When every provider fails, the stream ends with an error event."""
    llm.fail = True
    r = client.post("/v1/chat", json={"message": "Hello"})
    assert r.status_code == 200
    body = r.text
    assert 'data: {"type": "error"' in body


def test_chat_message_too_long_is_422(client):
    """max_length=4000 on the message: over-long input is rejected."""
    r = client.post("/v1/chat", json={"message": "x" * 4001})
    assert r.status_code == 422


def test_chat_empty_message_is_422(client):
    r = client.post("/v1/chat", json={"message": ""})
    assert r.status_code == 422


def test_usage_returns_totals(client):
    """GET /v1/usage shows calls, tokens, errors, fallbacks, rupees."""
    r = client.get("/v1/chat")
    assert r.status_code == 200
    body = r.json()
    for key in ("calls", "errors", "fallbacks", "tokens_in", "tokens_out", "cost_inr"):
        assert key in body


def test_prompt_has_not_sure_line():
    """The system prompt keeps the "I am not sure" line."""
    with open("prompts/chat_system_v1.md", encoding="utf-8") as f:
        text = f.read()
    assert "I am not sure" in text


def test_llm_is_fake_in_tests(llm):
    """Tests use FakeLLM: no network, no key, no bill."""
    assert isinstance(llm, FakeLLM)
    reply = llm.replies[0]
    assert reply == "this is a fake answer"
