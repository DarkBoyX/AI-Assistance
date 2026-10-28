import json, threading
import httpx, numpy as np, pytest
from vega.config import Settings
from vega.storage import Storage
from vega.ai.providers import OpenAICompat, AnthropicProvider, ProviderError, LLMResponse, ToolCall
from vega.ai.agent import Agent
from vega.tools import load_all, ToolContext
from vega.voice.audio_in import Segmenter
from vega.controller import parse_yes_no


@pytest.fixture
def env(tmp_path):
    s = Settings(tmp_path / "s.json"); st = Storage(tmp_path / "db")
    return s, st, load_all(tmp_path / "plug")


def test_settings_roundtrip_and_merge(tmp_path):
    s = Settings(tmp_path / "s.json"); s.set("voice.rate", 12); s.save()
    s2 = Settings(tmp_path / "s.json"); assert s2.get("voice.rate") == 12 and s2.get("voice.volume") == 85


def test_openai_tool_call_parsing_and_conversion():
    seen = {}
    def handler(req):
        seen["body"] = json.loads(req.content); seen["auth"] = req.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "On it.", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "open_app", "arguments": "{\"name\": \"chrome\"}"}}]}}]})
    p = OpenAICompat("https://x/v1", "m", "KEY", 0.3, httpx.MockTransport(handler))
    msgs = [{"role": "user", "content": "a"}, {"role": "user", "content": "b"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "z", "name": "t", "arguments": {"q": 1}}]},
            {"role": "tool", "tool_call_id": "z", "name": "t", "content": "OK"}]
    r = p.chat("sys", msgs, [{"name": "open_app", "description": "d", "parameters": {"type": "object", "properties": {}}}])
    assert r.text == "On it." and r.tool_calls[0].arguments == {"name": "chrome"}
    assert seen["auth"] == "Bearer KEY" and seen["body"]["messages"][1]["content"] == "a\nb"
    assert seen["body"]["messages"][2]["tool_calls"][0]["function"]["arguments"] == '{"q": 1}'


def test_anthropic_conversion_merges_tool_results():
    seen = {}
    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "hi"}, {"type": "tool_use", "id": "t1", "name": "x", "input": {"a": 1}}]})
    p = AnthropicProvider("https://a/v1", "m", "K", 0.5, httpx.MockTransport(handler))
    msgs = [{"role": "user", "content": "go"},
            {"role": "assistant", "content": "ok", "tool_calls": [{"id": "1", "name": "a", "arguments": {}}, {"id": "2", "name": "b", "arguments": {}}]},
            {"role": "tool", "tool_call_id": "1", "name": "a", "content": "r1"},
            {"role": "tool", "tool_call_id": "2", "name": "b", "content": "r2"}]
    r = p.chat("s", msgs, [{"name": "x", "description": "d", "parameters": {"type": "object", "properties": {}}}])
    assert r.tool_calls[0].name == "x"
    last = seen["body"]["messages"][-1]
    assert last["role"] == "user" and [b["tool_use_id"] for b in last["content"]] == ["1", "2"]
    assert seen["body"]["tools"][0]["input_schema"]["type"] == "object"


@pytest.mark.parametrize("code,frag", [(401, "API key"), (429, "rate"), (404, "model"), (500, "server")])
def test_friendly_http_errors(code, frag):
    p = OpenAICompat("https://x", "m", "k", 0.5, httpx.MockTransport(lambda r: httpx.Response(code, json={"error": {"message": "boom"}})))
    with pytest.raises(ProviderError) as e: p.chat("s", [{"role": "user", "content": "x"}], [])
    assert frag.lower() in str(e.value).lower()


def test_offline_error():
    def boom(req): raise httpx.ConnectError("no")
    p = OpenAICompat("https://x", "m", "k", 0.5, httpx.MockTransport(boom))
    with pytest.raises(ProviderError, match="internet"): p.chat("s", [{"role": "user", "content": "x"}], [])


class Fake:
    def __init__(self, script): self.script = list(script); self.calls = []
    def chat(self, system, msgs, tools):
        self.calls.append((len(msgs), [t["name"] for t in tools])); return self.script.pop(0)


def run(env, script, confirm=lambda q, d: True):
    s, st, reg = env
    fake = Fake(script); ag = Agent(s, st, reg, lambda _s: fake)
    said, tools_ = [], []
    ctx = ToolContext(s, confirm, threading.Event(), {"storage": st})
    ag.run_turn([("user", "hi")], ctx, ctx.cancel, said.append, lambda n, a, r: tools_.append((n, r)))
    return said, tools_, fake


def test_agent_narrates_runs_tools_and_finishes(env, tmp_path):
    target = tmp_path / "newdir"
    said, t, fake = run(env, [LLMResponse("Creating it.", [ToolCall("1", "create_folder", {"path": str(target)})]), LLMResponse("Done, sir.")])
    assert said == ["Creating it.", "Done, sir."] and target.is_dir() and t[0][1].startswith("OK")


def test_sensitive_tool_denied_and_allowed(env, tmp_path):
    f = tmp_path / "a.txt"; f.write_text("x")
    said, t, _ = run(env, [LLMResponse("", [ToolCall("1", "delete_path", {"path": str(f)})]), LLMResponse("ok")], confirm=lambda q, d: False)
    assert t[0][1].startswith("DENIED") and f.exists()


def test_permission_off_hides_and_blocks(env):
    s, st, reg = env; s.set("permissions.files", False)
    assert "create_folder" not in [x["name"] for x in reg.schemas(s)]
    ctx = ToolContext(s, lambda q, d: True)
    assert reg.execute("create_folder", {"path": "x"}, ctx).startswith("ERROR: the 'files' permission")


def test_unknown_missing_and_forbidden(env):
    s, st, reg = env; ctx = ToolContext(s, lambda q, d: True)
    assert reg.execute("nope", {}, ctx).startswith("ERROR: unknown")
    assert "missing" in reg.execute("create_folder", {}, ctx)
    assert "blocked" in reg.execute("run_command", {"command": "Set-MpPreference -DisableRealtimeMonitoring $true"}, ctx)


def test_file_tools(env, tmp_path):
    s, st, reg = env; ctx = ToolContext(s, lambda q, d: True)
    (tmp_path / "Report Final.docx").write_text("x"); (tmp_path / "pic.png").write_text("x")
    assert "Report Final.docx" in reg.execute("find_files", {"query": "report final", "folder": str(tmp_path)}, ctx)
    assert reg.execute("organize_folder", {"folder": str(tmp_path)}, ctx).startswith("OK")
    assert (tmp_path / "Images" / "pic.png").exists() and (tmp_path / "Documents" / "Report Final.docx").exists()
    assert reg.execute("read_file", {"path": str(tmp_path / "Documents" / "Report Final.docx")}, ctx) == "x"


def test_memory_and_reminder_tools(env):
    s, st, reg = env
    from vega.reminders import ReminderScheduler
    fired = []; rs = ReminderScheduler(st, fired.append)
    ctx = ToolContext(s, lambda q, d: True, services={"storage": st, "reminders": rs})
    assert reg.execute("remember", {"fact": "likes tea"}, ctx) == "OK: remembered" and st.facts() == ["likes tea"]
    assert reg.execute("set_reminder", {"text": "stretch", "minutes_from_now": 0.01}, ctx).startswith("OK")
    import time; time.sleep(2.2); rs.stop(); assert fired == ["stretch"]


def test_yes_no_parser():
    assert parse_yes_no("Yes, go ahead") is True and parse_yes_no("no don't") is False
    assert parse_yes_no("open chrome please and also something else entirely") is None


def test_segmenter_utterance_and_barge():
    rng = np.random.default_rng(1)
    n = lambda k, a: rng.normal(0, a, 480 * k).astype(np.int16)
    sig = np.concatenate([n(40, 60), n(30, 3000), n(40, 60)])
    for speaking, want in ((False, ["start", "utterance"]), (True, ["start", "barge", "utterance"])):
        seg, ev = Segmenter(5, 600), []
        for i in range(0, len(sig) - 479, 480):
            ev += [e[0] for e in seg.process(sig[i:i + 480], speaking) if e[0] != "level"]
        assert ev == want
