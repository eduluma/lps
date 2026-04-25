package main

import (
	"fmt"
	"os"
	"strings"
	"text/tabwriter"

	"github.com/spf13/cobra"

	"gitea.eduluma.org/eduluma/lps/cli/internal/api"
	"gitea.eduluma.org/eduluma/lps/cli/internal/config"
	"gitea.eduluma.org/eduluma/lps/cli/internal/distro"
)

func main() {
	if err := rootCmd().Execute(); err != nil {
		os.Exit(1)
	}
}

// ---- root ------------------------------------------------------------------

func rootCmd() *cobra.Command {
	root := &cobra.Command{
		Use:   "lps",
		Short: "Linux Package Search — find install commands for any package",
		Long: `lps searches packages across Debian, Ubuntu, Alpine, Arch, Fedora, and openSUSE.

  lps search lazygit
  lps install lazygit
  lps info lazygit
  lps config set distro debian`,
		SilenceUsage: true,
	}
	root.AddCommand(
		searchCmd(),
		installCmd(),
		infoCmd(),
		configCmd(),
	)
	return root
}

// ---- helpers ---------------------------------------------------------------

func newClient(cfg config.Config) *api.Client {
	return &api.Client{
		BaseURL: cfg.API.BaseURL,
		Token:   cfg.User.Token,
	}
}

// effectiveDistro returns the distro to use: flag > config > auto-detect.
func effectiveDistro(flagVal string, cfg config.Config) string {
	if flagVal != "" {
		return flagVal
	}
	if cfg.User.Distro != "" {
		return cfg.User.Distro
	}
	return distro.Detect().Distro
}

// ---- search ----------------------------------------------------------------

func searchCmd() *cobra.Command {
	var distroFlag string

	cmd := &cobra.Command{
		Use:   "search <query>",
		Short: "Search packages",
		Args:  cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			cfg, err := config.Load()
			if err != nil {
				return err
			}
			q := strings.Join(args, " ")
			d := effectiveDistro(distroFlag, cfg)
			client := newClient(cfg)

			resp, err := client.Search(q, d)
			if err != nil {
				return fmt.Errorf("search failed: %w", err)
			}
			if len(resp.Results) == 0 {
				fmt.Fprintf(cmd.OutOrStdout(), "No results for %q\n", q)
				return nil
			}

			w := tabwriter.NewWriter(cmd.OutOrStdout(), 0, 0, 2, ' ', 0)
			fmt.Fprintln(w, "PACKAGE\tDISTRO\tRELEASE\tVERSION\tDESCRIPTION")
			for _, r := range resp.Results {
				desc := r.Description
				if len(desc) > 60 {
					desc = desc[:57] + "..."
				}
				fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\n",
					r.PackageName, r.Distro, r.Release, r.Version, desc)
			}
			return w.Flush()
		},
	}
	cmd.Flags().StringVarP(&distroFlag, "distro", "d", "", "Filter by distro (overrides config)")
	return cmd
}

// ---- install ---------------------------------------------------------------

func installCmd() *cobra.Command {
	var distroFlag string

	cmd := &cobra.Command{
		Use:   "install <package>",
		Short: "Print the install command for a package",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			cfg, err := config.Load()
			if err != nil {
				return err
			}
			d := effectiveDistro(distroFlag, cfg)
			client := newClient(cfg)

			resp, err := client.Install(args[0], d)
			if err != nil {
				return fmt.Errorf("install lookup failed: %w", err)
			}
			// Print just the command so it's pipe-friendly.
			fmt.Fprintln(cmd.OutOrStdout(), resp.Command)
			return nil
		},
	}
	cmd.Flags().StringVarP(&distroFlag, "distro", "d", "", "Target distro (overrides config + auto-detect)")
	return cmd
}

// ---- info ------------------------------------------------------------------

func infoCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "info <package>",
		Short: "Show full package detail across all distros",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			cfg, err := config.Load()
			if err != nil {
				return err
			}
			client := newClient(cfg)

			proj, err := client.Project(args[0])
			if err != nil {
				return fmt.Errorf("package not found: %w", err)
			}

			out := cmd.OutOrStdout()
			fmt.Fprintf(out, "Name:        %s\n", proj.Name)
			if proj.Description != "" {
				fmt.Fprintf(out, "Description: %s\n", proj.Description)
			}
			if proj.HomepageURL != "" {
				fmt.Fprintf(out, "Homepage:    %s\n", proj.HomepageURL)
			}

			if len(proj.Packages) == 0 {
				fmt.Fprintln(out, "\nNo packages indexed yet.")
				return nil
			}

			fmt.Fprintln(out, "\nAvailable in:")
			w := tabwriter.NewWriter(out, 0, 0, 2, ' ', 0)
			fmt.Fprintln(w, "  DISTRO\tRELEASE\tVERSION\tPACKAGE NAME")
			for _, p := range proj.Packages {
				fmt.Fprintf(w, "  %s\t%s\t%s\t%s\n", p.Distro, p.Release, p.Version, p.PackageName)
			}
			return w.Flush()
		},
	}
}

// ---- config ----------------------------------------------------------------

func configCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "config",
		Short: "Manage lps configuration",
	}

	setCmd := &cobra.Command{
		Use:   "set <key> <value>",
		Short: "Set a config value",
		Example: `  lps config set distro debian
  lps config set release bookworm
  lps config set token mytoken
  lps config set api.base_url https://lps.example.com/api/v1
  lps config set output.format json`,
		Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := config.Set(args[0], args[1]); err != nil {
				return err
			}
			path, _ := config.Path()
			fmt.Fprintf(cmd.OutOrStdout(), "Saved %s = %q  (%s)\n", args[0], args[1], path)
			return nil
		},
	}

	showCmd := &cobra.Command{
		Use:   "show",
		Short: "Print current config",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			cfg, err := config.Load()
			if err != nil {
				return err
			}
			path, _ := config.Path()
			out := cmd.OutOrStdout()
			fmt.Fprintf(out, "# %s\n\n", path)

			d := cfg.User.Distro
			if d == "" {
				if det := distro.Detect(); det.Distro != "" {
					d = det.Distro + "  (auto-detected)"
				} else {
					d = "(not set — using API default)"
				}
			}
			r := cfg.User.Release
			if r == "" {
				if det := distro.Detect(); det.Release != "" {
					r = det.Release + "  (auto-detected)"
				} else {
					r = "(not set)"
				}
			}

			fmt.Fprintf(out, "distro      = %s\n", d)
			fmt.Fprintf(out, "release     = %s\n", r)
			fmt.Fprintf(out, "token       = %s\n", maskToken(cfg.User.Token))
			fmt.Fprintf(out, "api.base_url= %s\n", cfg.API.BaseURL)
			fmt.Fprintf(out, "output      = format=%s  color=%v\n", cfg.Output.Format, cfg.Output.Color)
			return nil
		},
	}

	pathCmd := &cobra.Command{
		Use:   "path",
		Short: "Print the config file path",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			p, err := config.Path()
			if err != nil {
				return err
			}
			fmt.Fprintln(cmd.OutOrStdout(), p)
			return nil
		},
	}

	cmd.AddCommand(setCmd, showCmd, pathCmd)
	return cmd
}

func maskToken(t string) string {
	if t == "" {
		return "(not set)"
	}
	if len(t) <= 6 {
		return "***"
	}
	return t[:3] + strings.Repeat("*", len(t)-6) + t[len(t)-3:]
}
