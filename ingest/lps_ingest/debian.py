"""Debian/Ubuntu Packages index parser.

Fetches the `Packages.xz` for a given distro/release/component/arch,
parses RFC822-style entries, and yields PackageRecord rows.
"""

from __future__ import annotations

import lzma
from collections.abc import Iterator

import httpx
from debian.deb822 import Packages as Deb822Packages

from .config import HTTP_TIMEOUT, USER_AGENT
from .models import PackageRecord

MIRRORS = {
    "debian": "https://deb.debian.org/debian",
    "ubuntu": "http://archive.ubuntu.com/ubuntu",
}


def index_url(distro: str, release: str, component: str = "main", arch: str = "amd64") -> str:
    base = MIRRORS[distro]
    return f"{base}/dists/{release}/{component}/binary-{arch}/Packages.xz"


def parse(distro: str, release: str, component: str, arch: str, raw: bytes) -> Iterator[PackageRecord]:
    text = lzma.decompress(raw).decode("utf-8", errors="replace")
    for entry in Deb822Packages.iter_paragraphs(text):
        name = entry.get("Package")
        version = entry.get("Version")
        if not name or not version:
            continue
        yield PackageRecord(
            distro=distro,
            release=release,
            repo=component,
            arch=arch,
            package_name=name,
            version=version,
            description=(entry.get("Description") or "").split("\n", 1)[0] or None,
            homepage_url=entry.get("Homepage"),
            maintainer=entry.get("Maintainer"),
            size_bytes=int(entry["Size"]) if entry.get("Size") else None,
        )


def fetch(distro: str, release: str, component: str = "main", arch: str = "amd64") -> bytes:
    url = index_url(distro, release, component, arch)
    with httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.content


def ingest(distro: str, release: str, component: str = "main", arch: str = "amd64") -> Iterator[PackageRecord]:
    return parse(distro, release, component, arch, fetch(distro, release, component, arch))
