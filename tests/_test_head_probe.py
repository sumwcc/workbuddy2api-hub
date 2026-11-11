"""HEAD 探路支持：new-api 的渠道 prewarm probe（wb_proxy / do_HEAD）。

`channel_probe.ts` 在冷态渠道上用 `HEAD <base_url>/v1/models` 判断 TCP/TLS 链路
是否还活着（任何 HTTP 响应都算通）。hub 以前没有 do_HEAD，落到 501：功能不受
影响，但日志里每分钟一条 501，像故障也污染状态码统计。

Run with: python tests/_test_head_probe.py
"""
import io
import json
import os
import sys
import tempfile
import unittest

_startup_dir = tempfile.TemporaryDirectory(prefix="head-probe-")
os.environ["ACCOUNTS_DIR"] = _startup_dir.name
os.environ["WB_PROXY_USAGE_DIR"] = _startup_dir.name
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wb_proxy


class StubHandler(wb_proxy.Handler):
    """只收响应输出、不起 socket 的 Handler 桩。"""

    def __init__(self, path, command="HEAD"):
        self.path = path
        self.command = command
        self.close_connection = False
        self.status = None
        self.headers_out = []
        self.body = b""
        self.error = None

    def send_response(self, code, message=None):
        self.status = code

    def send_header(self, key, value):
        self.headers_out.append((key, value))

    def end_headers(self):
        pass

    def send_error(self, code, message=None, explain=None):
        self.status = code
        self.error = message

    def do_GET(self):
        # /health 分支会转调 do_GET：这里只验「头照发、body 不写」，不跑真实路由。
        self._json(200, {"ok": True, "accounts": 70})

    @property
    def wfile(self):
        return self._wfile()

    def _wfile(self):
        stub = self
        class _Sink(io.BytesIO):
            def write(self, data):
                stub.body += bytes(data)
                return len(data)
            def flush(self):
                pass
        return _Sink()


class HeadProbeTests(unittest.TestCase):
    def test_models_head_is_200_without_auth(self):
        handler = StubHandler("/v1/models")
        handler.do_HEAD()
        self.assertEqual(handler.status, 200)
        headers = dict(handler.headers_out)
        self.assertEqual(headers.get("Content-Length"), "0")
        self.assertIn("application/json", headers.get("Content-Type", ""))
        self.assertEqual(handler.body, b"")

    def test_models_head_tolerates_trailing_slash(self):
        handler = StubHandler("/v1/models/")
        handler.do_HEAD()
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.body, b"")

    def test_health_head_keeps_headers_but_drops_body(self):
        handler = StubHandler("/health")
        handler.do_HEAD()
        self.assertEqual(handler.status, 200)
        headers = dict(handler.headers_out)
        expected = len(json.dumps({"ok": True, "accounts": 70}, ensure_ascii=False)
                       .encode("utf-8", "backslashreplace"))
        self.assertEqual(int(headers["Content-Length"]), expected)
        self.assertEqual(handler.body, b"")
        self.assertFalse(handler._head_only)

    def test_other_paths_keep_the_old_501(self):
        handler = StubHandler("/nope")
        handler.do_HEAD()
        self.assertEqual(handler.status, 501)

    def test_get_bodies_are_still_written(self):
        handler = StubHandler("/health", command="GET")
        handler._json(200, {"ok": True})
        self.assertIn(b'"ok"', handler.body)


if __name__ == "__main__":
    unittest.main()
