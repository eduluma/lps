"""Shared helpers for parsing RPM repodata ``primary.xml`` files.

Both Fedora and openSUSE publish their package metadata in this format:

    https://createrepo.baseurl.org/

The ``primary.xml.gz`` (or ``primary.xml.zst``) inside a repodata/ directory
contains ``<package type="rpm">`` elements.  We extract:

    name       → PackageRecord.package_name
    arch       → PackageRecord.arch  (skip "src")
    version    → combined epoch:ver-rel string
    summary    → PackageRecord.description
    url        → PackageRecord.homepage_url
    size       → PackageRecord.size_bytes  (package/@archive from <size>)
    location   → PackageRecord.download_url (href attr)
"""

from __future__ import annotations

import gzip
import io
import logging
import xml.etree.ElementTree as ET
from collections.abc import Iterator

import httpx

from .config import HTTP_TIMEOUT, USER_AGENT
from .models import PackageRecord

log = logging.getLogger(__name__)

# Namespaces used in primary.xml
_NS = {
    "common": "http://linux.duke.edu/metadata/common",
    "rpm": "http://linux.duke.edu/metadata/rpm",
}
_NS_REPO = {"repo": "http://linux.duke.edu/metadata/repo"}


def resolve_primary_url(base_url: str) -> str:
    """Fetch ``repomd.xml`` for *base_url* and return the full URL of the primary metadata file."""
    repomd_url = f"{base_url.rstrip('/')}/repodata/repomd.xml"
    log.info("Fetching repomd.xml from %s", repomd_url)
    resp = httpx.get(
        repomd_url,
        follow_redirects=True,
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    for data_el in root.findall("repo:data", _NS_REPO):
        if data_el.get("type") == "primary":
            loc = data_el.find("repo:location", _NS_REPO)
            if loc is not None:
                href = loc.get("href", "")
                return f"{base_url.rstrip('/')}/{href.lstrip('/')}"
    raise ValueError(f"No primary metadata found in {repomd_url}")


def fetch_primary_xml(url: str) -> bytes:
    """Download *url* and return decompressed XML bytes (handles .gz and .zst)."""
    log.info("Fetching %s", url)
    resp = httpx.get(
        url,
        follow_redirects=True,
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    data = resp.content
    if url.endswith(".gz"):
        data = gzip.decompress(data)
    elif url.endswith(".zst"):
        import io

        import zstandard

        data = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data)).read()
    return data


def parse_primary_xml(
    xml_bytes: bytes,
    *,
    distro: str,
    release: str,
    repo: str,
    base_url: str,
) -> Iterator[PackageRecord]:
    """Yield PackageRecords from RPM ``primary.xml`` content."""
    root = ET.parse(io.BytesIO(xml_bytes)).getroot()

    for pkg in root.findall("common:package", _NS):
        arch_el = pkg.find("common:arch", _NS)
        arch = arch_el.text if arch_el is not None else "noarch"
        if arch == "src":
            continue  # skip source RPMs

        name_el = pkg.find("common:name", _NS)
        if name_el is None or not name_el.text:
            continue
        name = name_el.text.strip()

        ver_el = pkg.find("common:version", _NS)
        if ver_el is None:
            continue
        epoch = ver_el.get("epoch", "0")
        ver = ver_el.get("ver", "")
        rel = ver_el.get("rel", "")
        version = f"{epoch}:{ver}-{rel}" if epoch != "0" else f"{ver}-{rel}"

        summary_el = pkg.find("common:summary", _NS)
        description = (
            summary_el.text.strip() if summary_el is not None and summary_el.text else None
        )

        url_el = pkg.find("common:url", _NS)
        homepage_url = url_el.text.strip() if url_el is not None and url_el.text else None

        size_el = pkg.find("common:size", _NS)
        size_bytes: int | None = None
        if size_el is not None:
            try:
                size_bytes = int(size_el.get("archive", 0))
            except (TypeError, ValueError):
                pass

        loc_el = pkg.find("common:location", _NS)
        download_url: str | None = None
        if loc_el is not None:
            href = loc_el.get("href")
            if href:
                download_url = f"{base_url.rstrip('/')}/{href.lstrip('/')}"

        yield PackageRecord(
            distro=distro,
            release=release,
            repo=repo,
            arch=arch or "noarch",
            package_name=name,
            version=version,
            description=description,
            homepage_url=homepage_url,
            maintainer=None,
            download_url=download_url,
            size_bytes=size_bytes,
        )
