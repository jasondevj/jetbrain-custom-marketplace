"""Upload plugin artifacts to GitHub Releases."""

from __future__ import annotations

from pathlib import Path

from github import Github, GithubException
from github.GitRelease import GitRelease
from github.Repository import Repository


def _repo(token: str, repo_full_name: str) -> Repository:
    gh = Github(token)
    return gh.get_repo(repo_full_name)


def release_tag(plugin_xml_id: str, version: str) -> str:
    """Stable tag scheme: one release per plugin+version."""
    safe_version = version.replace(" ", "_")
    return f"plugin/{plugin_xml_id}@{safe_version}"


def ensure_release(
    token: str,
    repo_full_name: str,
    plugin_xml_id: str,
    plugin_name: str,
    version: str,
    notes: str | None = None,
) -> GitRelease:
    """Create the release if missing, otherwise return the existing one."""
    repo = _repo(token, repo_full_name)
    tag = release_tag(plugin_xml_id, version)
    try:
        return repo.get_release(tag)
    except GithubException as exc:
        if exc.status != 404:
            raise
    body = notes or f"{plugin_name} {version}"
    return repo.create_git_release(
        tag=tag,
        name=f"{plugin_name} {version}",
        message=body,
        draft=False,
        prerelease=False,
    )


def upload_asset(release: GitRelease, file_path: Path) -> str:
    """Upload (or replace) an asset on the release; return its public URL."""
    for asset in release.get_assets():
        if asset.name == file_path.name:
            asset.delete_asset()
    asset = release.upload_asset(str(file_path), name=file_path.name)
    return asset.browser_download_url
