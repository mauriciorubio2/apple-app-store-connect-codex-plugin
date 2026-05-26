#!/usr/bin/env python3
"""Small App Store Connect API client used by the Codex plugin."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


API_BASE = "https://api.appstoreconnect.apple.com"
AUDIENCE = "appstoreconnect-v1"


class AppStoreConnectError(RuntimeError):
    """Raised for Apple API and local credential errors."""


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _read_length(data: bytes, idx: int) -> tuple[int, int]:
    first = data[idx]
    idx += 1
    if first < 0x80:
        return first, idx
    count = first & 0x7F
    if count == 0 or count > 4:
        raise AppStoreConnectError("Unsupported DER length in ECDSA signature")
    value = int.from_bytes(data[idx : idx + count], "big")
    return value, idx + count


def der_ecdsa_to_raw(der: bytes, size: int = 32) -> bytes:
    """Convert a DER-encoded ECDSA signature into JWT's raw r||s form."""

    idx = 0
    if not der or der[idx] != 0x30:
        raise AppStoreConnectError("Expected DER sequence for ECDSA signature")
    idx += 1
    seq_len, idx = _read_length(der, idx)
    seq_end = idx + seq_len
    parts: list[bytes] = []
    for _ in range(2):
        if idx >= len(der) or der[idx] != 0x02:
            raise AppStoreConnectError("Expected DER integer in ECDSA signature")
        idx += 1
        int_len, idx = _read_length(der, idx)
        raw_int = der[idx : idx + int_len]
        idx += int_len
        raw_int = raw_int.lstrip(b"\x00")
        if len(raw_int) > size:
            raise AppStoreConnectError("ECDSA integer is larger than expected")
        parts.append(raw_int.rjust(size, b"\x00"))
    if idx != seq_end:
        raise AppStoreConnectError("Unexpected trailing data in ECDSA signature")
    return b"".join(parts)


def sign_es256_with_openssl(message: bytes, key_path: Path) -> bytes:
    proc = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(key_path)],
        input=message,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise AppStoreConnectError(
            "openssl failed to sign the JWT: " + proc.stderr.decode("utf-8", "replace")
        )
    return der_ecdsa_to_raw(proc.stdout)


@dataclass(frozen=True)
class Credentials:
    key_id: str
    key_path: Path
    issuer_id: str | None = None
    key_type: str = "team"

    @classmethod
    def from_env(cls) -> "Credentials":
        key_id = os.environ.get("ASC_KEY_ID", "").strip()
        key_path = os.environ.get("ASC_KEY_PATH", "").strip()
        issuer_id = os.environ.get("ASC_ISSUER_ID", "").strip() or None
        key_type = os.environ.get("ASC_KEY_TYPE", "team").strip().lower()
        if key_type not in {"team", "individual"}:
            raise AppStoreConnectError("ASC_KEY_TYPE must be team or individual")
        if not key_id:
            raise AppStoreConnectError("ASC_KEY_ID is required")
        if not key_path:
            raise AppStoreConnectError("ASC_KEY_PATH is required")
        path = Path(key_path).expanduser()
        if not path.exists():
            raise AppStoreConnectError(f"ASC_KEY_PATH does not exist: {path}")
        if key_type == "team" and not issuer_id:
            raise AppStoreConnectError("ASC_ISSUER_ID is required for team keys")
        return cls(key_id=key_id, issuer_id=issuer_id, key_path=path, key_type=key_type)

    def token(self, lifetime_seconds: int = 15 * 60, scope: Iterable[str] | None = None) -> str:
        now = int(time.time())
        header = {"alg": "ES256", "kid": self.key_id, "typ": "JWT"}
        payload: dict[str, Any] = {
            "iat": now,
            "exp": now + min(lifetime_seconds, 20 * 60),
            "aud": AUDIENCE,
        }
        if self.key_type == "individual":
            payload["sub"] = "user"
        else:
            payload["iss"] = self.issuer_id
        if scope:
            payload["scope"] = list(scope)
        signing_input = (
            b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
            + "."
            + b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        ).encode("ascii")
        signature = sign_es256_with_openssl(signing_input, self.key_path)
        return signing_input.decode("ascii") + "." + b64url(signature)


class AppStoreConnectClient:
    def __init__(
        self,
        credentials: Credentials | None = None,
        base_url: str | None = None,
        timeout: int = 60,
    ) -> None:
        self.credentials = credentials or Credentials.from_env()
        self.base_url = (base_url or os.environ.get("ASC_API_BASE") or API_BASE).rstrip("/")
        self.timeout = timeout
        self._token: str | None = None
        self._token_expires_at = 0

    def token(self) -> str:
        now = int(time.time())
        if not self._token or self._token_expires_at - now < 60:
            self._token = self.credentials.token()
            self._token_expires_at = now + 15 * 60
        return self._token

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not path.startswith("/"):
            path = "/" + path
        url = self.base_url + path
        if query:
            clean: list[tuple[str, str]] = []
            for key, value in query.items():
                if value is None:
                    continue
                if isinstance(value, (list, tuple)):
                    clean.append((key, ",".join(str(item) for item in value)))
                else:
                    clean.append((key, str(value)))
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        data = None
        headers = {
            "Authorization": "Bearer " + self.token(),
            "Accept": "application/json",
        }
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise AppStoreConnectError(
                f"App Store Connect API {method.upper()} {path} failed with {exc.code}: {detail}"
            ) from exc
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def get(self, path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("GET", path, query=query)

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", path, body=body)

    def patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("PATCH", path, body=body)

    def delete(self, path: str) -> dict[str, Any]:
        return self.request("DELETE", path)


def json_api_body(
    resource_type: str,
    attributes: dict[str, Any] | None = None,
    relationships: dict[str, Any] | None = None,
    resource_id: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {"type": resource_type}
    if resource_id:
        data["id"] = resource_id
    if attributes:
        data["attributes"] = {key: value for key, value in attributes.items() if value is not None}
    if relationships:
        data["relationships"] = relationships
    return {"data": data}


def relationship(resource_type: str, resource_id: str) -> dict[str, Any]:
    return {"data": {"type": resource_type, "id": resource_id}}


def file_hash(path: Path, algorithm: str) -> str:
    hasher = hashlib.new(algorithm.lower().replace("_", ""))
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def upload_operations(file_path: Path, operations: list[dict[str, Any]], timeout: int = 300) -> None:
    with file_path.open("rb") as source:
        for operation in operations:
            offset = int(operation.get("offset", 0))
            length = int(operation["length"])
            source.seek(offset)
            chunk = source.read(length)
            headers = {
                item["name"]: item["value"]
                for item in operation.get("requestHeaders", [])
                if item.get("name") and item.get("value") is not None
            }
            req = urllib.request.Request(
                operation["url"],
                data=chunk,
                headers=headers,
                method=operation.get("method", "PUT"),
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout):
                    pass
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")
                raise AppStoreConnectError(
                    f"Upload operation failed with {exc.code}: {detail}"
                ) from exc


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))
