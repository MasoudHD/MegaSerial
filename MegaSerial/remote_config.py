"""Load app metadata (version hints, donation links) from a remote gist or bundled fallback."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from .icons import resource_path

REMOTE_CONFIG_URL = (
    "https://gist.githubusercontent.com/MasoudHD/"
    "cb11b5b7f12cf8f42e065ae338fa3d30/raw/config.json"
)

DONATE_LABELS = {
    "buymeacoffee": "Buy Me a Coffee",
    "buymecoffee": "Buy Me a Coffee",
    "donito": "Donito",
}


def _parse_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Gist JSON may include trailing commas; strip them and retry once.
        fixed = re.sub(r",(\s*[}\]])", r"\1", text)
        data = json.loads(fixed)
    if not isinstance(data, dict):
        raise ValueError("config root must be an object")
    return data


def donate_link_label(key: str) -> str:
    normalized = key.strip().lower()
    if normalized in DONATE_LABELS:
        return DONATE_LABELS[normalized]
    return key.replace("_", " ").strip().title() or key


def parse_donate_links(raw: Any) -> list[tuple[str, str]]:
    """Normalize gist/bundled donate config into ``[(button label, url), ...]``.

    Supported ``donate_links`` shapes:

    - List (recommended for full control from the gist):

      ``[{"name": "Buy Me a Coffee", "url": "https://..."}, ...]``

    - Dict of label -> url:

      ``{"Buy Me a Coffee": "https://...", "My Site": "https://..."}``

    - Legacy dict of id -> url (label from ``DONATE_LABELS`` or the id):

      ``{"buymeacoffee": "https://...", "donito": "https://..."}``
    """
    links: list[tuple[str, str]] = []

    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("label") or item.get("title")
            url = item.get("url") or item.get("link")
            if name and url:
                links.append((str(name).strip(), str(url).strip()))
        return links

    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, str) and value.strip():
                links.append((donate_link_label(str(key)), value.strip()))
            elif isinstance(value, dict):
                name = value.get("name") or value.get("label") or donate_link_label(str(key))
                url = value.get("url") or value.get("link")
                if name and url:
                    links.append((str(name).strip(), str(url).strip()))
        return links

    return links


def load_bundled_config() -> dict[str, Any]:
    path = resource_path("resources", "app_config.json")
    return _parse_json(path.read_text(encoding="utf-8"))


def fetch_remote_config(url: str = REMOTE_CONFIG_URL, timeout: float = 8.0) -> dict[str, Any]:
    cache_bust = int(time.time())
    sep = "&" if "?" in url else "?"
    fetch_url = f"{url}{sep}t={cache_bust}"
    req = urllib.request.Request(
        fetch_url,
        headers={
            "User-Agent": "MegaSerial",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return _parse_json(raw)


def load_app_config(*, prefer_remote: bool = True) -> dict[str, Any]:
    """Return bundled config, replaced by the remote gist when reachable."""
    config = load_bundled_config()
    if not prefer_remote:
        return config
    try:
        remote = fetch_remote_config()
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return config
    merged = dict(config)
    for key, value in remote.items():
        if key == "donate_links":
            merged["donate_links"] = value
        else:
            merged[key] = value
    return merged


def donate_links_from_config(config: dict[str, Any]) -> list[tuple[str, str]]:
    return parse_donate_links(config.get("donate_links"))
