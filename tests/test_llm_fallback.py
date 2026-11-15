"""The AI provider chain: Gemini first, then Groq. Providers are faked here, so no key or network is needed."""
import pytest
from pydantic import BaseModel

from core import llm, seed
from core.document import TechnicalError


class Answer(BaseModel):
    value: int


class FakeRunnable:
    def __init__(self, behaviour):
        self.behaviour = behaviour

    def invoke(self, messages):
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        return {"parsed": Answer(value=self.behaviour), "raw": None}


class FakeChat:
    def __init__(self, behaviour):
        self.behaviour = behaviour

    def with_structured_output(self, schema, include_raw=True):
        return FakeRunnable(self.behaviour)


@pytest.fixture()
def conn(tmp_path):
    c = seed.reset(tmp_path / "t.db")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)  # skip the backoff pauses in tests


def use_providers(monkeypatch, behaviour):
    """behaviour: {(provider, model): answer_int or Exception}. Records which models were called."""
    calls = []

    def fake_chat(provider, model):
        calls.append((provider, model))
        return FakeChat(behaviour[(provider, model)])
    monkeypatch.setattr(llm, "_chat", fake_chat)
    return calls


def test_no_keys_means_a_clear_technical_error(conn, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert llm.plan(None) == []
    with pytest.raises(TechnicalError, match="GEMINI_API_KEY"):
        llm._invoke_structured(conn, ("h", "t"), llm.plan(None), Answer, lambda p: [("human", "x")])


def test_gemini_used_when_it_works(conn, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    g = llm.models()
    calls = use_providers(monkeypatch, {("gemini", g["primary"]): 7, ("gemini", g["retry"]): 7, ("groq", llm.groq_models()["text"]): 7})
    data, meta = llm._invoke_structured(conn, ("h", "t"), llm.plan(None), Answer, lambda p: [("human", "x")], use_cache=False)
    assert data == {"value": 7} and meta["provider"] == "gemini" and "fallback_from" not in meta
    assert calls == [("gemini", g["primary"])]


def test_gemini_down_then_groq_answers(conn, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    g = llm.models()
    down = RuntimeError("503 UNAVAILABLE: high demand")
    calls = use_providers(monkeypatch, {("gemini", g["primary"]): down, ("gemini", g["retry"]): down,
                                        ("groq", llm.groq_models()["text"]): 42})
    data, meta = llm._invoke_structured(conn, ("h", "t"), llm.plan(None), Answer, lambda p: [("human", "x")], use_cache=False)
    assert data == {"value": 42}
    assert meta["provider"] == "groq" and meta["model"] == llm.groq_models()["text"]
    assert meta["fallback_from"] == f"gemini:{g['primary']}"
    assert [c[0] for c in calls] == ["gemini", "gemini", "groq"]


def test_all_providers_down_raises_the_last_error(conn, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    g = llm.models()
    use_providers(monkeypatch, {("gemini", g["primary"]): RuntimeError("503"), ("gemini", g["retry"]): RuntimeError("503"),
                                ("groq", llm.groq_models()["text"]): RuntimeError("429 rate limit")})
    with pytest.raises(TechnicalError):
        llm._invoke_structured(conn, ("h", "t"), llm.plan(None), Answer, lambda p: [("human", "x")], use_cache=False)


def test_scans_use_the_groq_vision_model_and_text_uses_the_text_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    g, q = llm.models(), llm.groq_models()
    assert ("groq", q["vision"]) in llm.plan(None, vision=True)
    assert ("groq", q["text"]) in llm.plan(None, vision=False)
    assert ("groq", q["text"]) not in llm.plan(None, vision=True)


def test_only_groq_key_still_works(conn, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert llm.available()
    use_providers(monkeypatch, {("groq", llm.groq_models()["text"]): 5})
    data, meta = llm._invoke_structured(conn, ("h", "t"), llm.plan(None), Answer, lambda p: [("human", "x")], use_cache=False)
    assert data == {"value": 5} and meta["provider"] == "groq"


def test_image_format_differs_by_provider():
    g = llm._messages("gemini", "t", [b"x"])[0][1]
    q = llm._messages("groq", "t", [b"x"])[0][1]
    assert isinstance(g[1]["image_url"], str)
    assert isinstance(q[1]["image_url"], dict) and q[1]["image_url"]["url"].startswith("data:image/png;base64,")
