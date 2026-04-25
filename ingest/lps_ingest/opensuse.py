"""openSUSE Leap package ingest.

Uses RPM repodata ``primary.xml.gz`` from the official openSUSE mirror.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import httpx

from .models import PackageRecord
from .rpm_repodata import fetch_primary_xml, parse_primary_xml, resolve_primary_url

log = logging.getLogger(__name__)

# openSUSE Leap OSS repo
_BASE_LEAP = "https://download.opensuse.org/distribution/leap/{release}/repo/oss"
# openSUSE Tumbleweed (rolling) OSS repo
_BASE_TW = "https://download.opensuse.org/tumbleweed/repo/oss"


def ingest(release: str) -> Iterator[PackageRecord]:
    """Yield PackageRecords for openSUSE *release*.

    Use ``"tumbleweed"`` for the rolling release, or a version string like
    ``"15.6"`` for Leap.
    """
    if release.lower() == "tumbleweed":
        base_url = _BASE_TW
    else:
        base_url = _BASE_LEAP.format(release=release)

    try:
        primary_url = resolve_primary_url(base_url)
    except httpx.HTTPStatusError as exc:
        log.error("Failed to fetch openSUSE %s repodata: %s", release, exc)
        return

    try:
        xml_bytes = fetch_primary_xml(primary_url)
    except httpx.HTTPStatusError as exc:
        log.error("Failed to fetch openSUSE %s primary XML: %s", release, exc)
        return

    yield from parse_primary_xml(
        xml_bytes,
        distro="opensuse",
        release=release,
        repo="oss",
        base_url=base_url,
    )
