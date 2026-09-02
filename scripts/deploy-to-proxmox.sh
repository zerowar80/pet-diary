#!/usr/bin/env bash
#
# Proxmox VE 호스트 쉘에서 실행하는 "원클릭 배포" 스크립트입니다.
# 1) LXC 컨테이너를 새로 만들고
# 2) 컨테이너 안에 git/필수 패키지를 설치하고
# 3) 비공개 GitHub 저장소를 clone하고
# 4) .env.example을 .env로 복사해둡니다.
#
# API 키 입력과 최종 설치(scripts/install-lxc.sh 실행)만 컨테이너 안에서 직접 하면 됩니다.
#
# 사용법 (Proxmox 호스트 쉘에서):
#   bash deploy-to-proxmox.sh <VMID> <고정IP/CIDR> <게이트웨이IP> <GitHub저장소HTTPS주소> [GitHub PAT]
#
#   예) bash deploy-to-proxmox.sh 210 192.168.0.210/24 192.168.0.1 \
#         https://github.com/내계정/pet-diary.git ghp_xxx여기에토큰
#
#   GitHub PAT를 생략하면 clone 단계에서 컨테이너 안에 직접 들어가 인증하라는 안내만 나옵니다.
#
set -euo pipefail

VMID="${1:?VMID를 입력하세요. 예: 210}"
IP_CIDR="${2:?컨테이너 고정 IP를 CIDR 형식으로 입력하세요. 예: 192.168.0.210/24}"
GATEWAY="${3:?게이트웨이 IP를 입력하세요. 예: 192.168.0.1}"
REPO_URL="${4:?GitHub 저장소 HTTPS 주소를 입력하세요. 예: https://github.com/내계정/pet-diary.git}"
GITHUB_TOKEN="${5:-}"

TEMPLATE_STORE="local"
TEMPLATE="debian-12-standard_12.7-1_amd64.tar.zst"
ROOTFS_STORE="local-lvm"
HOSTNAME="pet-diary"
APP_DIR="/root/pet-diary"

echo "== 1. Debian 템플릿 확인/다운로드 =="
pveam update
if ! pveam list "$TEMPLATE_STORE" | grep -q "$TEMPLATE"; then
  pveam download "$TEMPLATE_STORE" "$TEMPLATE"
fi

echo "== 2. LXC 컨테이너 생성 (VMID: $VMID) =="
if pct status "$VMID" &>/dev/null; then
  echo "VMID $VMID 는 이미 존재합니다. 생성을 건너뛰고 기존 컨테이너를 사용합니다."
else
  pct create "$VMID" "${TEMPLATE_STORE}:vztmpl/${TEMPLATE}" \
    --hostname "$HOSTNAME" \
    --cores 2 \
    --memory 1024 \
    --swap 512 \
    --rootfs "${ROOTFS_STORE}:8" \
    --net0 "name=eth0,bridge=vmbr0,ip=${IP_CIDR},gw=${GATEWAY}" \
    --features "nesting=1" \
    --unprivileged 1 \
    --onboot 1
fi

echo "== 3. 컨테이너 시작 및 네트워크 대기 =="
pct start "$VMID"
for i in $(seq 1 15); do
  if pct exec "$VMID" -- getent hosts deb.debian.org &>/dev/null; then
    break
  fi
  sleep 2
done

echo "== 4. 컨테이너 안에 git 설치 =="
pct exec "$VMID" -- bash -c "apt-get update -y && apt-get install -y git"

echo "== 5. 저장소 clone =="
if [ -n "$GITHUB_TOKEN" ]; then
  AUTH_URL=$(echo "$REPO_URL" | sed -E "s#https://#https://${GITHUB_TOKEN}@#")
  pct exec "$VMID" -- bash -c "rm -rf '${APP_DIR}' && git clone '${AUTH_URL}' '${APP_DIR}'"
else
  echo "GitHub PAT가 제공되지 않았습니다. 컨테이너 안에서 직접 clone해야 합니다:"
  echo "  pct enter ${VMID}"
  echo "  git clone ${REPO_URL} ${APP_DIR}"
  echo "  (Username: GitHub 계정 / Password: Personal Access Token)"
fi

echo "== 6. .env 파일 준비 =="
pct exec "$VMID" -- bash -c "
  if [ -d '${APP_DIR}' ] && [ ! -f '${APP_DIR}/.env' ] && [ -f '${APP_DIR}/.env.example' ]; then
    cp '${APP_DIR}/.env.example' '${APP_DIR}/.env'
  fi
"

echo ""
echo "== 여기까지 자동 처리 완료 (VMID: $VMID) =="
echo "남은 수동 단계:"
echo "  1) pct enter ${VMID}"
if [ -z "$GITHUB_TOKEN" ]; then
  echo "  2) git clone ${REPO_URL} ${APP_DIR}   (PAT 없이 실행한 경우)"
fi
echo "  3) nano ${APP_DIR}/.env    (사용할 AI API 키와 SESSION_SECRET을 실제 값으로 입력)"
echo "  4) bash ${APP_DIR}/scripts/install-lxc.sh"
echo ""
echo "설치가 끝나면 브라우저에서 http://${IP_CIDR%/*}:8000 으로 접속하세요."
