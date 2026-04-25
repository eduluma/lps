"""Fedora package ingest.

Uses RPM repodata ``primary.xml.gz`` from the official Fedora mirror.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import httpx

from .models import PackageRecord
from .rpm_repodata import fetch_primary_xml, parse_primary_xml, resolve_primary_url

log = logging.getLogger(__name__)

# Active releases mirror
_BASE = "https://dl.fedoraproject.org/pub/fedora/linux/releases/{release}/Everything/x86_64/os"
# EOL releases are moved to the archive mirror
_BASE_ARCHIVE = (
    "https://dl.fedoraproject.org/pub/archive/fedora/linux/releases/{release}/Everything/x86_64/os"
)


def ingest(release: str) -> Iterator[PackageRecord]:
    """Yield PackageRecords for Fedora *release* (e.g. ``"41"``).

    *release* must be the Fedora release number as a string.
    Falls back to the archive mirror for EOL releases.
    """
    base_url = _BASE.format(release=release)
    try:
        primary_url = resolve_primary_url(base_url)
    except httpx.HTTPStatusError:
        # Release may have moved to the archive mirror
        archive_url = _BASE_ARCHIVE.format(release=release)
        log.info("Fedora %s not on primary mirror, trying archive: %s", release, archive_url)
        try:
            primary_url = resolve_primary_url(archive_url)
            base_url = archive_url
        except httpx.HTTPStatusError as exc:
            log.error("Failed to fetch Fedora %s repodata: %s", release, exc)
            return

    try:
        xml_bytes = fetch_primary_xml(primary_url)
    except httpx.HTTPStatusError as exc:
        log.error("Failed to fetch Fedora %s primary XML: %s", release, exc)
        return

    yield from parse_primary_xml(
        xml_bytes,
        distro="fedora",
        release=release,
        repo="Everything",
        base_url=base_url,
    )
