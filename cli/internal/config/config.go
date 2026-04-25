// Package config handles reading and writing ~/.config/lps/config.toml.
package config

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/BurntSushi/toml"
)

// Config is the top-level structure for ~/.config/lps/config.toml.
type Config struct {
	User   UserConfig   `toml:"user"`
	API    APIConfig    `toml:"api"`
	Output OutputConfig `toml:"output"`
}

type UserConfig struct {
	Distro  string `toml:"distro"`
	Release string `toml:"release"`
	Token   string `toml:"token"`
}

type APIConfig struct {
	BaseURL string `toml:"base_url"`
}

type OutputConfig struct {
	Format string `toml:"format"` // "text" | "json"
	Color  bool   `toml:"color"`
}

// defaults returns a Config with sensible defaults.
func defaults() Config {
	return Config{
		API:    APIConfig{BaseURL: "https://lps.eduluma.org/api/v1"},
		Output: OutputConfig{Format: "text", Color: true},
	}
}

// Path returns the absolute path to the config file, respecting XDG_CONFIG_HOME.
func Path() (string, error) {
	base := os.Getenv("XDG_CONFIG_HOME")
	if base == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", fmt.Errorf("cannot find home directory: %w", err)
		}
		base = filepath.Join(home, ".config")
	}
	return filepath.Join(base, "lps", "config.toml"), nil
}

// Load reads the config file. If it does not exist, defaults are returned.
func Load() (Config, error) {
	cfg := defaults()
	path, err := Path()
	if err != nil {
		return cfg, err
	}

	data, err := os.ReadFile(path) // #nosec G304 — user-controlled config path is expected
	if os.IsNotExist(err) {
		return cfg, nil
	}
	if err != nil {
		return cfg, fmt.Errorf("reading config: %w", err)
	}

	if _, err := toml.Decode(string(data), &cfg); err != nil {
		return cfg, fmt.Errorf("parsing config: %w", err)
	}
	return cfg, nil
}

// Set updates a single key=value in the config and writes it back.
// Supported keys: distro, release, token, api.base_url, output.format, output.color
func Set(key, value string) error {
	cfg, err := Load()
	if err != nil {
		return err
	}

	switch key {
	case "distro":
		cfg.User.Distro = value
	case "release":
		cfg.User.Release = value
	case "token":
		cfg.User.Token = value
	case "api.base_url":
		cfg.API.BaseURL = value
	case "output.format":
		if value != "text" && value != "json" {
			return fmt.Errorf("output.format must be 'text' or 'json'")
		}
		cfg.Output.Format = value
	case "output.color":
		cfg.Output.Color = value == "true" || value == "1" || value == "yes"
	default:
		return fmt.Errorf("unknown config key %q\nValid keys: distro, release, token, api.base_url, output.format, output.color", key)
	}

	return write(cfg)
}

func write(cfg Config) error {
	path, err := Path()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return fmt.Errorf("creating config dir: %w", err)
	}

	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o600) // #nosec G304
	if err != nil {
		return fmt.Errorf("writing config: %w", err)
	}
	defer f.Close()

	return toml.NewEncoder(f).Encode(cfg)
}
