"""HTTP adapter (C-N): the only module allowed to use urllib.request.

Stdlib urllib only — no requests/httpx (runtime_deps ratchet). GET is the
entire verb set this project needs for endpoint health. `http_get_json`
never raises for transport or parse trouble: it returns
(status, parsed-body-or-None) so callers report health without
exception plumbing. Status 0 means the request never reached an HTTP
response — connection refused, DNS failure, or timeout. Bodies are read
up to a cap; an oversized or non-object body is None, not a crash.
"""
import json
import urllib.error
import urllib.request

_MAX_BODY = 65_536


def _parse_json_object(raw: bytes) -> dict | None:
    try:
        parsed = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def http_get_json(url: str, timeout: float = 5.0) -> tuple[int, dict | None]:
    """GET url; return (HTTP status, JSON object or None). 0 = no response."""
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            body = _parse_json_object(response.read(_MAX_BODY))
    except urllib.error.HTTPError as exc:  # non-2xx: a real response
        return int(exc.code), _parse_json_object(exc.read(_MAX_BODY))
    except OSError:  # URLError, socket/TimeoutError, refused, DNS
        return 0, None
    return status, body


def http_post_json(
    url: str, payload: dict, token: str | None = None, timeout: float = 5.0
) -> tuple[int, dict | None]:
    """POST payload as one JSON body; return (status, parsed-or-None). 0 = no
    response. Same never-raises contract as http_get_json."""
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            raw = response.read(_MAX_BODY)
    except urllib.error.HTTPError as exc:
        return int(exc.code), _parse_json_object(exc.read(_MAX_BODY))
    except OSError:
        return 0, None
    return status, _parse_json_object(raw)
