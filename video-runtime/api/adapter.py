"""Thin Volcengine API adapter. No routing, polling, media processing or workflows."""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent
ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"
MEDIAKIT_BASE = "https://amk-ark.cn-beijing.volces.com/api/v1"
MEDIAKIT_TOOLS_BASE = "https://mediakit.cn-beijing.volces.com/api/v1"
ASR_BASE = "https://openspeech.bytedance.com/api/v3/auc/bigmodel"
KEYS = {
    "ark": ("ARK_API_KEY", "ark_key_file"),
    "asr": ("VOLC_ASR_API_KEY", "asr_key_file"),
    "mediakit": ("VOLC_MEDIAKIT_API_KEY", "mediakit_key_file"),
}


class Credentials:
    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or ROOT / "connection.json"

    def get(self, service: str) -> str:
        env_name, file_field = KEYS[service]
        value = (os.environ.get(env_name) or os.environ.get("VOLC_API_KEY", "")).strip()
        if not value and self.config_path.exists():
            try:
                config = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
                filename = config.get(file_field) or config.get("shared_key_file", "")
                if filename:
                    content = Path(filename).read_text(encoding="utf-8-sig")
                    line = config.get(service + "_key_line")
                    if line is not None:
                        lines = content.splitlines()
                        if type(line) is not int or not 1 <= line <= len(lines):
                            raise ValueError("Invalid credential line selection")
                        value = lines[line - 1].strip()
                    else:
                        value = content.strip()
                    prefix = config.get(service + "_key_prefix")
                    if prefix is not None:
                        # Strip only the explicitly configured label. A changed label
                        # must fail locally rather than send the wrong line as a key.
                        if not isinstance(prefix, str) or not prefix or not value.startswith(prefix):
                            raise ValueError("Credential label does not match configuration")
                        value = value[len(prefix):].strip()
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f"Cannot read local {service} credential configuration") from None
        if not value:
            raise ValueError(f"Missing {service} credential; configure {env_name}, VOLC_API_KEY or a key file")
        if any(ch.isspace() for ch in value):
            raise ValueError(f"The {service} credential file must contain a single raw key")
        return value

    def ready(self, service: str) -> bool:
        try:
            self.get(service)
            return True
        except ValueError:
            return False

    def secret_values(self) -> list[str]:
        values = []
        for service in KEYS:
            try:
                values.append(self.get(service))
            except ValueError:
                pass
        values.extend(os.environ.get(name, "") for name in
                      ("VOLC_ASR_APP_ID", "VOLC_ASR_ACCESS_TOKEN"))
        return [value for value in values if value]


class VolcAPI:
    def __init__(self, credentials: Credentials | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.credentials = credentials or Credentials()
        self.transport = transport

    def status(self) -> dict[str, Any]:
        legacy_asr = bool(os.environ.get("VOLC_ASR_APP_ID") and
                          os.environ.get("VOLC_ASR_ACCESS_TOKEN"))
        return {
            "transport": "stdio",
            "credential_configured": {
                "ark": self.credentials.ready("ark"),
                "asr": self.credentials.ready("asr") or legacy_asr,
                "mediakit": self.credentials.ready("mediakit"),
            },
            "network_verified": False,
            "note": "Local configuration only; no network call or account permission check.",
        }

    def _redact(self, value: Any, secrets: list[str] | None = None) -> Any:
        if secrets is None:
            secrets = self.credentials.secret_values()
        if isinstance(value, dict):
            return {key: self._redact(item, secrets) for key, item in value.items()}
        if isinstance(value, list):
            return [self._redact(item, secrets) for item in value]
        if isinstance(value, str):
            for secret in secrets:
                value = value.replace(secret, "[REDACTED]")
            value = re.sub(r"ark-\*+[A-Za-z0-9-]*", "[REDACTED]", value)
        return value

    async def _post(self, url: str, body: dict[str, Any], headers: dict[str, str],
                    timeout_seconds: int, asr: bool = False, *, method="POST", multipart=None) -> dict[str, Any]:
        if not 1 <= timeout_seconds <= 600:
            raise ValueError("timeout_seconds must be between 1 and 600")
        # Credentials go only to these fixed HTTPS API endpoints; redirects are disabled.
        try:
            async with httpx.AsyncClient(transport=self.transport, follow_redirects=False,
                                        timeout=timeout_seconds, trust_env=self.transport is None) as client:
                options = multipart if multipart is not None else ({"json": body} if method == "POST" else {})
                response = await client.request(method, url, headers=headers, **options)
        except httpx.TimeoutException:
            return {"ok": False, "error": "timeout", "retry_performed": False,
                    "note": "The provider may have accepted the request. Check before resubmitting."}
        except httpx.HTTPError as exc:
            return {"ok": False, "error": "transport_error", "transport_error_type": type(exc).__name__,
                    "retry_performed": False, "note": "Acceptance may be uncertain; inspect before resubmitting."}
        try:
            data = response.json() if response.content else None
        except ValueError:
            # Do not return a proxy HTML page or dump request/credential information.
            return {"ok": False, "http_status": response.status_code,
                    "error": "non_json_response", "retry_performed": False}
        provider_code = response.headers.get("X-Api-Status-Code") if asr else None
        valid_asr = provider_code in {"20000000", "20000001", "20000002", "20000003"}
        result = {
            "ok": response.is_success and (valid_asr if asr else not
                  (isinstance(data, dict) and (data.get("error") or data.get("success") is False))),
            "http_status": response.status_code,
            "request_id": response.headers.get("X-Tt-Logid") or
                          response.headers.get("X-Request-Id"),
            "body": data,
        }
        if asr:
            result["provider_code"] = provider_code
            result["provider_message"] = response.headers.get("X-Api-Message")
            result["state"] = {"20000000": "success", "20000001": "processing",
                               "20000002": "queued", "20000003": "no_speech"}.get(provider_code, "error")
        return self._redact(result)

    async def video_file(self, *, path=None, model=None, fps=1, file_id=None):
        """Upload an audiovisual proxy once, or query its saved Ark File ID."""
        headers = {"Authorization": "Bearer " + self.credentials.get("ark")}
        if file_id is not None:
            if not re.fullmatch(r"file-[A-Za-z0-9_-]+", file_id):
                raise ValueError("Invalid Ark File ID")
            return await self._post(ARK_BASE + "/files/" + file_id, {}, headers, 60, method="GET")
        if not isinstance(model, str) or not model:
            raise ValueError("File preprocessing requires a model ID")
        with Path(path).open("rb") as stream:
            return await self._post(ARK_BASE + "/files", {}, headers, 300, multipart={
                "data": {"purpose": "user_data", "preprocess_configs[video][model]": model,
                         "preprocess_configs[video][fps]": str(fps)},
                "files": {"file": ("clip.mp4", stream, "video/mp4")}})

    async def chat(self, request: dict[str, Any], *, mediakit: bool = False,
                   responses: bool = False, timeout_seconds: int = 180) -> dict[str, Any]:
        input_field = "input" if responses else "messages"
        if not isinstance(request.get("model"), str) or not request["model"].strip():
            raise ValueError("Specify the exact model or endpoint ID in request.model")
        if input_field not in request or not request[input_field]:
            raise ValueError(f"request.{input_field} is required")
        if request.get("stream"):
            raise ValueError("Streaming is not supported by this MCP tool; use stream=false")
        body = dict(request, stream=False)
        key = self.credentials.get("ark")
        if mediakit:
            key += "/" + self.credentials.get("mediakit")
        base = MEDIAKIT_BASE if mediakit else ARK_BASE
        endpoint = "/responses" if responses else "/chat/completions"
        return await self._post(base + endpoint, body, {"Authorization": f"Bearer {key}"},
                                timeout_seconds)

    def _asr_headers(self, request_id: str, resource_id: str) -> dict[str, str]:
        if not request_id or any(ch in request_id for ch in "\r\n"):
            raise ValueError("A valid request_id is required")
        if resource_id not in {"volc.seedasr.auc", "volc.bigasr.auc",
                                "volc.bigasr.auc_turbo"}:
            raise ValueError("Unsupported ASR resource ID")
        try:
            auth = {"X-Api-Key": self.credentials.get("asr")}
        except ValueError:
            appid = os.environ.get("VOLC_ASR_APP_ID", "")
            token = os.environ.get("VOLC_ASR_ACCESS_TOKEN", "")
            if not appid or not token:
                raise ValueError("Missing ASR API key or legacy App ID/Access Token") from None
            auth = {"X-Api-App-Key": appid, "X-Api-Access-Key": token}
        return {**auth, "X-Api-Resource-Id": resource_id, "X-Api-Request-Id": request_id}

    async def asr(self, operation: str, request: dict[str, Any] | None = None,
                  request_id: str | None = None, resource_id: str = "volc.seedasr.auc",
                  timeout_seconds: int = 180) -> dict[str, Any]:
        if operation not in {"submit", "query", "flash"}:
            raise ValueError("Unsupported ASR operation")
        if operation != "query":
            audio = request.get("audio") if request else None
            if not isinstance(audio, dict) or not (audio.get("url") or
                    (isinstance(audio.get("data"), str) and audio["data"])):
                raise ValueError("request.audio.url or base64 audio.data is required")
        elif not request_id:
            raise ValueError("query requires the original submit request_id")
        task_id = request_id or str(uuid.uuid4())
        if operation == "flash":
            resource_id = "volc.bigasr.auc_turbo"
        elif resource_id == "volc.bigasr.auc_turbo":
            raise ValueError("Use flash for the turbo resource")
        headers = self._asr_headers(task_id, resource_id)
        if operation != "query":
            headers["X-Api-Sequence"] = "-1"
        endpoint = "/recognize/flash" if operation == "flash" else "/" + operation
        result = await self._post(ASR_BASE + endpoint, request or {}, headers, timeout_seconds, asr=True)
        result["task_id"] = task_id
        result["resource_id"] = resource_id
        if operation == "submit" and result.get("state") == "success":
            result["state"] = "submitted"
        return result
