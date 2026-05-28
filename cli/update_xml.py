"""Generate the updatePlugins.xml served to IntelliJ."""

from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement

from .manifest import Manifest


def _indent(elem: Element, level: int = 0) -> None:
    pad = "\n" + "  " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = pad + "  "
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = pad
    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = pad


def render(manifest: Manifest) -> bytes:
    root = Element("plugins")
    for entry in manifest.latest_per_plugin():
        plugin = SubElement(
            root,
            "plugin",
            {
                "id": entry.plugin_xml_id,
                "url": entry.download_url,
                "version": entry.version,
            },
        )
        SubElement(plugin, "name").text = entry.name
        SubElement(plugin, "vendor").text = entry.vendor
        attrs: dict[str, str] = {}
        if entry.since_build:
            attrs["since-build"] = entry.since_build
        if entry.until_build:
            attrs["until-build"] = entry.until_build
        if attrs:
            SubElement(plugin, "idea-version", attrs)
    _indent(root)
    from io import BytesIO

    buf = BytesIO()
    ElementTree(root).write(buf, encoding="UTF-8", xml_declaration=True)
    return buf.getvalue()


def write(manifest: Manifest, path: Path) -> None:
    path.write_bytes(render(manifest))
