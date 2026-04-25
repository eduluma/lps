# DB

Raw SQL migrations are the source of truth in [`migrations/`](./migrations/).
Alembic in `api/migrations/versions/` simply executes them, so we can switch
runners later (sqlx, dbmate, atlas) without rewriting schema.

Apply with:

```bash
make migrate    # alembic upgrade head
make seed       # populate distros table
```
