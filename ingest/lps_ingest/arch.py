"""Arch Linux package ingest.

Downloads the pacman package database tarballs from an Arch mirror.
Each repo (core, extra, multilib) is a .db.tar.gz containing one directory
per package with a ``desc`` file inside.

Relevant fields in ``desc``:
    %NAME%
    %VERSION%
    %DESC%
    %URL%
    %CSIZE%   — compressed size in bytes
    %FILENAME%
"""

from __future__ import annotations

import io
import logging
import re
import tarfile
from collections.abc import Iterator

import httpx

from .config import HTTP_TIMEOUT, USER_AGENT
from .models import PackageRecord

log = logging.getLogger(__name__)

_MIRROR = "https://geo.mirror.pkgbuild.com/{repo}/os/x86_64/{repo}.db.tar.gz"
_REPOS = ["core", "extra", "multilib"]

# Arch Linux is a rolling release; use a fixed release label.
_RELEASE = "rolling"


def _fetch_db(repo: str) -> bytes:
    url = _MIRROR.format(repo=repo)
    log.info("Fetching %s", url)
    resp = httpx.get(
        url,
        follow_redirects=True,
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    return resp.content


def _parse_desc(text: str) -> dict[str, str]:
    """Parse a pacman ``desc`` file into a key→value dict.

    Format is:
        %KEY%
        value line(s)
        (blank line)
    We only care about single-value fields.
    """
    result: dict[str, str] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if re.fullmatch(r"%[A-Z0-9_]+%", line):
            key = line[1:-1]  # strip leading/trailing %
            i += 1
            values: list[str] = []
            while i < len(lines) and lines[i].strip():
                values.append(lines[i].strip())
                i += 1
            if values:
                result[key] = values[0]  # take first line only
        else:
            i += 1
    return result


def _parse_tarball(data: bytes, repo: str) -> Iterator[PackageRecord]:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for member in tf.getmembers():
            if not member.name.endswith("/desc"):
                continue
            f = tf.extractfile(member)
            if f is None:
                continue
            desc = _parse_desc(f.read().decode("utf-8", errors="replace"))

            name = desc.get("NAME")
            version = desc.get("VERSION")
            if not name or not version:
                continue

            size_raw = desc.get("CSIZE")
            try:
                size_bytes = int(size_raw) if size_raw else None
            except ValueError:
                size_bytes = None

            yield PackageRecord(
                distro="arch",
                release=_RELEASE,
                repo=repo,
                arch="x86_64",
                package_name=name,
                version=version,
                description=desc.get("DESC"),
                homepage_url=desc.get("URL") or None,
                maintainer=None,
                download_url=None,
                size_bytes=size_bytes,
            )


def ingest(release: str) -> Iterator[PackageRecord]:
    """Yield PackageRecords for all Arch Linux packages.

    *release* is ignored (Arch is rolling) but kept for CLI API consistency.
    """
    for repo in _REPOS:
        try:
            raw = _fetch_db(repo)
        except httpx.HTTPStatusError as exc:
            log.warning("Skipping repo %s: %s", repo, exc)
            continue
        yield from _parse_tarball(raw, repo)
