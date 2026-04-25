"""Seed canonical distro metadata and releases."""

from __future__ import annotations

import asyncio

from .db import close_pool, get_pool, init_pool

DISTROS = [
    (
        "debian",
        "debian",
        "apt",
        "sudo apt install {pkg}",
        "apt search {q}",
        "https://packages.debian.org/{release}/{pkg}",
    ),
    (
        "ubuntu",
        "debian",
        "apt",
        "sudo apt install {pkg}",
        "apt search {q}",
        "https://packages.ubuntu.com/{release}/{pkg}",
    ),
    (
        "alpine",
        "alpine",
        "apk",
        "apk add {pkg}",
        "apk search {q}",
        "https://pkgs.alpinelinux.org/package/{release}/main/x86_64/{pkg}",
    ),
    (
        "arch",
        "arch",
        "pacman",
        "sudo pacman -S {pkg}",
        "pacman -Ss {q}",
        "https://archlinux.org/packages/?name={pkg}",
    ),
    (
        "fedora",
        "rpm",
        "dnf",
        "sudo dnf install {pkg}",
        "dnf search {q}",
        "https://packages.fedoraproject.org/pkgs/{pkg}/",
    ),
    (
        "opensuse",
        "rpm",
        "zypper",
        "sudo zypper install {pkg}",
        "zypper search {q}",
        "https://software.opensuse.org/package/{pkg}",
    ),
]


# (distro_name, release_name, is_lts, is_stable)
RELEASES: dict[str, list[tuple[str, bool, bool]]] = {
    "debian": [
        ("bookworm", False, True),  # 12, current stable
        ("trixie", False, False),  # 13, testing
        ("bullseye", False, False),  # 11, oldstable
    ],
    "ubuntu": [
        ("noble", True, True),  # 24.04 LTS
        ("jammy", True, True),  # 22.04 LTS
        ("focal", True, False),  # 20.04 LTS (EOL Apr 2025)
        ("oracular", False, False),  # 24.10
    ],
    "alpine": [
        ("edge", False, False),
        ("v3.21", False, True),
        ("v3.20", False, True),
    ],
    "arch": [
        ("rolling", False, True),
    ],
    "fedora": [
        ("42", False, True),
        ("41", False, False),
    ],
    "opensuse": [
        ("tumbleweed", False, True),
        ("leap-15.6", False, True),
    ],
}

# (canonical_name, description, homepage_url, source_url)
PROJECTS: list[tuple[str, str, str, str]] = [
    (
        "curl",
        "Command-line tool for transferring data with URLs",
        "https://curl.se",
        "https://github.com/curl/curl",
    ),
    (
        "git",
        "Distributed version control system",
        "https://git-scm.com",
        "https://github.com/git/git",
    ),
    ("vim", "Highly configurable text editor", "https://www.vim.org", "https://github.com/vim/vim"),
    (
        "neovim",
        "Hyperextensible Vim-based text editor",
        "https://neovim.io",
        "https://github.com/neovim/neovim",
    ),
    (
        "tmux",
        "Terminal multiplexer",
        "https://github.com/tmux/tmux",
        "https://github.com/tmux/tmux",
    ),
    ("htop", "Interactive process viewer", "https://htop.dev", "https://github.com/htop-dev/htop"),
    (
        "wget",
        "Network downloader",
        "https://www.gnu.org/software/wget/",
        "https://gitlab.com/gnuwget/wget2",
    ),
    (
        "ripgrep",
        "Recursively search directories for a regex pattern",
        "https://github.com/BurntSushi/ripgrep",
        "https://github.com/BurntSushi/ripgrep",
    ),
    (
        "fd",
        "Simple, fast and user-friendly alternative to find",
        "https://github.com/sharkdp/fd",
        "https://github.com/sharkdp/fd",
    ),
    (
        "bat",
        "A cat clone with syntax highlighting and Git integration",
        "https://github.com/sharkdp/bat",
        "https://github.com/sharkdp/bat",
    ),
    (
        "fzf",
        "Command-line fuzzy finder",
        "https://github.com/junegunn/fzf",
        "https://github.com/junegunn/fzf",
    ),
    (
        "lazygit",
        "Simple terminal UI for git commands",
        "https://github.com/jesseduffield/lazygit",
        "https://github.com/jesseduffield/lazygit",
    ),
    (
        "zsh",
        "Z shell — extended Bourne shell with improvements",
        "https://www.zsh.org",
        "https://github.com/zsh-users/zsh",
    ),
    (
        "fish",
        "Friendly interactive shell",
        "https://fishshell.com",
        "https://github.com/fish-shell/fish-shell",
    ),
    (
        "nginx",
        "HTTP and reverse proxy server",
        "https://nginx.org",
        "https://github.com/nginx/nginx",
    ),
    (
        "postgresql",
        "Powerful open-source relational database",
        "https://www.postgresql.org",
        "https://github.com/postgres/postgres",
    ),
    (
        "redis",
        "In-memory data structure store",
        "https://redis.io",
        "https://github.com/redis/redis",
    ),
    (
        "docker",
        "Platform for developing and running containers",
        "https://www.docker.com",
        "https://github.com/docker/docker-ce",
    ),
    (
        "python3",
        "High-level programming language",
        "https://www.python.org",
        "https://github.com/python/cpython",
    ),
    (
        "nodejs",
        "JavaScript runtime built on Chrome's V8 engine",
        "https://nodejs.org",
        "https://github.com/nodejs/node",
    ),
    (
        "jq",
        "Lightweight command-line JSON processor",
        "https://jqlang.github.io/jq/",
        "https://github.com/jqlang/jq",
    ),
    (
        "ffmpeg",
        "Complete solution for audio/video recording and conversion",
        "https://ffmpeg.org",
        "https://github.com/FFmpeg/FFmpeg",
    ),
    (
        "rsync",
        "Fast, versatile file copying tool",
        "https://rsync.samba.org",
        "https://github.com/WayneD/rsync",
    ),
    ("strace", "System call tracer", "https://strace.io", "https://github.com/strace/strace"),
]

# project canonical_name → list of alias strings
ALIASES: dict[str, list[str]] = {
    "ripgrep": ["rg", "rgrep"],
    "neovim": ["nvim"],
    "lazygit": ["lg"],
    "fd": ["fd-find"],
    "bat": ["batcat"],
    "fzf": ["fuzzy finder"],
    "postgresql": ["postgres", "psql"],
    "nodejs": ["node", "npm"],
    "ffmpeg": ["ffplay", "ffprobe"],
}


async def main() -> None:
    await init_pool()
    pool = get_pool()
    async with pool.acquire() as conn:
        for name, family, pm, install_t, search_t, url_t in DISTROS:
            await conn.execute(
                """
                INSERT INTO distros (name, family, package_manager,
                  install_command_template, search_command_template, package_url_template)
                VALUES ($1,$2,$3,$4,$5,$6)
                ON CONFLICT (name) DO UPDATE SET
                  family = EXCLUDED.family,
                  package_manager = EXCLUDED.package_manager,
                  install_command_template = EXCLUDED.install_command_template,
                  search_command_template = EXCLUDED.search_command_template,
                  package_url_template = EXCLUDED.package_url_template
                """,
                name,
                family,
                pm,
                install_t,
                search_t,
                url_t,
            )

        # Seed releases
        for distro_name, releases in RELEASES.items():
            distro_id = await conn.fetchval("SELECT id FROM distros WHERE name = $1", distro_name)
            if distro_id is None:
                continue
            for rel_name, is_lts, is_stable in releases:
                await conn.execute(
                    """
                    INSERT INTO releases (distro_id, name, is_lts, is_stable)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (distro_id, name) DO UPDATE SET
                      is_lts = EXCLUDED.is_lts,
                      is_stable = EXCLUDED.is_stable
                    """,
                    distro_id,
                    rel_name,
                    is_lts,
                    is_stable,
                )

        # Seed projects + aliases
        for canonical, description, homepage, source in PROJECTS:
            normalized = canonical.lower().replace("-", "").replace("_", "")
            project_id = await conn.fetchval(
                """
                INSERT INTO projects (canonical_name, normalized_name, description,
                  homepage_url, source_url)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (normalized_name) DO UPDATE SET
                  description = EXCLUDED.description,
                  homepage_url = EXCLUDED.homepage_url,
                  source_url   = EXCLUDED.source_url
                RETURNING id
                """,
                canonical,
                normalized,
                description,
                homepage,
                source,
            )
            for alias in ALIASES.get(canonical, []):
                normalized_alias = alias.lower()
                await conn.execute(
                    """
                    INSERT INTO aliases (project_id, alias, normalized_alias)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                    """,
                    project_id,
                    alias,
                    normalized_alias,
                )

    release_count = sum(len(v) for v in RELEASES.values())
    alias_count = sum(len(v) for v in ALIASES.values())
    await close_pool()
    print(
        f"seeded {len(DISTROS)} distros, {release_count} releases, "
        f"{len(PROJECTS)} projects, {alias_count} aliases"
    )


if __name__ == "__main__":
    asyncio.run(main())
