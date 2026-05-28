"""Client for the JetBrains Marketplace public API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import requests

API_BASE = "https://plugins.jetbrains.com/api"
DOWNLOAD_BASE = "https://plugins.jetbrains.com"


@dataclass
class PluginSummary:
    id: int
    xml_id: str
    name: str
    vendor: str

    @property
    def label(self) -> str:
        return f"{self.name}  (id={self.id}, {self.xml_id}) — {self.vendor}"


@dataclass
class PluginVersion:
    update_id: int
    version: str
    since: str | None
    until: str | None
    file: str
    notes: str | None

    @property
    def label(self) -> str:
        compat = f"{self.since or '*'} → {self.until or '*'}"
        return f"{self.version}  [{compat}]"

    @property
    def download_url(self) -> str:
        return f"{DOWNLOAD_BASE}/files/{self.file}"

    @property
    def filename(self) -> str:
        return Path(self.file).name


def search_plugins(query: str, max_results: int = 20) -> list[PluginSummary]:
    """Search the JetBrains plugin marketplace by free-text query."""
    resp = requests.get(
        f"{API_BASE}/searchPlugins",
        params={"search": query, "max": max_results},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("plugins", []):
        results.append(
            PluginSummary(
                id=item["id"],
                xml_id=item.get("xmlId") or item.get("link", "").strip("/"),
                name=item["name"],
                vendor=item.get("vendor", "") or "unknown",
            )
        )
    return results


def get_plugin(plugin_id: int) -> PluginSummary:
    """Fetch plugin metadata by numeric ID."""
    resp = requests.get(f"{API_BASE}/plugins/{plugin_id}", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return PluginSummary(
        id=data["id"],
        xml_id=data.get("xmlId") or data.get("link", "").strip("/"),
        name=data["name"],
        vendor=(data.get("vendor") or {}).get("name", "unknown")
        if isinstance(data.get("vendor"), dict)
        else (data.get("vendor") or "unknown"),
    )


def get_versions(plugin_id: int, max_results: int = 30) -> list[PluginVersion]:
    """List the most recent versions/updates available for a plugin."""
    resp = requests.get(
        f"{API_BASE}/plugins/{plugin_id}/updates",
        params={"size": max_results},
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json()
    versions = []
    for item in items:
        versions.append(
            PluginVersion(
                update_id=item["id"],
                version=item["version"],
                since=item.get("since") or None,
                until=item.get("until") or None,
                file=item["file"],
                notes=item.get("notes"),
            )
        )
    return versions


def download_plugin(version: PluginVersion, dest_dir: Path) -> Path:
    """Download a plugin artifact to dest_dir; returns the saved path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / version.filename
    with requests.get(version.download_url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)
    return dest


def resolve_plugin_id(value: str) -> int:
    """Resolve a numeric ID, marketplace URL, or 'xmlId' to a numeric plugin ID."""
    value = value.strip()
    if value.isdigit():
        return int(value)
    # URL like https://plugins.jetbrains.com/plugin/17718-github-copilot
    if "plugins.jetbrains.com" in value:
        tail = value.rstrip("/").split("/plugin/")[-1]
        head = tail.split("-", 1)[0]
        if head.isdigit():
            return int(head)
    # Treat as xmlId — search and pick the exact match
    results = search_plugins(value, max_results=10)
    for plugin in results:
        if plugin.xml_id == value:
            return plugin.id
    if results:
        return results[0].id
    raise ValueError(f"Could not resolve plugin reference: {value!r}")
