#!/usr/bin/env bash
#
# LXC(또는 일반 Debian/Ubuntu 서버) 안에서 실행하는 설치 스크립트입니다.
# Docker 없이 systemd 서비스로 직접 실행되도록 구성합니다.
# 실행 중 사용할 AI의 API 키를 화면에서 직접 입력받습니다 (.env를 미리 편집할 필요 없음).
#
# 사용법 (LXC 컨테이너 안에서, root 권한으로):
#   bash scripts/install-lxc.sh
#
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="pet-diary"
SERVICE_USER="petdiary"
PYTHON_BIN="python3"

echo "== 1. 시스템 패키지 설치 =="
apt-get update -y
apt-get install -y python3 python3-venv python3-pip ffmpeg

echo "== 2. 전용 실행 계정 생성 (이미 있으면 건너뜀) =="
if ! id "$SERVICE_USER" &>/dev/null; then
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

echo "== 3. 환경 설정(.env) 입력 =="
if [ ! -f "$APP_DIR/.env" ]; then
  if [ -f "$APP_DIR/.env.example" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  else
    touch "$APP_DIR/.env"
  fi
fi

is_placeholder() {
  local value="$1"
  [ -z "$value" ] && return 0
  case "$value" in
    *"여기에"*) return 0 ;;
  esac
  return 1
}

get_env_value() {
  (grep "^${1}=" "$APP_DIR/.env" 2>/dev/null || true) | head -n1 | cut -d '=' -f2-
}

set_env_value() {
  local key="$1"
  local value="$2"
  local escaped
  escaped=$(printf '%s' "$value" | sed -e 's/[\/&]/\\&/g')
  if grep -q "^${key}=" "$APP_DIR/.env" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" "$APP_DIR/.env"
  else
    echo "${key}=${value}" >> "$APP_DIR/.env"
  fi
}

prompt_if_needed() {
  local key="$1"
  local label="$2"
  local current
  current=$(get_env_value "$key")
  if is_placeholder "$current"; then
    read -r -p "${label} (사용 안 하시면 그냥 Enter): " input
    if [ -n "$input" ]; then
      set_env_value "$key" "$input"
    fi
  else
    echo "${label}: 이미 입력되어 있어 건너뜁니다."
  fi
}

echo ""
echo "사용할 AI의 API 키를 입력해주세요. 최소 하나는 입력해야 합니다."
echo "안 쓰는 AI는 그냥 Enter를 눌러 건너뛰면 됩니다."
echo ""
prompt_if_needed "ANTHROPIC_API_KEY" "Claude (Anthropic) API 키"
prompt_if_needed "GOOGLE_API_KEY"    "Gemini (Google) API 키"
prompt_if_needed "OPENAI_API_KEY"    "ChatGPT (OpenAI) API 키"

CURRENT_SECRET=$(get_env_value "SESSION_SECRET")
if is_placeholder "$CURRENT_SECRET"; then
  NEW_SECRET=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | base64 | tr -d '\n=+/')
  set_env_value "SESSION_SECRET" "$NEW_SECRET"
  echo ""
  echo "SESSION_SECRET(로그인 보안 키)은 자동으로 생성했습니다."
fi

HAS_ANY_KEY=false
for key_line in "ANTHROPIC_API_KEY" "GOOGLE_API_KEY" "OPENAI_API_KEY"; do
  value=$(get_env_value "$key_line" | tr -d '[:space:]')
  if [ -n "$value" ] && ! is_placeholder "$value"; then
    HAS_ANY_KEY=true
  fi
done

if [ "$HAS_ANY_KEY" = false ]; then
  echo ""
  echo "!! 최소 한 곳의 AI API 키가 필요합니다. 스크립트를 다시 실행해서 입력해주세요:"
  echo "   bash $0"
  exit 1
fi

echo ""
echo "== 3-1. 접속 포트 설정 =="
CURRENT_PORT=$(get_env_value "APP_PORT")
if [[ "$CURRENT_PORT" =~ ^[0-9]+$ ]]; then
  APP_PORT="$CURRENT_PORT"
  echo "접속 포트: 이미 ${APP_PORT}로 설정되어 있어 건너뜁니다."
else
  read -r -p "웹 접속 포트를 입력하세요 (기본값 8000, 그냥 Enter 시 8000 사용): " PORT_INPUT
  if [ -z "$PORT_INPUT" ]; then
    APP_PORT=8000
  elif [[ "$PORT_INPUT" =~ ^[0-9]+$ ]] && [ "$PORT_INPUT" -ge 1 ] && [ "$PORT_INPUT" -le 65535 ]; then
    APP_PORT="$PORT_INPUT"
  else
    echo "!! 올바르지 않은 포트 번호라 기본값 8000을 사용합니다."
    APP_PORT=8000
  fi
  set_env_value "APP_PORT" "$APP_PORT"
fi

echo "== 4. 파이썬 가상환경 생성 및 패키지 설치 =="
"$PYTHON_BIN" -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "== 5. 데이터 폴더 권한 설정 =="
mkdir -p "$APP_DIR/data/uploads"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR"

echo "== 6. systemd 서비스 등록 =="
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=반려견 AI 사진 일기장
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo ""
echo "== 설치 완료 (버전: $(cat "$APP_DIR/VERSION" 2>/dev/null || echo '알 수 없음')) =="
echo "상태 확인:   systemctl status ${SERVICE_NAME}"
echo "로그 확인:   journalctl -u ${SERVICE_NAME} -f"
echo "접속 주소:   http://<이 LXC의 IP>:${APP_PORT}"
