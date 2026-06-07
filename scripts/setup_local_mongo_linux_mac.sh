#!/usr/bin/env bash
set -euo pipefail

# One-time local MongoDB setup for Linux/macOS.
# Run from the project root:
#   bash scripts/setup_local_mongo_linux_mac.sh

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONGO_PORT="${MONGO_PORT:-27017}"
DB_NAME="${DB_NAME:-ai_hrms_local}"
MONGO_URI="mongodb://127.0.0.1:${MONGO_PORT}"
DATA_DIR="${PROJECT_ROOT}/data/mongo"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/mongod.log"
ENV_FILE="${PROJECT_ROOT}/.env"
ENV_EXAMPLE="${PROJECT_ROOT}/.env.example"

mkdir -p "$DATA_DIR" "$LOG_DIR"

if ! command -v mongod >/dev/null 2>&1; then
  echo "mongod was not found. Install MongoDB Community Server, then run this script again."
  exit 1
fi

if python - <<PY >/dev/null 2>&1
from pymongo import MongoClient
MongoClient('$MONGO_URI', serverSelectionTimeoutMS=2000).admin.command('ping')
PY
then
  echo "MongoDB is already running on $MONGO_URI"
else
  echo "Starting local MongoDB on $MONGO_URI ..."
  nohup mongod --dbpath "$DATA_DIR" --bind_ip 127.0.0.1 --port "$MONGO_PORT" --logpath "$LOG_FILE" --logappend >/dev/null 2>&1 &
  sleep 4
fi

if [ ! -f "$ENV_FILE" ]; then
  if [ -f "$ENV_EXAMPLE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
  else
    touch "$ENV_FILE"
  fi
fi

python - <<PY
from pathlib import Path
p = Path('$ENV_FILE')
text = p.read_text() if p.exists() else ''
lines = text.splitlines()
def set_key(lines, key, value):
    done = False
    out = []
    for line in lines:
        if line.startswith(key + '='):
            out.append(f'{key}={value}')
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f'{key}={value}')
    return out
lines = set_key(lines, 'MONGO_URI', '$MONGO_URI')
lines = set_key(lines, 'DB_NAME', '$DB_NAME')
p.write_text('\n'.join(lines) + '\n')
PY

python "$PROJECT_ROOT/scripts/check_local_mongo.py"
echo "Setup complete. Run: python app.py"
