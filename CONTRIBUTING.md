# Contributing to LPS

Thanks for your interest! LPS is an open project and contributions are welcome.

## Ways to contribute

- **Report a bug** — open a GitHub issue with steps to reproduce
- **Suggest a package** — use the in-app [suggest form](https://lps.eduluma.org/suggest) or the API
- **Add a new distro** — see [docs/distro-onboarding-and-ingest-jobs.md](docs/distro-onboarding-and-ingest-jobs.md)
- **Improve the frontend / API** — PRs welcome; please open an issue first for non-trivial changes

## Development setup

```bash
git clone https://github.com/eduluma/lps.git
cd lps
task install    # uv sync + pnpm install
task dev        # docker compose up
```

See [README.md](README.md) for the full quick-start.

## Pull request guidelines

1. One logical change per PR.
2. Follow the existing code style — `task fmt` and `task lint` must pass.
3. Add or update tests if you're changing API behaviour.
4. Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
   `fix(scope):`, `feat(scope):`, `chore:`, etc.
5. Keep PRs focused — avoid unrelated refactors in the same diff.

## Code of conduct

Be respectful. We don't tolerate harassment, spam, or abusive behaviour.
Issues or PRs that violate this will be closed without discussion.

## License

By contributing you agree that your work will be licensed under the [MIT License](LICENSE).
