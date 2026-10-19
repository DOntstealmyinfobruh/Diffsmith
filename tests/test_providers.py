import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from diffsmith.agent import Diffsmith
from diffsmith.config import Config
from diffsmith.llm import AnthropicClient, LLMError, OpenAICompatibleClient, make_llm
from test_agent import GOOD


class FakeServer:
    """A tiny OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, replies):
        self.replies = list(replies)  # each: (status, body_dict_or_str)
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                outer.requests.append({
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                    "body": json.loads(self.rfile.read(length)),
                })
                status, body = outer.replies.pop(0)
                data = json.dumps(body).encode() if isinstance(body, dict) else body.encode()
                self.send_response(status)
                if status == 429:
                    self.send_header("Retry-After", "0")
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


def completion(text, prompt_tokens=100, completion_tokens=20):
    return {"choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}}


@pytest.fixture
def server():
    servers = []

    def make(replies):
        s = FakeServer(replies)
        servers.append(s)
        return s

    yield make
    for s in servers:
        s.close()


def test_request_format_and_usage(server):
    srv = server([(200, completion("hello"))])
    client = OpenAICompatibleClient(srv.url, "qwen2.5-coder:7b", api_key="k")
    assert client.complete("SYS", [{"role": "user", "content": "hi"}]) == "hello"
    req = srv.requests[0]
    assert req["path"] == "/v1/chat/completions"
    assert req["auth"] == "Bearer k"
    assert req["body"]["model"] == "qwen2.5-coder:7b"
    assert req["body"]["messages"][0] == {"role": "system", "content": "SYS"}
    assert client.usage.input_tokens == 100 and client.usage.output_tokens == 20


def test_no_auth_header_without_key(server):
    srv = server([(200, completion("ok"))])
    OpenAICompatibleClient(srv.url, "m").complete("s", [])
    assert srv.requests[0]["auth"] is None


def test_retries_rate_limits(server):
    srv = server([(429, '{"error": "slow down"}'), (503, "busy"), (200, completion("done"))])
    slept = []
    client = OpenAICompatibleClient(srv.url, "m", sleep=slept.append)
    assert client.complete("s", []) == "done"
    assert len(srv.requests) == 3 and len(slept) == 2


def test_gives_up_with_clear_error(server):
    srv = server([(401, '{"error": "bad key"}')])
    with pytest.raises(LLMError, match="HTTP 401.*bad key"):
        OpenAICompatibleClient(srv.url, "m", sleep=lambda s: None).complete("s", [])


def test_unreachable_server():
    client = OpenAICompatibleClient("http://127.0.0.1:9/v1", "m", max_retries=1,
                                    sleep=lambda s: None, timeout=2)
    with pytest.raises(LLMError, match="Could not reach"):
        client.complete("s", [])


def test_strips_reasoning(server):
    srv = server([(200, completion("<think>let me see...</think>\nFILE: a.py"))])
    assert OpenAICompatibleClient(srv.url, "m").complete("s", []).strip() == "FILE: a.py"


def test_end_to_end_with_openai_compatible_provider(repo, server):
    srv = server([(200, completion(GOOD))])
    cfg = Config()
    cfg.embedder = "hashing"
    cfg.provider = "openai-compatible"
    cfg.base_url = srv.url
    cfg.model = "local-model"
    result = Diffsmith(repo, cfg).run("reject discount percents outside 0-100")
    assert result.success and result.commit
    # the retrieved code really went to the server
    assert "apply_discount" in srv.requests[0]["body"]["messages"][1]["content"]


# ---- config / factory ------------------------------------------------------

def _cfg(**kw):
    cfg = Config()
    cfg.model = cfg.base_url = cfg.api_key = None
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def test_claude_is_still_the_default(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    cfg = _cfg(provider="anthropic")
    assert cfg.resolved_model == "claude-sonnet-5-5"
    assert isinstance(make_llm(cfg), AnthropicClient)


def test_presets(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    cfg = _cfg(provider="groq", model="llama-3.3-70b-versatile")
    client = make_llm(cfg)
    assert client.url == "https://api.groq.com/openai/v1/chat/completions"
    assert client.api_key == "g"


def test_ollama_needs_no_key(monkeypatch):
    client = make_llm(_cfg(provider="ollama", model="qwen2.5-coder:7b"))
    assert client.url == "http://localhost:11434/v1/chat/completions"
    assert client.api_key is None


@pytest.mark.parametrize("kw,msg", [
    (dict(provider="ollama"), "Set a model"),
    (dict(provider="groq", model="x"), "GROQ_API_KEY"),
    (dict(provider="openai-compatible", model="x"), "base-url"),
    (dict(provider="nope"), "Unknown provider"),
])
def test_config_problems(monkeypatch, kw, msg):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LLMError, match=msg):
        make_llm(_cfg(**kw))
