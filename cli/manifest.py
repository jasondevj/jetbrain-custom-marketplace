"""Read/write the local plugins.json manifest."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class PluginEntry:
    plugin_xml_id: str
    plugin_id: int
    name: str
    vendor: str
    version: str
    since_build: str | None
    until_build: str | None
    download_url: str
    filename: str

    @classmethod
    def from_dict(cls, data: dict) -> "PluginEntry":
        return cls(**data)


@dataclass
class Manifest:
    plugins: list[PluginEntry] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text())
        return cls(
            plugins=[PluginEntry.from_dict(p) for p in raw.get("plugins", [])],
        )

    def save(self, path: Path) -> None:
        payload = {"plugins": [asdict(p) for p in self.plugins]}
        path.write_text(json.dumps(payload, indent=2) + "\n")

    def upsert(self, entry: PluginEntry) -> None:
        """Replace any prior entry for the same xml_id+version, then append."""
        self.plugins = [
            p
            for p in self.plugins
            if not (p.plugin_xml_id == entry.plugin_xml_id and p.version == entry.version)
        ]
        self.plugins.append(entry)

    def latest_per_plugin(self) -> list[PluginEntry]:
        """Return only the most recently-added entry per plugin_xml_id.

        Order in the file is insertion order; the most recent upsert wins.
        """
        seen: dict[str, PluginEntry] = {}
        for entry in self.plugins:
            seen[entry.plugin_xml_id] = entry
        return list(seen.values())
