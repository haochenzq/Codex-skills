"""Verify authentication, provider status handling and MCP stdio without paid API calls."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from adapter import Credentials, VolcAPI, ARK_BASE, MEDIAKIT_BASE, ASR_BASE


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Path(self.temp.name) / "config.json"
        self.config.write_text("{}", encoding="utf-8")
        self.env = patch.dict(os.environ, {
            "ARK_API_KEY": "fixture-ark-key", "VOLC_ASR_API_KEY": "fixture-asr-key",
            "VOLC_MEDIAKIT_API_KEY": "fixture-mediakit-key",
            "VOLC_ASR_APP_ID": "", "VOLC_ASR_ACCESS_TOKEN": "", "VOLC_API_KEY": "",
        })
        self.env.start()
        self.creds = Credentials(self.config)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def api(self, handler):
        return VolcAPI(self.creds, httpx.MockTransport(handler))

    async def test_ark_native_payload_and_secret_redaction(self):
        payload = {"model": "exact-model-id", "messages": [{"role": "user", "content": "ping"}],
                   "temperature": 0.2}
        def handler(request):
            self.assertEqual(str(request.url), ARK_BASE + "/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer fixture-ark-key")
            self.assertEqual(json.loads(request.content), dict(payload, stream=False))
            return httpx.Response(200, json={"id": "test", "echo": "fixture-ark-key"})
        result = await self.api(handler).chat(payload)
        self.assertTrue(result["ok"])
        self.assertEqual(result["body"]["echo"], "[REDACTED]")

    async def test_mediakit_combined_auth(self):
        def handler(request):
            self.assertEqual(str(request.url), MEDIAKIT_BASE + "/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer fixture-ark-key/fixture-mediakit-key")
            return httpx.Response(200, json={"id": "test"})
        self.assertTrue((await self.api(handler).chat({"model": "specific-model", "messages": ["test"]},
                                                     mediakit=True))["ok"])

    async def test_responses_endpoint(self):
        def handler(request):
            self.assertEqual(str(request.url), ARK_BASE + "/responses")
            return httpx.Response(200, json={"id": "test"})
        self.assertTrue((await self.api(handler).chat({"model": "specific-model", "input": "test"},
                                                     responses=True))["ok"])

    async def test_asr_submit_empty_body_and_query_processing(self):
        task_id = "existing-test-task"
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.headers["X-Api-Key"], "fixture-asr-key")
            self.assertEqual(request.headers["X-Api-Request-Id"], task_id)
            self.assertEqual(request.headers["X-Api-Resource-Id"], "volc.seedasr.auc")
            if request.url.path.endswith("submit"):
                self.assertEqual(request.headers["X-Api-Sequence"], "-1")
                return httpx.Response(200, headers={"X-Api-Status-Code": "20000000"})
            self.assertEqual(json.loads(request.content), {})
            self.assertNotIn("X-Api-Sequence", request.headers)
            return httpx.Response(200, headers={"X-Api-Status-Code": "20000001"}, json={})
        api = self.api(handler)
        submitted = await api.asr("submit", {"audio": {"url": "https://example.com/test.mp3"}}, task_id)
        self.assertEqual(submitted["state"], "submitted")
        queried = await api.asr("query", request_id=task_id)
        self.assertEqual(queried["state"], "processing")
        self.assertEqual(len(calls), 2)

    async def test_asr_business_error_on_http_200(self):
        def handler(request):
            self.assertEqual(str(request.url), ASR_BASE + "/recognize/flash")
            self.assertEqual(request.headers["X-Api-Resource-Id"], "volc.bigasr.auc_turbo")
            return httpx.Response(200, headers={"X-Api-Status-Code": "45000132"}, json={})
        result = await self.api(handler).asr("flash", {"audio": {"url": "https://example.com/test.mp3"}})
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "error")

    async def test_no_speech_is_a_distinct_confirmed_terminal(self):
        body = {"audio_info": {"duration": 60000}, "result": {"text": ""}}
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, headers={"X-Api-Status-Code": "20000003",
                "X-Api-Message": "[Normal silence audio] no valid speech in audio",
                "X-Tt-Logid": "provider-request"}, json=body)
        api = self.api(handler)
        for operation in ("flash", "query", "submit"):
            result = await api.asr(operation, {"audio": {"url": "https://example.com/test.mp3"}},
                                   request_id="saved-task")
            self.assertTrue(result["ok"])
            self.assertEqual(result["state"], "no_speech")
            self.assertEqual(result["body"], body)
            self.assertEqual(result["task_id"], "saved-task")
            self.assertEqual(result["request_id"], "provider-request")
        self.assertEqual(len(calls), 3)

    async def test_no_speech_code_does_not_override_http_failure(self):
        api = self.api(lambda request: httpx.Response(500,
            headers={"X-Api-Status-Code": "20000003"}, json={}))
        result = await api.asr("flash", {"audio": {"url": "https://example.com/test.mp3"}})
        self.assertFalse(result["ok"])

    async def test_native_asr_accepts_direct_audio(self):
        payload = {"audio": {"data": "UklGRg==", "format": "wav"}}
        calls = []
        def handler(request):
            calls.append(request)
            self.assertIn(str(request.url), (ASR_BASE + "/recognize/flash", ASR_BASE + "/submit"))
            self.assertEqual(json.loads(request.content), payload)
            return httpx.Response(200, headers={"X-Api-Status-Code": "20000000"}, json={})
        api = self.api(handler)
        self.assertTrue((await api.asr("flash", payload))["ok"])
        self.assertEqual((await api.asr("submit", payload))["state"], "submitted")
        with self.assertRaisesRegex(ValueError, "audio.url"):
            await api.asr("flash", {"audio": {"data": ""}})
        self.assertEqual(len(calls), 2)

    async def test_no_redirect_or_automatic_retry(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(307, headers={"Location": "https://example.com/redirect"}, json={})
        result = await self.api(handler).chat({"model": "specific-model", "messages": ["test"]})
        self.assertFalse(result["ok"])
        self.assertEqual(len(calls), 1)

    async def test_timeout_keeps_asr_task_id(self):
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("fixture-ark-key", request=request)
        result = await self.api(handler).asr("submit", {"audio": {"url": "https://example.com/test.mp3"}},
                                            "stable-request-id")
        self.assertEqual(result["task_id"], "stable-request-id")
        self.assertFalse(result["retry_performed"])
        self.assertNotIn("fixture-ark-key", json.dumps(result))
        self.assertEqual(len(calls), 1)

    async def test_missing_credentials_fail_before_network(self):
        os.environ["ARK_API_KEY"] = ""
        def handler(request):
            self.fail("network must not be called")
        with self.assertRaisesRegex(ValueError, "Missing ark credential"):
            await self.api(handler).chat({"model": "specific-model", "messages": ["test"]})

    async def test_shared_key_file_and_masked_provider_redaction(self):
        key_file = Path(self.temp.name) / "shared.txt"
        key_file.write_text("fixture-shared-key", encoding="utf-8")
        self.config.write_text(json.dumps({"shared_key_file": str(key_file)}), encoding="utf-8")
        for variable in ("ARK_API_KEY", "VOLC_ASR_API_KEY", "VOLC_MEDIAKIT_API_KEY"):
            os.environ[variable] = ""
        self.assertEqual(self.creds.get("ark"), "fixture-shared-key")
        self.assertEqual(self.creds.get("asr"), "fixture-shared-key")
        self.assertEqual(self.creds.get("mediakit"), "fixture-shared-key")
        api = self.api(lambda request: httpx.Response(200, json={}))
        self.assertEqual(api._redact("key 'ark-***abcd' not found"), "key '[REDACTED]' not found")

    async def test_labeled_credential_lines_and_mismatched_label(self):
        key_file = Path(self.temp.name) / "labeled.txt"
        key_file.write_text("火山方舟：fixture-ark-key\n\nmediakit：fixture-mediakit-key\n\n豆包语音：fixture-asr-key\n", encoding="utf-8-sig")
        config = {}
        for service, line, prefix in (("ark", 1, "火山方舟："),
                                      ("mediakit", 3, "mediakit："),
                                      ("asr", 5, "豆包语音：")):
            config.update({service + "_key_file": str(key_file),
                           service + "_key_line": line, service + "_key_prefix": prefix})
        self.config.write_text(json.dumps(config), encoding="utf-8")
        for variable in ("ARK_API_KEY", "VOLC_ASR_API_KEY", "VOLC_MEDIAKIT_API_KEY"):
            os.environ[variable] = ""
        for service in ("ark", "mediakit", "asr"):
            self.assertEqual(self.creds.get(service), "fixture-" + service + "-key")
        config["asr_key_line"] = 1
        self.config.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Cannot read local asr credential configuration"):
            self.creds.get("asr")
        self.assertFalse(self.creds.ready("asr"))

    async def test_stdio_handshake_tool_listing_and_status(self):
        params = StdioServerParameters(command=sys.executable,
                                       args=[str(Path(__file__).with_name("server.py"))],
                                       env=dict(os.environ))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
                names = {tool.name for tool in listing.tools}
                self.assertEqual(len(names), 15)
                self.assertTrue({'volc_prepare_generation','volc_generation_status','volc_submit_generation',
                                 'volc_query_generation','volc_download_generation'}.issubset(names))
                self.assertIn("volc_ark_chat", names)
                self.assertIn("volc_prepare_workflow", names)
                self.assertNotIn("volc_mediakit_chat", names)
                result = await session.call_tool("volc_connection_status", {})
                self.assertFalse(result.isError)
                body = result.structuredContent
                self.assertTrue(body["credential_configured"]["ark"])
                self.assertFalse(body["network_verified"])
                self.assertNotIn("fixture-ark-key", result.model_dump_json())


if __name__ == "__main__":
    unittest.main(verbosity=2)
