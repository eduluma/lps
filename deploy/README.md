# LPS Deploy

Deployment artifacts beyond local dev. Local dev lives at the repo root
([../docker-compose.yml](../docker-compose.yml)) using per-service Dockerfiles
(`api/Dockerfile`, `web/Dockerfile`, `ingest/Dockerfile`).

## Layout

```
deploy/
└── helm/lps/        # Helm chart for Docker Desktop k8s / any cluster
```

## Cloudflare Tunnel (local + prod)

The `cloudflared` service in the root `docker-compose.yml` is opt-in via the
`tunnel` profile.

1. Cloudflare Zero Trust → Networks → Tunnels → create a tunnel.
2. Add public hostnames:
   - `lps.eduluma.org`     → `http://web:4321`
   - `api.lps.eduluma.org` → `http://api:8000`
3. Save the token to `.env.compose` at the repo root:
   ```bash
   cp .env.compose.example .env.compose
   # paste CLOUDFLARE_TUNNEL_TOKEN=...
   ```
4. Start:
   ```bash
   docker compose --profile tunnel up -d
   ```

## Production: Docker Desktop Kubernetes + Helm

The same per-service Dockerfiles deploy via the Helm chart in
[helm/lps/](./helm/lps/) (coming next).
