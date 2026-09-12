#!/usr/bin/env bash
# Derlem test koşucusu (POSIX): scripts/test.ps1 ile aynı davranış.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

if [ -z "${DERLEM_TEST_DATABASE_URL:-}" ] && [ -f .env ]; then
  DERLEM_TEST_DATABASE_URL="$(grep -E '^\s*DERLEM_TEST_DATABASE_URL\s*=' .env | tail -1 | cut -d= -f2- | xargs || true)"
  if [ -z "$DERLEM_TEST_DATABASE_URL" ]; then
    # Çalışma veritabanının adını derlem_ci_test ile değiştir.
    DERLEM_TEST_DATABASE_URL="$(grep -E '^\s*DATABASE_URL\s*=' .env | tail -1 | cut -d= -f2- | xargs | sed -E 's#/derlem(\?|$)#/derlem_ci_test\1#' || true)"
  fi
  export DERLEM_TEST_DATABASE_URL
fi
if [ -z "${DERLEM_TEST_DATABASE_URL:-}" ]; then
  echo "DERLEM_TEST_DATABASE_URL yok ve .env'den türetilemedi. docs/local_development.md > Testler" >&2
  exit 1
fi

db_name="$(printf '%s' "$DERLEM_TEST_DATABASE_URL" | sed -E 's#.*/([^/?]+).*#\1#')"
case "$db_name" in
  *_test) ;;
  *) echo "Test veritabanı adı _test ile bitmeli, '$db_name' çalışma veritabanı olabilir." >&2; exit 1 ;;
esac
echo "Test veritabanı: $db_name"

echo "== Go =="
go test ./...

echo "== Worker =="
if [ -x .venv/bin/python ]; then py=.venv/bin/python; else py=.venv/Scripts/python.exe; fi
"$py" -m pytest worker/tests -q -rs

echo "Tüm testler yeşil (veritabanı testleri dahil)."
