"""Server-side startup script.

Runs once when the nginx container starts:

* Reads /srv/plugins.json (bind-mounted from the host).
* Always regenerates /srv/static/updatePlugins.xml from it.
* If LOCAL_CACHE=true, also downloads every plugin asset into
  /srv/static/plugins/<filename> (skipping files already there) and rewrites
  the XML's <plugin url=…> to point at the locally served copy.

Then `exec nginx` takes over.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement

MANIFEST_PATH = Path("/srv/plugins.json")
STATIC_DIR = Path("/srv/static")
PLUGINS_DIR = STATIC_DIR / "plugins"
XML_PATH = STATIC_DIR / "updatePlugins.xml"

LOCAL_CACHE = os.environ.get("LOCAL_CACHE", "false").lower() == "true"
# Optional absolute base for plugin URLs in local-cache mode. If unset, URLs
# are emitted as relative paths (resolved by the IDE against the XML's URL),
# which works out of the box for most setups.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")


def log(msg: str) -> None:
    print(f"[entrypoint] {msg}", flush=True)


def load_manifest() -> list[dict]:
    if not MANIFEST_PATH.exists():
        log(f"no manifest at {MANIFEST_PATH}; serving empty index")
        return []
    data = json.loads(MANIFEST_PATH.read_text())
    return data.get("plugins", [])


def latest_per_plugin(entries: list[dict]) -> list[dict]:
    """Match cli/manifest.py: insertion order, last write wins per xml_id."""
    seen: dict[str, dict] = {}
    for entry in entries:
        seen[entry["plugin_xml_id"]] = entry
    return list(seen.values())


def download(url: str, dest: Path) -> None:
    log(f"  fetching {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "jb-marketplace/1"})
    with urllib.request.urlopen(req, timeout=600) as resp, tmp.open("wb") as fh:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
    tmp.rename(dest)


def prefetch(entries: list[dict]) -> dict[str, str]:
    """Download any missing assets; return xml_id+version → local URL map."""
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    local_urls: dict[str, str] = {}
    for entry in entries:
        filename = entry["filename"]
        dest = PLUGINS_DIR / filename
        if dest.exists() and dest.stat().st_size > 0:
            log(f"  cached: {filename}")
        else:
            try:
                download(entry["download_url"], dest)
            except Exception as exc:  # noqa: BLE001
                log(f"  ERROR fetching {filename}: {exc}")
                continue
        if PUBLIC_BASE_URL:
            url = f"{PUBLIC_BASE_URL}/plugins/{filename}"
        else:
            url = f"plugins/{filename}"
        local_urls[f"{entry['plugin_xml_id']}@{entry['version']}"] = url
    return local_urls


def render_xml(entries: list[dict], url_overrides: dict[str, str]) -> bytes:
    root = Element("plugins")
    for entry in entries:
        key = f"{entry['plugin_xml_id']}@{entry['version']}"
        url = url_overrides.get(key, entry["download_url"])
        plugin = SubElement(
            root,
            "plugin",
            {
                "id": entry["plugin_xml_id"],
                "url": url,
                "version": entry["version"],
            },
        )
        SubElement(plugin, "name").text = entry["name"]
        SubElement(plugin, "vendor").text = entry["vendor"]
        attrs: dict[str, str] = {}
        if entry.get("since_build"):
            attrs["since-build"] = entry["since_build"]
        if entry.get("until_build"):
            attrs["until-build"] = entry["until_build"]
        if attrs:
            SubElement(plugin, "idea-version", attrs)

    from io import BytesIO

    buf = BytesIO()
    ElementTree(root).write(buf, encoding="UTF-8", xml_declaration=True)
    return buf.getvalue()


def main() -> int:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    all_entries = load_manifest()
    entries = latest_per_plugin(all_entries)
    log(f"manifest: {len(all_entries)} entries, {len(entries)} latest-per-plugin")
    log(f"LOCAL_CACHE={'on' if LOCAL_CACHE else 'off'}")

    url_overrides: dict[str, str] = {}
    if LOCAL_CACHE and entries:
        url_overrides = prefetch(entries)

    XML_PATH.write_bytes(render_xml(entries, url_overrides))
    log(f"wrote {XML_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
