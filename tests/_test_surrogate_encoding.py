"""Test surrogate encoding resilience in wb_proxy.

Verifies that requests containing unpaired UTF-16 surrogates (e.g. truncated emojis
like '\\ud83d') do not crash with UnicodeEncodeError ('surrogates not allowed')
when encoded for upstream transmission.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wb_proxy as proxy


class SurrogateEncodingTests(unittest.TestCase):
    def test_encode_upstream_body_with_normal_content(self):
        body = {
            "model": "deepseek-v4.1-flash",
            "messages": [
                {"role": "user", "content": "你好世界 🚀 123 abc"}
            ]
        }
        encoded = proxy.encode_upstream_body(body)
        self.assertIsInstance(encoded, bytes)
        # Should be valid utf-8 JSON
        decoded = json.loads(encoded.decode("utf-8"))
        self.assertEqual("你好世界 🚀 123 abc", decoded["messages"][0]["content"])

    def test_encode_upstream_body_with_lone_surrogate(self):
        # Position with lone surrogate \ud83d
        broken_prompt = "leading text \ud83d trailing text"
        body = {
            "model": "deepseek-v4.1-flash",
            "messages": [
                {"role": "user", "content": broken_prompt}
            ]
        }
        # Previously, this raised UnicodeEncodeError: 'utf-8' codec can't encode character '\ud83d': surrogates not allowed
        encoded = proxy.encode_upstream_body(body)
        self.assertIsInstance(encoded, bytes)
        # Must decode cleanly as valid UTF-8
        decoded_text = encoded.decode("utf-8")
        self.assertIn(r"\ud83d", decoded_text)
        # Must be valid JSON parseable by any JSON parser
        parsed = json.loads(decoded_text)
        self.assertEqual(broken_prompt, parsed["messages"][0]["content"])

    def test_prompt_fingerprint_and_affinity_with_lone_surrogate(self):
        msgs = [
            {"role": "system", "content": "system prompt \ud83d"},
            {"role": "user", "content": "hello \ud83d"}
        ]
        fp = proxy.prompt_fingerprint(msgs)
        self.assertIn("msgs_sha", fp)
        self.assertEqual(2, fp.get("n_msgs"))

        key, _ = proxy.affinity_route(msgs)
        self.assertIsNotNone(key)
        self.assertTrue(key.startswith("pfx-"))


if __name__ == "__main__":
    unittest.main()
