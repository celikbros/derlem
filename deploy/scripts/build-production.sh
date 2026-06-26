#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

mkdir -p bin

go build -trimpath -ldflags="-s -w" -o bin/derlem-api ./cmd/api
go build -trimpath -ldflags="-s -w" -o bin/derlem-migrate ./cmd/migrate

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ./worker

cd web
npm ci
npm run build
