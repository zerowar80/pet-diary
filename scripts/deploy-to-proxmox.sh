#!/usr/bin/env bash
#
# Proxmox VE 호스트 쉘에서 실행하는 "원클릭 배포" 스크립트입니다.
# 1) 비어있는 VMID를 자동으로 찾고
# 2) 컨테이너를 만들 저장소(storage)도 자동으로 고르고 (IP도 DHCP로 자동 할당)
# 3) 컨테이너 안에 git/필수 패키지를 설치하고
# 4) 비공개 GitHub 저장소를 clone하고
# 5) .env.example을 .env로 복사한 뒤
# 6) 이어서 컨테이너 안으로 자동으로 들어가 scripts/install-lxc.sh까지 실행합니다.
#    (그 안에서 AI API 키 / 접속 포트를 화면에서 바로 입력받습니다)
#
# 회원님이 넣어야 하는 건 GitHub 저장소 주소(와 선택적으로 PAT)뿐입니다.
#
# 사용법 (Proxmox 호스트 쉘에서, 원격 스크립트를 바로 실행할 때):
#   bash <(curl -fsSL https://raw.githubusercontent.com/내계정/pet-diary/main/scripts/deploy-to-proxmox.sh) \
#     https://github.com/내계정/pet-diary.git [GitHub PAT]
#
#   ※ "curl ... | bash -s --" 형태(파이프)로 실행하면 뒤이어 나오는 AI 키 입력 등
#      키보드 입력을 받을 수 없습니다. 반드시 위처럼 "bash <(curl ...)" 형태로 실행하세요.
#
#   이미 파일을 다운로드해서 로컬에 갖고 있다면 그냥:
#   bash deploy-to-proxmox.sh <GitHub저장소HTTPS주소> [GitHub PAT]
#
#   GitHub PAT는 저장소가 비공개일 때만 필요합니다. 저장소를 공개(Public)로 바꾸면 PAT 없이
#   두 번째 인자를 생략해도 clone까지 자동으로 됩니다.
#
#   자동으로 고른 값이 마음에 안 들면 환경변수로 직접 지정할 수 있습니다 (전부 선택 사항):
#   STORAGE=local-lvm TEMPLATE_STORAGE=local STATIC_IP=192.168.0.210/24 GATEWAY=192.168.0.1 \
#     bash <(curl -fsSL ...) https://github.com/내계정/pet-diary.git ghp_토큰
#
set -euo pipefail

REPO_URL="${1:?GitHub 저장소 HTTPS 주소를 입력하세요. 예: https://github.com/내계정/pet-diary.git}"
GITHUB_TOKEN="${2:-}"

STATIC_IP="${STATIC_IP:-}"
GATEWAY="${GATEWAY:-}"
STORAGE="${STORAGE:-}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-}"

if [ -n "$STATIC_IP" ] && [ -n "$GATEWAY" ]; then
  NET_CONFIG="name=eth0,bridge=vmbr0,ip=${STATIC_IP},gw=${GATEWAY}"
  echo "고정 IP 모드: ${STATIC_IP} (게이트웨이 ${GATEWAY})"
else
  NET_CONFIG="name=eth0,bridge=vmbr0,ip=dhcp"
  echo "DHCP 모드: 공유기가 IP를 자동으로 할당합니다."
fi

echo "== 0. 빈 VMID 자동 탐색 =="
VMID=$(pvesh get /cluster/nextid 2>/dev/null | tr -d '"[:space:]')
if [ -z "$VMID" ]; then
  VMID=200
  while pct status "$VMID" &>/dev/null; do
    VMID=$((VMID + 1))
  done
fi
echo "사용할 VMID: ${VMID}"

echo "== 1. 컨테이너 저장소(storage) 자동 탐색 =="
ROOTFS_STORE="$STORAGE"
if [ -z "$ROOTFS_STORE" ]; then
  ROOTFS_STORE=$(pvesm status --content rootdir 2>/dev/null | awk 'NR>1 && $3=="active" {print $1; exit}')
fi
if [ -z "$ROOTFS_STORE" ]; then
  ROOTFS_STORE=$(pvesm status 2>/dev/null | awk 'NR>1 && $3=="active" {print $1; exit}')
fi
if [ -z "$ROOTFS_STORE" ]; then
  echo "!! 사용 가능한 저장소를 찾지 못했습니다. 아래 목록에서 하나를 골라 STORAGE=이름 형태로 다시 실행해주세요:"
  pvesm status
  exit 1
fi
echo "사용할 저장소: ${ROOTFS_STORE} (자동 선택됨, 다른 저장소를 쓰려면 STORAGE=이름 환경변수로 지정)"

echo "== 2. 템플릿 저장소 자동 탐색 및 Debian 템플릿 확인/다운로드 =="
TEMPLATE_STORE="$TEMPLATE_STORAGE"
if [ -z "$TEMPLATE_STORE" ]; then
  TEMPLATE_STORE=$(pvesm status --content vztmpl 2>/dev/null | awk 'NR>1 && $3=="active" {print $1; exit}')
fi
if [ -z "$TEMPLATE_STORE" ]; then
  TEMPLATE_STORE="local"
fi
echo "사용할 템플릿 저장소: ${TEMPLATE_STORE} (다른 저장소를 쓰려면 TEMPLATE_STORAGE=이름 환경변수로 지정)"
pveam update

# 이미 로컬에 받아둔 debian-12-standard 템플릿이 있으면 그걸 쓰고,
# 없으면 미러 목록(pveam available)에서 가장 최신 버전 이름을 찾아 다운로드합니다.
# (Proxmox가 배포하는 템플릿 버전은 주기적으로 바뀌므로 버전을 하드코딩하지 않습니다.)
TEMPLATE=$(pveam list "$TEMPLATE_STORE" 2>/dev/null | awk -F'[/ ]+' '/debian-12-standard/ {print $2; exit}')
if [ -z "$TEMPLATE" ]; then
  TEMPLATE=$(pveam available --section system 2>/dev/null | awk '/debian-12-standard/ {print $2}' | sort -V | tail -n1)
fi
if [ -z "$TEMPLATE" ]; then
  echo "!! debian-12-standard 템플릿을 찾지 못했습니다. 'pveam available'로 직접 확인해주세요."
  exit 1
fi
echo "사용할 템플릿: ${TEMPLATE}"

if ! pveam list "$TEMPLATE_STORE" | grep -q "$TEMPLATE"; then
  pveam download "$TEMPLATE_STORE" "$TEMPLATE"
fi

HOSTNAME="pet-diary"
APP_DIR="/opt/pet-diary"

echo "== 3. LXC 컨테이너 생성 (VMID: $VMID, 저장소: $ROOTFS_STORE) =="
pct create "$VMID" "${TEMPLATE_STORE}:vztmpl/${TEMPLATE}" \
  --hostname "$HOSTNAME" \
  --cores 2 \
  --memory 1024 \
  --swap 512 \
  --rootfs "${ROOTFS_STORE}:8" \
  --net0 "$NET_CONFIG" \
  --features "nesting=1" \
  --unprivileged 1 \
  --onboot 1

echo "== 4. 컨테이너 시작 및 네트워크 대기 =="
pct start "$VMID"
for i in $(seq 1 15); do
  if pct exec "$VMID" -- getent hosts deb.debian.org &>/dev/null; then
    break
  fi
  sleep 2
done

CONTAINER_IP=$(pct exec "$VMID" -- hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$CONTAINER_IP" ]; then
  echo "!! IP를 아직 확인하지 못했습니다. 잠시 후 Proxmox 웹 UI에서 컨테이너 요약 화면의 IP를 직접 확인해주세요."
else
  echo "컨테이너에 할당된 IP: ${CONTAINER_IP}"
fi

echo "== 5. 컨테이너 안에 git 설치 =="
pct exec "$VMID" -- bash -c "apt-get update -y && apt-get install -y git"

echo "== 6. 저장소 clone =="
CLONE_URL="$REPO_URL"
if [ -n "$GITHUB_TOKEN" ]; then
  CLONE_URL=$(echo "$REPO_URL" | sed -E "s#https://#https://${GITHUB_TOKEN}@#")
fi
if pct exec "$VMID" -- bash -c "rm -rf '${APP_DIR}' && git clone '${CLONE_URL}' '${APP_DIR}'"; then
  echo "clone 완료"
else
  echo "!! clone에 실패했습니다. 저장소가 비공개라면 GitHub PAT를 두 번째 인자로 넣어서 다시 실행하거나,"
  echo "   컨테이너 안에서 직접 clone하세요: pct enter ${VMID} && git clone ${REPO_URL} ${APP_DIR}"
fi

echo "== 7. .env 파일 준비 =="
pct exec "$VMID" -- bash -c "
  if [ -d '${APP_DIR}' ] && [ ! -f '${APP_DIR}/.env' ] && [ -f '${APP_DIR}/.env.example' ]; then
    cp '${APP_DIR}/.env.example' '${APP_DIR}/.env'
  fi
"

echo ""
echo "== 여기까지 자동 처리 완료 (VMID: $VMID, 저장소: $ROOTFS_STORE) =="

if pct exec "$VMID" -- test -f "${APP_DIR}/scripts/install-lxc.sh" 2>/dev/null; then
  echo ""
  echo "이어서 컨테이너 안으로 들어가 설치를 계속 진행합니다 (AI API 키 / 접속 포트를 지금 바로 입력받습니다)."
  echo ""
  if pct exec "$VMID" -- bash "${APP_DIR}/scripts/install-lxc.sh"; then
    :
  else
    echo ""
    echo "!! install-lxc.sh 실행 중 문제가 있었습니다. 아래 명령어로 컨테이너에 직접 들어가 다시 실행해주세요:"
    echo "  pct enter ${VMID}"
    echo "  bash ${APP_DIR}/scripts/install-lxc.sh"
  fi
else
  echo "저장소 clone이 완료되지 않아 자동으로 이어서 진행할 수 없습니다. 아래 단계를 직접 진행해주세요:"
  echo "  1) pct enter ${VMID}"
  echo "  2) git clone ${REPO_URL} ${APP_DIR}"
  echo "  3) bash ${APP_DIR}/scripts/install-lxc.sh"
fi

echo ""
if [ -n "$CONTAINER_IP" ]; then
  echo "설치가 끝나면 브라우저에서 http://${CONTAINER_IP}:<방금 정한 포트, 기본 8000> 으로 접속하세요."
else
  echo "설치가 끝나면 브라우저에서 http://<컨테이너IP>:<방금 정한 포트, 기본 8000> 으로 접속하세요. (IP는 Proxmox 웹 UI에서 확인)"
fi
echo ""
echo "참고: DHCP로 받은 IP는 공유기 재시작 등으로 바뀔 수 있습니다. 계속 같은 주소로 쓰고 싶다면"
echo "공유기 관리화면에서 이 컨테이너의 MAC 주소를 고정 IP로 예약(DHCP reservation)해두는 걸 추천합니다."
