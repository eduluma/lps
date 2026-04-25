# LPS Web (Astro + Tailwind)

```bash
cd web
pnpm install
cp .env.example .env
pnpm dev    # http://localhost:4321
```

Pages:
- `/` — home + search box
- `/search?q=...` — results list
- `/p/{name}` — brew.sh-style package page (install tabs, versions)
