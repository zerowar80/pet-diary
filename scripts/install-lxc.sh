#!/usr/bin/env bash
#
# LXC(또는 일반 Debian/Ubuntu 서버) 안에서 실행하는 설치 스크립트입니다.
# Docker 없이 systemd 서비스로 직접 실행되도록 구성합니다.
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
apt-get install -y python3 python3-venv python3-pip

echo "== 2. 전용 실행 계정 생성 (이미 있으면 건너뜀) =="
if ! id "$SERVICE_USER" &>/dev/null; then
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

echo "== 3. .env 파일 확인 =="
if [ ! -f "$APP_DIR/.env" ]; then
  if [ -f "$APP_DIR/.env.example" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  fi
  echo ""
  echo "!! $APP_DIR/.env 파일에 ANTHROPIC_API_KEY 를 입력한 뒤 이 스크립트를 다시 실행하세요."
  echo "   예) nano $APP_DIR/.env"
  exit 1
fi

if grep -q "sk-ant-여기에" "$APP_DIR/.env" 2>/dev/null; then
  echo "!! .env 파일의 ANTHROPIC_API_KEY 값이 아직 예시 그대로입니다. 실제 키로 바꿔주세요."
  exit 1
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
ExecStart=${APP_DIR}/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo ""
echo "== 설치 완료 =="
echo "상태 확인:   systemctl status ${SERVICE_NAME}"
echo "로그 확인:   journalctl -u ${SERVICE_NAME} -f"
echo "접속 주소:   http://<이 LXC의 IP>:8000"
