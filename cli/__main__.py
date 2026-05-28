"""Interactive entrypoint: pick a plugin, pick a version, mirror it."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import questionary
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from . import github_releases, jetbrains, update_xml
from .jetbrains import PluginSummary, PluginVersion
from .manifest import Manifest, PluginEntry

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "plugins.json"
PUBLIC_DIR = REPO_ROOT / "public"
UPDATE_XML_PATH = PUBLIC_DIR / "updatePlugins.xml"

console = Console()


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value or value.startswith("ghp_replace_me") or value.startswith("your-org"):
        console.print(f"[red]Missing or placeholder env var:[/red] {name}")
        console.print("Copy .env.example to .env and fill in real values.")
        sys.exit(2)
    return value


def _pick_plugin() -> PluginSummary | None:
    mode = questionary.select(
        "How do you want to find the plugin?",
        choices=[
            questionary.Choice("Search by name", "search"),
            questionary.Choice("Paste plugin ID or marketplace URL", "paste"),
            questionary.Choice("Cancel", "cancel"),
        ],
    ).ask()
    if mode in (None, "cancel"):
        return None

    if mode == "search":
        query = questionary.text("Search query:").ask()
        if not query:
            return None
        with console.status("Searching JetBrains Marketplace…"):
            results = jetbrains.search_plugins(query)
        if not results:
            console.print("[yellow]No results.[/yellow]")
            return None
        choice = questionary.select(
            "Pick a plugin:",
            choices=[questionary.Choice(p.label, p) for p in results],
        ).ask()
        return choice

    # Paste fallback
    raw = questionary.text("Plugin ID, xmlId, or marketplace URL:").ask()
    if not raw:
        return None
    try:
        plugin_id = jetbrains.resolve_plugin_id(raw)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return None
    with console.status(f"Fetching plugin {plugin_id}…"):
        return jetbrains.get_plugin(plugin_id)


def _pick_version(plugin: PluginSummary) -> PluginVersion | None:
    with console.status(f"Fetching versions for {plugin.name}…"):
        versions = jetbrains.get_versions(plugin.id)
    if not versions:
        console.print("[yellow]No versions found.[/yellow]")
        return None
    return questionary.select(
        "Pick a version:",
        choices=[questionary.Choice(v.label, v) for v in versions],
    ).ask()


def mirror_one(token: str, repo_full: str) -> bool:
    plugin = _pick_plugin()
    if not plugin:
        return False
    version = _pick_version(plugin)
    if not version:
        return False

    console.print(
        Panel.fit(
            f"[bold]{plugin.name}[/bold]  v{version.version}\n"
            f"xml_id: {plugin.xml_id}\n"
            f"since-build: {version.since or '*'}   until-build: {version.until or '*'}",
            title="Plugin to mirror",
        )
    )
    if not questionary.confirm("Download from JetBrains and push to GitHub?", default=True).ask():
        return False

    with tempfile.TemporaryDirectory(prefix="jb-plugin-") as tmp:
        download_dir = Path(tmp)
        with console.status(f"Downloading {version.filename}…"):
            artifact = jetbrains.download_plugin(version, download_dir)
        size_mb = artifact.stat().st_size / (1024 * 1024)
        console.print(f"  → downloaded {artifact.name} ({size_mb:.1f} MB)")

        with console.status("Creating GitHub release…"):
            release = github_releases.ensure_release(
                token=token,
                repo_full_name=repo_full,
                plugin_xml_id=plugin.xml_id,
                plugin_name=plugin.name,
                version=version.version,
                notes=version.notes,
            )
        with console.status("Uploading asset…"):
            download_url = github_releases.upload_asset(release, artifact)
        console.print(f"  → uploaded to {download_url}")

    entry = PluginEntry(
        plugin_xml_id=plugin.xml_id,
        plugin_id=plugin.id,
        name=plugin.name,
        vendor=plugin.vendor,
        version=version.version,
        since_build=version.since,
        until_build=version.until,
        download_url=download_url,
        filename=version.filename,
    )
    manifest = Manifest.load(MANIFEST_PATH)
    manifest.upsert(entry)
    manifest.save(MANIFEST_PATH)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    update_xml.write(manifest, UPDATE_XML_PATH)
    console.print(
        f"[green]✓[/green] manifest updated; regenerated [bold]{UPDATE_XML_PATH.relative_to(REPO_ROOT)}[/bold]"
    )
    return True


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    token = _require_env("GITHUB_TOKEN")
    repo_full = _require_env("GITHUB_REPO")

    console.print(
        Panel.fit(
            f"Mirror target: [bold]{repo_full}[/bold]\n"
            f"Manifest: {MANIFEST_PATH.relative_to(REPO_ROOT)}\n"
            f"Output XML: {UPDATE_XML_PATH.relative_to(REPO_ROOT)}",
            title="JetBrains plugin mirror",
        )
    )

    while True:
        try:
            mirror_one(token, repo_full)
        except KeyboardInterrupt:
            console.print("\n[dim]aborted[/dim]")
            return
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Error:[/red] {exc}")
        if not questionary.confirm("Mirror another plugin?", default=False).ask():
            break

    console.print(
        "\n[bold]Done.[/bold] Commit & push changes to publish:"
        "\n  git add plugins.json public/updatePlugins.xml"
        "\n  git commit -m 'mirror plugin update'"
        "\n  git push"
    )


if __name__ == "__main__":
    main()
