from __future__ import annotations

import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://lps:lps@localhost:5432/lps")
HTTP_TIMEOUT = float(os.getenv("INGEST_HTTP_TIMEOUT", "60"))
USER_AGENT = os.getenv("INGEST_USER_AGENT", "lps-ingest/0.1 (+https://lps.eduluma.org)")
