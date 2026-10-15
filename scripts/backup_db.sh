#!/usr/bin/env sh
set -eu
mkdir -p backups
stamp="$(date +%Y%m%d-%H%M%S)"
use_postgres=0
if [ -n "${DATABASE_URL:-}" ] && printf '%s' "$DATABASE_URL" | grep -q '^postgresql'; then
  use_postgres=1
elif docker compose ps --status running --services db 2>/dev/null | grep -qx db; then
  use_postgres=1
fi
if [ "$use_postgres" -eq 1 ]; then
  docker compose exec -T db sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "backups/ace-canteen-$stamp.sql"
else
  source="backend/ace_canteen.db"
  [ -f "$source" ] || { echo "SQLite database not found: $source" >&2; exit 1; }
  cp "$source" "backups/ace-canteen-$stamp.db"
fi
echo "Backup completed: backups/ace-canteen-$stamp.*"
