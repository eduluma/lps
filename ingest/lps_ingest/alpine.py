"""Alpine Linux package ingest.

Parses APKINDEX.tar.gz from Alpine mirrors.
APKINDEX is a plain-text file with key:value blocks separated by blank lines.

Relevant fields:
    P  — package name
    V  — version
    T  — description (one line)
    U  — homepage URL
    S  — package size in bytes
"""

from __future__ import annotations

import io
import logging
import tarfile
from collections.abc import Iterator

import httpx

from .config import HTTP_TIMEOUT, USER_AGENT
from .models import PackageRecord

log = logging.getLogger(__name__)

# repo → base URL template.  {version} and {repo} are filled in at runtime.
_MIRROR = "https://dl-cdn.alpinelinux.org/alpine/{version}/{repo}/x86_64/APKINDEX.tar.gz"

# Repos to ingest (main + community; edge doesn't have testing in stable runs)
_REPOS = ["main", "community"]


def _fetch_apkindex(version: str, repo: str) -> bytes:
    url = _MIRROR.format(version=version, repo=repo)
    log.info("Fetching %s", url)
    resp = httpx.get(
        url,
        follow_redirects=True,
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    return resp.content


def _parse_apkindex(raw: bytes) -> Iterator[dict[str, str]]:
    """Yield one dict per package block inside an APKINDEX text file."""
    current: dict[str, str] = {}
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.rstrip("\r")
        if not line:
            if current:
                yield current
                current = {}
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            current[key.strip()] = value.strip()
    if current:
        yield current


def _parse_tarball(data: bytes) -> Iterator[dict[str, str]]:
    """Extract APKINDEX from the .tar.gz archive and parse it."""
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        try:
            member = tf.getmember("APKINDEX")
        except KeyError:
            # Some older alpine tarballs use a slightly different path
            for name in tf.getnames():
                if name.endswith("APKINDEX"):
                    member = tf.getmember(name)
                    break
            else:
                log.warning("APKINDEX not found inside tarball")
                return
        f = tf.extractfile(member)
        if f is None:
            return
        yield from _parse_apkindex(f.read())


def ingest(release: str) -> Iterator[PackageRecord]:
    """Yield PackageRecords for all Alpine packages in *release*.

    *release* should be a version string like ``"edge"`` or ``"v3.21"``.
    If the caller omits the leading ``v`` for numeric versions, it is added.
    """
    # Normalise: edge stays as-is, numeric releases need a leading "v"
    if release != "edge" and not release.startswith("v"):
        release = f"v{release}"

    for repo in _REPOS:
        try:
            raw = _fetch_apkindex(release, repo)
        except httpx.HTTPStatusError as exc:
            log.warning("Skipping %s/%s: %s", release, repo, exc)
            continue

        for pkg in _parse_tarball(raw):
            name = pkg.get("P")
            version = pkg.get("V")
            if not name or not version:
                continue

            size_raw = pkg.get("S")
            try:
                size_bytes = int(size_raw) if size_raw else None
            except ValueError:
                size_bytes = None

            yield PackageRecord(
                distro="alpine",
                release=release,
                repo=repo,
                arch="x86_64",
                package_name=name,
                version=version,
                description=pkg.get("T"),
                homepage_url=pkg.get("U") or None,
                maintainer=None,
                download_url=None,
                size_bytes=size_bytes,
            )
