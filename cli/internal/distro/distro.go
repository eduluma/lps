// Package distro detects the running Linux distribution from /etc/os-release.
package distro

import (
	"bufio"
	"os"
	"strings"
)

// Info holds the detected distro slug and release codename.
type Info struct {
	Distro  string // debian, ubuntu, alpine, arch, fedora, opensuse — or ""
	Release string // bookworm, jammy, edge, rolling, etc. — or ""
}

// Detect reads /etc/os-release and normalises it to LPS slugs.
// Returns an empty Info{} on non-Linux systems or if the file is absent.
func Detect() Info {
	fields := parseOSRelease("/etc/os-release")
	if len(fields) == 0 {
		return Info{}
	}

	id := strings.ToLower(fields["ID"])
	idLike := strings.ToLower(fields["ID_LIKE"])
	codename := strings.ToLower(fields["VERSION_CODENAME"])
	versionID := strings.ToLower(fields["VERSION_ID"])

	distro := normalise(id, idLike)
	release := codename
	if release == "" {
		release = versionID
	}

	return Info{Distro: distro, Release: release}
}

func normalise(id, idLike string) string {
	for _, src := range []string{id, idLike} {
		switch {
		case src == "debian" || strings.Contains(src, "debian"):
			return "debian"
		case src == "ubuntu" || strings.Contains(src, "ubuntu"):
			return "ubuntu"
		case src == "alpine":
			return "alpine"
		case src == "arch" || src == "archlinux" || strings.Contains(src, "arch"):
			return "arch"
		case src == "fedora" || strings.Contains(src, "fedora"):
			return "fedora"
		case src == "opensuse" || strings.Contains(src, "suse"):
			return "opensuse"
		}
	}
	return ""
}

func parseOSRelease(path string) map[string]string {
	f, err := os.Open(path) // #nosec G304 — fixed well-known path
	if err != nil {
		return nil
	}
	defer f.Close()

	fields := make(map[string]string)
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.Trim(strings.TrimSpace(parts[1]), `"'`)
		fields[key] = val
	}
	return fields
}
