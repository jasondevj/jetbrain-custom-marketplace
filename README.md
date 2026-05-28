# JetBrains custom plugin marketplace

A tiny self-hosted mirror of JetBrains Marketplace plugins, designed for
corporate networks that block `plugins.jetbrains.com`.

- **Storage:** plugin binaries are pushed to **GitHub Releases** of this repo
  (no LFS, unlimited public bandwidth, 2 GB per asset).
- **Index:** a Python CLI builds an `updatePlugins.xml` manifest that points
  IntelliJ at the GitHub Release asset URLs.
- **Server:** a tiny nginx container serves `updatePlugins.xml` — IntelliJ
  fetches plugin binaries directly from GitHub, the server never proxies them.

## Components

```
.
├── cli/                  # Python CLI (interactive)
├── docker/               # Dockerfiles + nginx config
├── public/               # served by nginx (index.html, updatePlugins.xml)
├── plugins.json          # source-of-truth manifest of mirrored plugins
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## One-time setup

1. **Create the repo on GitHub.** This same repo will hold both the tool and
   the plugin Release assets. It must be **public** so the corporate-network
   IDEs can download from `releases/download/...` without auth.
2. **Create a Personal Access Token** with `repo` scope at
   <https://github.com/settings/tokens>.
3. **Copy `.env.example` → `.env`** and fill in:
   ```env
   GITHUB_TOKEN=ghp_…
   GITHUB_REPO=your-org/your-repo
   PUBLIC_BASE_URL=http://plugins.intranet.acme.corp
   ```
4. **Build the images** (one-off):
   ```bash
   docker compose --profile cli build
   docker compose build server
   ```

## Mirroring a plugin

```bash
docker compose run --rm cli
```

Interactive flow:

1. Search by name *(or paste a plugin ID / marketplace URL)*.
2. Pick a version from the list — `since-build` / `until-build` are filled in
   automatically from the JetBrains API.
3. The CLI downloads the artifact from JetBrains, creates a GitHub Release
   (`plugin/<xmlId>@<version>`), uploads the asset, then updates
   `plugins.json` and regenerates `public/updatePlugins.xml`.

Commit and push the updated manifest/XML so the hosted server can pick them up:

```bash
git add plugins.json public/updatePlugins.xml
git commit -m "mirror: <plugin> <version>"
git push
```

## Hosting

```bash
docker compose up -d server
```

The server listens on port `8080` and serves:

- `http://<host>:8080/` — landing page
- `http://<host>:8080/updatePlugins.xml` — the IntelliJ-readable index
  (regenerated at every container start from `plugins.json`)

When you push new mirror updates, redeploy with:

```bash
git pull && docker compose up -d --build server
```

### Two serving modes

Set `LOCAL_CACHE` in your `.env` to choose how plugin binaries are delivered:

| `LOCAL_CACHE` | Where binaries come from | Disk | First start | Use when |
| --- | --- | --- | --- | --- |
| `false` *(default)* | IDE downloads straight from GitHub Releases | tiny | instant | dev networks can reach `objects.githubusercontent.com` |
| `true` | Server pre-downloads all assets into a Docker volume and serves them from `/plugins/<file>` | full size of every mirrored plugin | slow (downloads everything once) | corporate networks where IDEs cannot reach GitHub at all, or where you want LAN-speed installs |

In `LOCAL_CACHE=true` mode the container creates a named volume
(`plugin-cache`) and only re-downloads assets that aren't already in it, so
restarts are fast. After adding a new plugin with the CLI, restart the
server (`docker compose restart server`) to pick it up.

If your IDEs reach the server at a non-default URL (reverse-proxied, custom
DNS, etc.) set `PUBLIC_BASE_URL=http://plugins.intranet.example` so the
`<plugin url=…>` entries are absolute. Otherwise relative URLs work fine.

## Configuring IntelliJ

In each developer's IDE:

1. **Settings → Plugins → ⚙ (gear) → Manage Plugin Repositories…**
2. Add `http://<your-host>:8080/updatePlugins.xml`.
3. **Marketplace** tab now shows your mirrored plugins; install/update as
   usual. Downloads go directly to GitHub Releases — the IDE only talks to
   this server for the XML index.

## Running the CLI without Docker (optional)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m cli
```

## Notes & limits

- One **release per plugin+version** (tag: `plugin/<xmlId>@<version>`). Old
  versions stay accessible at their stable URLs.
- The manifest only emits the **latest mirrored version per plugin** in
  `updatePlugins.xml`; older releases remain in `plugins.json` and on GitHub
  for rollback, but IntelliJ only sees the newest.
- GitHub Releases caps a single asset at **2 GB**; larger plugins won't fit.
- Public repo + Releases = **unlimited download bandwidth**. Keep the repo
  private at your peril (IDEs would then need auth).
