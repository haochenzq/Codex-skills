"""Real local FFmpeg + simulated cloud: alignment, lifecycle, safety and separate MCP."""
import asyncio
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from adapter import Credentials, VolcAPI
from mediakit import MediaKit, MEDIAKIT_TOOLS_BASE
import workflow

class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_turbo_no_speech_still_analyzes_music_and_ocr(self):
        prepared = workflow.prepare([str(self.fixture())], asr_backend_name="doubao_turbo", summary_backend_name="local")
        folder, job = workflow.load(prepared["job_id"])
        duration = job["clips"][0]["duration"]
        calls = []
        def handler(request):
            calls.append((request.url.host, request.method, request.url.path))
            if request.url.host == "openspeech.bytedance.com":
                return httpx.Response(200, headers={"X-Api-Status-Code": "20000003", "X-Tt-Logid": "no-speech-request"},
                    json={"audio_info": {"duration": duration * 1000}, "result": {"text": ""}})
            if request.url.path == "/api/v3/files":
                return httpx.Response(200, json={"id": "file-fixture", "status": "processing"})
            if request.method == "GET":
                return httpx.Response(200, json={"id": "file-fixture", "status": "active"})
            data = {"summary": "配乐与屏幕文字", "scenes": [], "events": [], "ocr": [
                {"start": 0, "end": 1, "text": "屏幕文字"}], "highlights": [], "editing_suggestions": [],
                **{field: [] for field in workflow.AV_FIELDS}}
            data["music"] = [{"start": 0, "end": 1, "description": "可听配乐"}]
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(data)}}]})
        api = self.api(handler)
        for _ in range(8):
            folder, job = workflow.load(prepared["job_id"])
            job["clips"][0]["visual"]["next_poll_at"] = 0
            workflow.dump(folder / "job.json", job)
            status = await workflow.advance(prepared["job_id"], True, api)
            self.assertNotEqual(status["state"], "needs_review", status)
            if status["state"] == "completed":
                break
        self.assertEqual(status["state"], "completed")
        evidence = workflow.result(prepared["job_id"])["evidence"]["videos"][0]
        self.assertEqual(evidence["transcript"], [])
        self.assertEqual(evidence["asr_outcomes"][0]["speech_status"], "no_speech")
        self.assertEqual(evidence["audio_understanding"], "analyzed")
        self.assertTrue(evidence["music"])
        self.assertTrue(evidence["ocr"])
        self.assertEqual(sum(host == "openspeech.bytedance.com" for host, _, _ in calls), 1)

    async def test_standard_query_no_speech_finishes_without_resubmit(self):
        prepared = workflow.prepare([str(self.fixture())], task="audio_transcription", asr_backend_name="doubao2")
        folder, job = workflow.load(prepared["job_id"])
        calls = []
        def handler(request):
            calls.append(request.url.path)
            if request.url.path.endswith("submit"):
                return httpx.Response(200, headers={"X-Api-Status-Code": "20000000"}, json={})
            return httpx.Response(200, headers={"X-Api-Status-Code": "20000003"}, json={
                "audio_info": {"duration": job["clips"][0]["duration"] * 1000}, "result": {"text": ""}})
        api = self.api(handler)
        await workflow.advance(prepared["job_id"], True, api)
        folder, job = workflow.load(prepared["job_id"])
        job["clips"][0]["asr"]["next_poll_at"] = 0
        workflow.dump(folder / "job.json", job)
        await workflow.advance(prepared["job_id"], True, api)
        status = await workflow.advance(prepared["job_id"], True, api)
        self.assertEqual(status["state"], "completed")
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[1].endswith("query"))

    def reviewed_no_speech_fixture(self):
        prepared = workflow.prepare([str(self.fixture())], asr_backend_name="doubao_turbo", summary_backend_name="local")
        folder, job = workflow.load(prepared["job_id"])
        clip = job["clips"][0]
        clip["asr"].update(state="submit_started", task_id="retained-task")
        job.update(state="needs_review", paid_requests_attempted=1, error="ASR submission failed or is uncertain; do not automatically resubmit")
        workflow.dump(folder / "job.json", job)
        raw = folder / "raw" / (clip["id"] + "_asr_submit.json")
        raw.parent.mkdir(exist_ok=True)
        response = {"ok": False, "http_status": 200, "state": "error", "provider_code": "20000003",
                    "task_id": "retained-task", "request_id": "retained-request",
                    "body": {"audio_info": {"duration": clip["duration"] * 1000}, "result": {"text": ""}}}
        workflow.dump(raw, response)
        return folder, job, clip, raw

    async def test_reviewed_no_speech_recovery_is_local_idempotent_and_keeps_raw(self):
        folder, job, clip, raw = self.reviewed_no_speech_fixture()
        raw_bytes, job_bytes = raw.read_bytes(), (folder / "job.json").read_bytes()
        status = workflow.recover_no_speech(job["job_id"], clip["id"])
        self.assertEqual(status["state"], "processing")
        self.assertEqual(status["completed_asr_clips"], 1)
        _, saved = workflow.load(job["job_id"])
        self.assertEqual(saved["paid_requests_attempted"], 1)
        self.assertEqual(saved["clips"][0]["asr"]["segments"], [])
        self.assertEqual(saved["clips"][0]["asr"]["request_id"], "retained-request")
        self.assertEqual(saved["clips"][0]["visual"], job["clips"][0]["visual"])
        self.assertEqual(raw.read_bytes(), raw_bytes)
        self.assertEqual((folder / "job.before-no-speech-recovery.json").read_bytes(), job_bytes)
        after = (folder / "job.json").read_bytes()
        workflow.recover_no_speech(job["job_id"], clip["id"])
        self.assertEqual((folder / "job.json").read_bytes(), after)
        def handler(request):
            self.assertNotEqual(request.url.host, "openspeech.bytedance.com", "Must not resubmit recovered audio")
            return httpx.Response(200, json={"id": "file-fixture", "status": "processing"})
        await workflow.advance(job["job_id"], True, self.api(handler))

    async def test_review_recovery_rejects_unknown_result_and_preserves_existing_lock(self):
        folder, job, clip, raw = self.reviewed_no_speech_fixture()
        response = json.loads(raw.read_text(encoding="utf-8"))
        response["provider_code"] = "20000001"
        workflow.dump(raw, response)
        before = (folder / "job.json").read_bytes()
        with self.assertRaises(ValueError):
            workflow.recover_no_speech(job["job_id"], clip["id"])
        self.assertEqual((folder / "job.json").read_bytes(), before)
        self.assertFalse((folder / ".advance.lock").exists())
        (folder / ".advance.lock").write_text("active", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            workflow.recover_no_speech(job["job_id"], clip["id"])
        self.assertEqual((folder / ".advance.lock").read_text(encoding="utf-8"), "active")

    async def test_no_speech_recovery_rejects_contradictory_text_or_wrong_duration(self):
        folder, job, clip, raw = self.reviewed_no_speech_fixture()
        response = json.loads(raw.read_text(encoding="utf-8"))
        for change in ("text", "duration", "task_id"):
            import copy
            altered = copy.deepcopy(response)
            if change == "text":
                altered["body"]["result"]["text"] = "实际有文字"
            elif change == "duration":
                altered["body"]["audio_info"]["duration"] = 10
            else:
                altered["task_id"] = "another-task"
            workflow.dump(raw, altered)
            before = (folder / "job.json").read_bytes()
            with self.subTest(change=change), self.assertRaises(ValueError):
                workflow.recover_no_speech(job["job_id"], clip["id"])
            self.assertEqual((folder / "job.json").read_bytes(), before)

    async def test_standard_features_reach_request_and_evidence(self):
        prepared=workflow.prepare([str(self.fixture())],task='audio_transcription',asr_features=['emotion','speech_rate','volume'])
        folder,job=workflow.load(prepared['job_id']);clip=job['clips'][0];calls=[]
        body={'audio_info':{'duration':round(clip['duration']*1000)},'result':{'text':'测试','utterances':[
            {'start_time':2000,'end_time':2500,'text':'测试','additions':{'emotion':'neutral','speech_rate':'3','volume':'-20'},
             'words':[{'start_time':2000,'end_time':2500,'text':'测试'}]}]}}
        def handler(request):
            payload=json.loads(request.content);calls.append(payload)
            if request.url.path.endswith('submit'):
                self.assertTrue(all(payload['request'][flag] for flag in workflow.ASR_FEATURES.values()))
                return httpx.Response(200,headers={'X-Api-Status-Code':'20000000'},json={})
            return httpx.Response(200,headers={'X-Api-Status-Code':'20000000'},json=body)
        api=self.api(handler)
        await workflow.advance(job['job_id'],True,api)
        folder,job=workflow.load(job['job_id']);job['clips'][0]['asr']['next_poll_at']=0;workflow.dump(folder/'job.json',job)
        await workflow.advance(job['job_id'],True,api)
        await workflow.advance(job['job_id'],True,api)
        evidence=workflow.result(job['job_id'])['evidence']['videos'][0]
        self.assertEqual(evidence['asr_feature_coverage'],dict.fromkeys(workflow.ASR_FEATURES,'available'))
        self.assertEqual(evidence['transcript'][0]['additions']['volume'],'-20')
        self.assertEqual(len(calls),2)
    async def test_optional_asr_features_cannot_silently_use_turbo(self):
        with self.assertRaisesRegex(ValueError,'doubao2'):
            workflow.prepare(['not-needed'],asr_backend_name='doubao_turbo',asr_features=['emotion'])
        with self.assertRaises(ValueError): workflow.prepare(['not-needed'],asr_features=['unknown'])
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.jobs = patch.object(workflow, "JOBS", self.root / "outputs")
        self.jobs.start()
        self.env = patch.dict(os.environ, {"ARK_API_KEY": "fixture-ark-key",
            "VOLC_MEDIAKIT_API_KEY": "fixture-mediakit-key", "VOLC_ASR_API_KEY": "fixture-asr-key",
            "VOLC_API_KEY": ""})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.jobs.stop()
        self.temp.cleanup()

    def fixture(self, name="fixture.mp4", audio=True):
        output = self.root / name
        args = [workflow.native("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=10:d=12"]
        if audio:
            args += ["-itsoffset", "2", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=3"]
        args += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if audio:
            args += ["-c:a", "aac"]
        workflow.run_local(args + [str(output)], 30)
        return output

    def api(self, handler):
        return VolcAPI(transport=httpx.MockTransport(handler))

    async def test_credential_line_selection_and_redaction(self):
        self.env.stop()
        with patch.dict(os.environ, {"ARK_API_KEY": "", "VOLC_MEDIAKIT_API_KEY": "", "VOLC_API_KEY": ""}):
            keys = self.root / "keys.txt"
            keys.write_text("fixture-ark\n\nfixture-media\n")
            config = self.root / "config.json"
            config.write_text(json.dumps({"ark_key_file": str(keys), "ark_key_line": 1,
                "mediakit_key_file": str(keys), "mediakit_key_line": 3}))
            creds = Credentials(config)
            self.assertEqual(creds.get("mediakit"), "fixture-media")
            self.assertEqual(VolcAPI(creds)._redact("fixture-ark/fixture-media"), "[REDACTED]/[REDACTED]")
            config.write_text(json.dumps({"ark_key_file": str(keys), "ark_key_line": 2}))
            self.assertFalse(creds.ready("ark"))
        self.env.start()

    async def test_real_preprocessing_preserves_audio_delay_and_tail(self):
        source = self.fixture()
        original = workflow.fingerprint(source)
        prepared = workflow.prepare([str(source)], clip_seconds=10)
        folder, job = workflow.load(prepared["job_id"])
        self.assertEqual(len(job["clips"]), 2)
        self.assertEqual([c["start"] for c in job["clips"]], [0, 10])
        self.assertEqual(workflow.fingerprint(source), original)
        for clip in job["clips"]:
            self.assertAlmostEqual(workflow.probe(Path(clip["audio_path"]))["duration"], clip["duration"], places=2)
        with wave.open(job["clips"][0]["audio_path"], "rb") as stream:
            values = struct.unpack("<" + "h" * stream.getnframes(), stream.readframes(stream.getnframes()))
            self.assertLess(max(abs(v) for v in values[:24000]), 10)
            self.assertGreater(max(abs(v) for v in values[40000:48000]), 100)
            self.assertLess(max(abs(v) for v in values[120000:]), 10)
        pcm = workflow.run_local([workflow.native("ffmpeg"), "-v", "error", "-i",
            job["clips"][0]["video_path"], "-map", "0:a:0", "-f", "s16le", "-ar", "16000", "-ac", "1", "pipe:1"])
        embedded = struct.unpack("<" + "h"*(len(pcm)//2), pcm)
        self.assertLess(max(abs(v) for v in embedded[:24000]), 10)
        self.assertGreater(max(abs(v) for v in embedded[40000:48000]), 100)
        self.assertLess(max(abs(v) for v in embedded[120000:]), 10)
        self.assertEqual(prepared["planned_paid_requests"], 4)
        self.assertEqual(prepared["asr_backend"], "doubao2")

    async def test_no_network_without_job_approval(self):
        source = self.fixture(audio=False)
        prepared = workflow.prepare([str(source)], clip_seconds=10)
        def handler(request):
            self.fail("Unapproved workflow must not call network")
        result = await workflow.advance(prepared["job_id"], api=self.api(handler))
        self.assertEqual(result["state"], "prepared")
        self.assertIn("action_required", result)

    async def test_end_to_end_multivideo_outputs_and_timestamp_provenance(self):
        await self.exercise_multivideo("mediakit")

    async def test_doubao_default_bridge_native_timestamps_and_multivideo(self):
        await self.exercise_multivideo("doubao2", bridge=True)

    async def test_legacy_job_without_backend_keeps_mediakit(self):
        await self.exercise_multivideo("mediakit", legacy=True)

    async def test_default_local_summary_skips_extra_cloud_reasoning(self):
        await self.exercise_multivideo("doubao2", summary="local")

    async def test_turbo_inline_returns_word_evidence_without_asr_polling(self):
        await self.exercise_multivideo("doubao_turbo", summary="local")

    async def exercise_multivideo(self, backend, legacy=False, summary="ark", bridge=False):
        one = self.fixture()
        two = self.root / "second.mp4"
        shutil.copyfile(one, two)
        prepared = workflow.prepare([str(one), str(two)], task="multi_video_summary", clip_seconds=10,
                                     speaker_info=True, asr_backend_name=backend, summary_backend_name=summary)
        folder, job = workflow.load(prepared["job_id"])
        # Exercise the retained visual-only route for historical jobs.
        job.pop("visual_transport", None)
        workflow.dump(folder / "job.json", job)
        if bridge:
            del job["asr_transport"]
            for c in job["clips"]:
                c["asr"]["state"] = "pending_upload"
            job["planned_paid_requests"] += len(job["clips"])
            workflow.dump(folder / "job.json", job)
            prepared = workflow.overview(folder, job)
        if legacy:
            del job["asr_backend"]
            del job["summary_backend"]
            workflow.dump(folder / "job.json", job)
        uploads = []
        calls = []
        native_tasks = {}
        def response(body):
            return httpx.Response(200, json=body)
        async def handler(request):
            calls.append((request.method, request.url.host, request.url.path))
            if request.url.path.endswith("request-media-upload-url"):
                self.assertEqual(request.headers["authorization"], "Bearer fixture-mediakit-key")
                number = len(uploads)
                uploads.append(number)
                return response({"success": True, "result": {"file_id": f"mediakit://fixture{number}",
                    "method": "PUT", "upload_headers": [], "upload_url": f"https://tob-upload-y.volcvod.com/{number}"}})
            if request.method == "PUT":
                self.assertNotIn("fixture-mediakit-key", str(request.headers))
                self.assertIn(request.headers["content-type"], {"audio/wav", "audio/x-wav"})
                self.assertTrue((await request.aread()).startswith(b"RIFF"))
                return httpx.Response(200)
            if request.url.path.endswith("asr-subtitles"):
                self.assertEqual(backend, "mediakit")
                body = json.loads(request.content)
                self.assertTrue(body["audio_url"].startswith("mediakit://"))
                self.assertLessEqual(len(body["client_token"]), 64)
                return response({"success": True, "task_id": "task-" + body["audio_url"].split("//")[1]})
            if request.url.path.endswith("transcode-audio"):
                self.assertIn(backend, workflow.NATIVE_ASR)
                body = json.loads(request.content)
                self.assertTrue(body["audio_url"].startswith("mediakit://"))
                self.assertEqual(body["audio"]["sample_rate"], 16000)
                self.assertNotIn("volume_method", body["audio"])
                self.assertLessEqual(len(body["client_token"]), 64)
                return response({"success": True, "task_id": "bridge-" + body["audio_url"].split("//")[1]})
            if request.url.host == "openspeech.bytedance.com":
                self.assertIn(backend, workflow.NATIVE_ASR)
                self.assertEqual(request.headers["x-api-key"], "fixture-asr-key")
                self.assertEqual(request.headers["x-api-resource-id"],
                    "volc.bigasr.auc_turbo" if backend == "doubao_turbo" else "volc.seedasr.auc")
                task = request.headers["x-api-request-id"]
                if request.url.path.endswith(("submit", "flash")):
                    body = json.loads(request.content)
                    if bridge:
                        number = int(body["audio"]["url"].split("/")[-1].split(".")[0])
                    else:
                        import base64
                        self.assertEqual(body["audio"]["format"], "wav")
                        self.assertTrue(base64.b64decode(body["audio"]["data"]).startswith(b"RIFF"))
                        self.assertNotIn("url", body["audio"])
                        number = len(native_tasks)
                    self.assertEqual(body["request"]["model_name"], "bigmodel")
                    self.assertTrue(body["request"]["show_utterances"])
                    self.assertFalse(body["request"]["enable_ddc"])
                    saved = json.loads((folder / "job.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved["clips"][number]["asr"]["task_id"], task)
                    native_tasks[task] = number
                    if backend != "doubao_turbo":
                        return httpx.Response(200, headers={"X-Api-Status-Code": "20000000"}, json={})
                if backend == "doubao_turbo":
                    self.assertTrue(request.url.path.endswith("flash"), "Turbo must not poll standard ASR")
                duration = job["clips"][native_tasks[task]]["duration"]
                return httpx.Response(200, headers={"X-Api-Status-Code": "20000000"}, json={
                    "audio_info": {"duration": round(duration * 1000)}, "result": {
                    "text": "测试转写", "utterances": [{"start_time": 500, "end_time": 1500,
                    "text": "测试转写", "additions": {"speaker": "speaker_0"},
                    "words": [{"start_time": 600, "end_time": 800, "text": "测试"}]}]}})
            if request.method == "GET":
                if request.url.path.split("/")[-1].startswith("bridge-"):
                    number = int(request.url.path.split("fixture")[-1])
                    return response({"success": True, "status": "completed", "result": {
                        "audio_url": f"https://cdn.volcvideo.com/audio/{number}.mp3",
                        "duration": job["clips"][number]["duration"]}})
                return response({"success": True, "status": "completed", "result": {
                    "subtitles": [{"start_time": .5, "end_time": 1.5,
                                   "subtitle_text": "测试转写", "speaker": "speaker_0"}]}})
            body = json.loads(request.content)
            if request.url.host.startswith("amk-ark"):
                self.assertEqual(request.headers["authorization"], "Bearer fixture-ark-key/fixture-mediakit-key")
                video = body["messages"][0]["content"][1]["video_url"]
                self.assertTrue(video["url"].startswith("data:video/mp4;base64,"))
                self.assertEqual(video["max_frames"], 120)
                generated = {"summary": "蓝色画面", "scenes": [{"start": 0, "end": 1, "description": "蓝色"}],
                    "events": [], "ocr": [], "highlights": [], "editing_suggestions": ["可作背景"]}
            else:
                self.assertEqual(summary, "ark", "Local summary must not request cloud text inference")
                generated = {"summary": "两个视频均为蓝色画面", "common_themes": ["共同背景"],
                             "differences": [], "recommendations": ["作为同组素材使用"]}
            return response({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(generated)}}]})
        api = self.api(handler)
        for n in range(40):
            with patch.object(workflow.time, "time", return_value=1000 + n * 20):
                result = await workflow.advance(prepared["job_id"], True, api)
            self.assertNotEqual(result["state"], "needs_review", result)
            if result["state"] == "completed":
                break
        self.assertEqual(result["state"], "completed")
        expected = (12 if bridge else 8) + (summary == "ark")
        self.assertEqual(result["paid_requests_attempted"], expected)
        self.assertEqual(prepared["planned_paid_requests"], expected)
        self.assertEqual(result["asr_backend"], backend)
        if backend in workflow.NATIVE_ASR and not bridge:
            self.assertEqual(uploads, [])
            self.assertEqual(prepared["service_plan"]["mediakit_transcode_calls"], 0)
        evidence = workflow.result(prepared["job_id"])["evidence"]
        transcript = evidence["videos"][0]["transcript"]
        self.assertEqual([s["start"] for s in transcript], [.5, 10.5])
        self.assertNotEqual(transcript[0]["speaker"], transcript[1]["speaker"])
        if backend in workflow.NATIVE_ASR:
            self.assertEqual(transcript[1]["words"][0]["start"], 10.6)
            self.assertEqual(transcript[1]["words"][0]["end"], 10.8)
        folder, _ = workflow.load(prepared["job_id"])
        self.assertIn("00:00:10,500", (folder / "video_001" / "transcript.srt").read_text(encoding="utf-8"))
        self.assertEqual((folder / "multi_video_summary.json").is_file(), summary == "ark")
        if summary == "local":
            self.assertTrue(workflow.result(prepared["job_id"])["local_summary_required"])
        self.assertTrue((folder / "video_001" / "keyframes" / "index.json").is_file())
        before = len(calls)
        await workflow.advance(prepared["job_id"], True, api)
        self.assertEqual(len(calls), before)

    async def test_native_timeout_keeps_task_id_and_never_falls_back(self):
        await self.exercise_native_timeout("doubao2")

    async def test_lite_real_track_file_lifecycle_and_audio_evidence(self):
        prepared = workflow.prepare([str(self.fixture())], asr_backend_name="doubao_turbo")
        folder, job = workflow.load(prepared["job_id"])
        clip = job["clips"][0]
        self.assertTrue(workflow.probe(Path(clip["video_path"]))["has_audio"])
        clip["asr"].update(state="done", segments=[], reused_from_job="fixture")
        workflow.dump(folder / "job.json", job)
        calls = []
        def handler(request):
            calls.append((request.method, request.url.path))
            self.assertEqual(request.headers["authorization"], "Bearer fixture-ark-key")
            if request.url.path.endswith("/files"):
                self.assertIn(workflow.LITE.encode(), request.content)
                return httpx.Response(200, json={"id": "file-fixture", "status": "processing"})
            if request.method == "GET":
                return httpx.Response(200, json={"id": "file-fixture", "status": "active"})
            body = json.loads(request.content)
            self.assertEqual(body["messages"][0]["content"][1]["video_url"], {"file_id": "file-fixture"})
            data = {"summary": "蓝色画面与短音调", "scenes": [], "events": [], "ocr": [],
                    "highlights": [], "editing_suggestions": [], **{k: [] for k in workflow.AV_FIELDS}}
            data["sound_events"] = [{"start": 2, "end": 5, "description": "短音调"}]
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps(data)}}]})
        for n in range(5):
            with patch.object(workflow.time, "time", return_value=1000 + 20*n):
                result = await workflow.advance(prepared["job_id"], True, self.api(handler))
            self.assertNotEqual(result["state"], "needs_review", result)
        self.assertEqual(result["state"], "completed")
        self.assertEqual(calls, [("POST", "/api/v3/files"), ("GET", "/api/v3/files/file-fixture"),
                                ("POST", "/api/v3/chat/completions")])
        video = workflow.result(prepared["job_id"])["evidence"]["videos"][0]
        self.assertEqual(video["audio_understanding"], "analyzed")
        self.assertEqual(video["sound_events"][0]["start"], 2)

    async def test_file_upload_timeout_is_not_repeated(self):
        prepared = workflow.prepare([str(self.fixture())])
        folder, job = workflow.load(prepared["job_id"])
        job["clips"][0]["asr"].update(state="done", segments=[])
        workflow.dump(folder / "job.json", job)
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("fixture", request=request)
        for _ in range(2):
            self.assertEqual((await workflow.advance(prepared["job_id"], True,
                self.api(handler)))["state"], "needs_review")
        self.assertEqual(len(calls), 1)

    async def test_audio_evidence_missing_or_for_silent_input_rejected(self):
        clip = {"start": 10, "duration": 2, "asset_id": "v1", "id": "c1", "av_input": True, "has_audio": False}
        data = {"summary": "画面", "scenes": [], "events": [], "ocr": [], "highlights": [],
                "editing_suggestions": [], **{k: [] for k in workflow.AV_FIELDS}}
        def response():
            return {"body": {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(data)}}]}}
        workflow.parse_visual(response(), clip)
        data["music"] = [{"start": 0, "end": 1, "description": "不存在的音乐"}]
        with self.assertRaisesRegex(ValueError, "without audio"):
            workflow.parse_visual(response(), clip)
        del data["music"]
        with self.assertRaisesRegex(ValueError, "Missing audiovisual"):
            workflow.parse_visual(response(), clip)

    async def test_turbo_timeout_never_retries_or_switches_engine(self):
        await self.exercise_native_timeout("doubao_turbo")

    async def exercise_native_timeout(self, backend):
        prepared = workflow.prepare([str(self.fixture())], task="audio_transcription", asr_backend_name=backend)
        folder, job = workflow.load(prepared["job_id"])
        job["clips"][0]["asr"].update(state="pending_submit", audio_url="https://cdn.volcvideo.com/test.mp3",
                                      url_received_at=1000)
        workflow.dump(folder / "job.json", job)
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.host, "openspeech.bytedance.com")
            raise httpx.ReadTimeout("timed out", request=request)
        api = self.api(handler)
        with patch.object(workflow.time, "time", return_value=1000):
            first = await workflow.advance(prepared["job_id"], True, api)
            second = await workflow.advance(prepared["job_id"], True, api)
        self.assertEqual(first["state"], "needs_review")
        self.assertEqual(second["state"], "needs_review")
        self.assertEqual(len(calls), 1)
        _, saved = workflow.load(prepared["job_id"])
        self.assertEqual(saved["clips"][0]["asr"]["task_id"], calls[0].headers["x-api-request-id"])

    async def test_invalid_bridge_and_native_word_timestamps_rejected(self):
        clip = {"start": 10, "duration": 2, "asset_id": "v1", "id": "c1"}
        for url, duration in (("mediakit://internal", 2), ("http://example.com/a.mp3", 2),
                              ("https://example.com/a.mp3", 30)):
            with self.assertRaises(ValueError):
                workflow.parse_bridge({"result": {"audio_url": url, "duration": duration}}, clip)
        body = {"audio_info": {"duration": 2000}, "result": {"text": "test", "utterances": [
            {"start_time": 500, "end_time": 1500, "text": "test", "words": [
                {"start_time": 600, "end_time": 1900, "text": "test"}]}]}}
        with self.assertRaises(ValueError):
            workflow.parse_doubao(body, clip)


    async def test_native_untimed_english_separators_preserve_words_and_raw_body(self):
        import copy
        clip = {"start": 10, "duration": 2, "asset_id": "v1", "id": "c1"}
        body = {"audio_info": {"duration": 2000}, "result": {"text": "用 AI", "utterances": [
            {"start_time": 500, "end_time": 1500, "text": "用 AI", "words": [
                {"start_time": 500, "end_time": 700, "text": "用"},
                {"start_time": -1, "end_time": -1, "text": " "},
                {"start_time": 900, "end_time": 1400, "text": "AI"},
                {"start_time": -1, "end_time": -1, "text": " "}]}]}}
        original = copy.deepcopy(body)
        segments = workflow.parse_doubao(body, clip)
        self.assertEqual(body, original)
        self.assertEqual(segments[0]["text"], "用 AI")
        self.assertEqual(segments[0]["words"], [
            {"start": 10.5, "end": 10.7, "text": "用"},
            {"start": 10.9, "end": 11.4, "text": "AI"}])

    async def test_native_negative_real_word_or_other_invalid_separator_still_stops(self):
        import copy
        clip = {"start": 0, "duration": 2, "asset_id": "v1", "id": "c1"}
        template = {"audio_info": {"duration": 2000}, "result": {"text": "AI", "utterances": [
            {"start_time": 500, "end_time": 1500, "text": "AI", "words": []}]}}
        for word in ({"start_time": -1, "end_time": -1, "text": "AI"},
                     {"start_time": -1, "end_time": -1, "text": ""},
                     {"start_time": -1, "end_time": 900, "text": " "},
                     {"start_time": 800, "end_time": 1900, "text": " "}):
            with self.subTest(word=word):
                body = copy.deepcopy(template)
                body["result"]["utterances"][0]["words"] = [word]
                with self.assertRaisesRegex(ValueError, "Invalid native ASR word"):
                    workflow.parse_doubao(body, clip)

    async def test_uncertain_visual_call_is_never_repeated(self):
        prepared = workflow.prepare([str(self.fixture(audio=False))], clip_seconds=10)
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("fixture-mediakit-key", request=request)
        api = self.api(handler)
        first = await workflow.advance(prepared["job_id"], True, api)
        self.assertEqual(first["state"], "needs_review")
        second = await workflow.advance(prepared["job_id"], True, api)
        self.assertEqual(second["state"], "needs_review")
        self.assertEqual(len(calls), 1)

    async def test_changed_proxy_is_rejected_before_paid_call(self):
        prepared = workflow.prepare([str(self.fixture(audio=False))], clip_seconds=10)
        _, job = workflow.load(prepared["job_id"])
        Path(job["clips"][0]["video_path"]).write_bytes(b"changed")
        def handler(request):
            self.fail("Changed proxy must not reach network")
        self.assertEqual((await workflow.advance(prepared["job_id"], True, self.api(handler)))["state"], "needs_review")

    async def test_nonfinite_or_out_of_range_provider_timestamps_rejected(self):
        clip = {"start": 10, "duration": 2, "asset_id": "v1", "id": "c1"}
        for start, end in ((0, 5), (math.nan, 1), (0, math.inf), (-1, 1)):
            with self.assertRaises(ValueError):
                workflow.timed([{"start": start, "end": end, "text": "test"}], clip, "text")

    async def test_concurrent_advance_cannot_duplicate_paid_operation(self):
        prepared = workflow.prepare([str(self.fixture(audio=False))], clip_seconds=10)
        folder, job = workflow.load(prepared["job_id"])
        job.pop("visual_transport", None)
        workflow.dump(folder / "job.json", job)
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def handler(request):
            calls.append(request)
            started.set()
            await release.wait()
            generated = {"summary": "blue", "scenes": [], "events": [], "ocr": [],
                         "highlights": [], "editing_suggestions": []}
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
                "message": {"content": json.dumps(generated)}}]})
        api = self.api(handler)
        first = asyncio.create_task(workflow.advance(prepared["job_id"], True, api))
        await started.wait()
        try:
            second = await workflow.advance(prepared["job_id"], True, api)
            self.assertTrue(second["busy"])
        finally:
            release.set()
        result = await first
        self.assertEqual(result["paid_requests_attempted"], 1)
        self.assertEqual(len(calls), 1)

    async def test_independent_media_failure_and_untrusted_upload_destination(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"success": True, "result": {"method": "PUT",
                "upload_url": "https://evil.example/upload", "file_id": "fixture"}})
        media = MediaKit(self.api(handler))
        video = self.fixture(audio=False)
        result = await media.upload(str(video))
        self.assertFalse(result["ok"])
        self.assertEqual(len(calls), 1)
        def fail(request):
            return httpx.Response(200, json={"success": False})
        self.assertFalse((await MediaKit(self.api(fail)).submit("asr-subtitles", {"audio_url": "mediakit://a"}))["ok"])

    async def test_independent_mediakit_stdio_entry(self):
        params = StdioServerParameters(command=sys.executable,
            args=[str(Path(__file__).with_name("mediakit_server.py"))], env=dict(os.environ))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                self.assertEqual(len(names), 5)
                self.assertIn("mediakit_analyze_video", names)
                self.assertNotIn("volc_ark_chat", names)
                result = await session.call_tool("mediakit_connection_status", {})
                self.assertFalse(result.isError)
                self.assertNotIn("fixture-mediakit-key", result.model_dump_json())

if __name__ == "__main__":
    unittest.main(verbosity=2)
