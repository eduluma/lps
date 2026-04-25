from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PackageRecord:
    distro: str
    release: str
    repo: str
    arch: str
    package_name: str
    version: str
    description: str | None = None
    homepage_url: str | None = None
    maintainer: str | None = None
    download_url: str | None = None
    size_bytes: int | None = None
