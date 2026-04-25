# LPS Ingest

Per-distro parsers + upsert into Postgres.

```bash
cd ingest
uv sync
uv run python -m lps_ingest.cli debian bookworm
uv run python -m lps_ingest.cli ubuntu jammy
```

Implemented:
- `debian` / `ubuntu` (Packages.xz)

Planned: `alpine` (APKINDEX.tar.gz), `arch` (JSON), `fedora` (repodata XML), `opensuse`.
