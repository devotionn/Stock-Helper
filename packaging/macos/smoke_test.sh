#!/bin/bash
# 对最终 PyInstaller 后端、内置前端、SQLite 与可选 macOS Keychain 执行写入型冒烟测试。
set -euo pipefail
APP_PATH="${1:?用法: smoke_test.sh <app_path> [version]}"
EXPECTED_VERSION="${2:-1.0.0}"
BACKEND="$APP_PATH/Contents/Resources/backend/stock-helper-server"
TEST_KEYCHAIN="${TEST_KEYCHAIN:-0}"
[[ -x "$BACKEND" ]] || { echo "后端不存在或不可执行: $BACKEND"; exit 1; }

TEST_DATA="$(mktemp -d "${RUNNER_TEMP:-/tmp}/stock-helper-smoke.XXXXXX")"
LOG_FILE="$TEST_DATA/backend.log"
PID=""
cleanup() {
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    sleep 1
    kill -9 "$PID" 2>/dev/null || true
  fi
  rm -rf "$TEST_DATA"
}
trap cleanup EXIT

STOCK_DATA_DIR="$TEST_DATA/data" STOCK_APP_VERSION="$EXPECTED_VERSION" "$BACKEND" >"$LOG_FILE" 2>&1 &
PID=$!

HEALTH=""
for _ in $(seq 1 60); do
  if ! kill -0 "$PID" 2>/dev/null; then
    cat "$LOG_FILE"
    echo "后端提前退出"
    exit 1
  fi
  HEALTH="$(curl --max-time 2 -fsS -H 'Host: 127.0.0.1:8765' http://127.0.0.1:8765/api/health 2>/dev/null || true)"
  if [[ "$HEALTH" == *'"app":"stock-helper"'* || "$HEALTH" == *'"app": "stock-helper"'* ]]; then
    break
  fi
  sleep 0.5
done

[[ "$HEALTH" == *"$EXPECTED_VERSION"* ]] || { echo "健康检查版本不匹配: $HEALTH"; exit 1; }
SESSION="$(curl --max-time 5 -fsS -H 'Host: 127.0.0.1:8765' http://127.0.0.1:8765/api/session)"
TOKEN="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])' <<<"$SESSION")"
HEADERS=(-H 'Host: 127.0.0.1:8765' -H "X-Session-Token: $TOKEN" -H 'Content-Type: application/json')

MODULE="$(curl --max-time 5 -fsS "${HEADERS[@]}" http://127.0.0.1:8765/api/modules/0)"
REVISION="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["revision"])' <<<"$MODULE")"
curl --max-time 5 -fsS -X PUT "${HEADERS[@]}" \
  -d "{\"text_content\":\"smoke-test-$EXPECTED_VERSION\",\"revision\":$REVISION}" \
  http://127.0.0.1:8765/api/modules/0 >/dev/null
VERIFY="$(curl --max-time 5 -fsS "${HEADERS[@]}" http://127.0.0.1:8765/api/modules/0)"
[[ "$VERIFY" == *"smoke-test-$EXPECTED_VERSION"* ]] || { echo "模块写入验证失败"; exit 1; }

INDEX="$(curl --max-time 5 -fsS http://127.0.0.1:8765/)"
[[ "$INDEX" == *'<!DOCTYPE html>'* || "$INDEX" == *'<html'* ]] || { echo "前端首页未正确打包"; exit 1; }

if [[ "$TEST_KEYCHAIN" == "1" ]]; then
  TEST_SECRET="sk-smoke-12345678"
  if ! curl --max-time 15 -fsS -X PUT "${HEADERS[@]}" \
    -d "{\"ai_api_key\":\"$TEST_SECRET\"}" \
    http://127.0.0.1:8765/api/settings >/dev/null; then
    cat "$LOG_FILE"
    echo "Keychain 写入 API 超时或失败"
    exit 1
  fi
  SETTINGS="$(curl --max-time 15 -fsS "${HEADERS[@]}" http://127.0.0.1:8765/api/settings)"
  python3 - "$SETTINGS" <<'PY'
import json
import sys

settings = json.loads(sys.argv[1])
assert settings["has_api_key"] is True
assert settings["masked_api_key"] == "sk****5678"
assert "ai_api_key" not in settings
PY
  DB_SECRET_COUNT="$(sqlite3 "$TEST_DATA/data/stock_helper.db" "SELECT COUNT(*) FROM settings WHERE key='ai_api_key' AND value<>'';")"
  [[ "$DB_SECRET_COUNT" == "0" ]] || { echo "API 密钥错误写入 SQLite"; exit 1; }
  echo "macOS Keychain 读写、脱敏及 SQLite 隔离测试通过"
fi

kill "$PID"
wait "$PID" || true
PID=""
for _ in $(seq 1 30); do
  if ! lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "冒烟测试通过"
    exit 0
  fi
  sleep 0.2
done

echo "后端退出后端口仍被占用"
exit 1
