"""Non-blocking GitHub release update checking.

The checker fetches only public release metadata from the project's GitHub
repository. It never sends message content, window identity, or local
application data. Network access is opt-in from the tray/orb menu and uses a
short timeout.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import urllib.request
from typing import Callable, Optional

_RELEASES_URL = "https://api.github.com/repos/Pyraxxz/Floating-Bar/releases/latest"
_TIMEOUT_S = 4.0
_VERSION_RE = re.compile(r"^[vV]?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    url: str


def parse_version(value: str) -> tuple[int, int, int]:
    match = _VERSION_RE.fullmatch(str(value or "").strip())
    if not match:
        raise ValueError("invalid semantic version")
    return tuple(int(part) for part in match.groups())


def is_newer_version(current: str, candidate: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def fetch_latest_release(
    *,
    url: str = _RELEASES_URL,
    timeout: float = _TIMEOUT_S,
    opener: Optional[Callable] = None,
) -> ReleaseInfo:
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "FloatingBar-update-check",
        },
    )
    with opener(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    tag = str(payload.get("tag_name", "")).strip()
    html_url = str(payload.get("html_url", "")).strip()
    parse_version(tag)
    if not html_url.startswith("https://github.com/"):
        raise ValueError("release URL is not trusted")
    return ReleaseInfo(version=tag.lstrip("vV"), url=html_url)


__all__ = ["ReleaseInfo", "fetch_latest_release", "is_newer_version", "parse_version"]
