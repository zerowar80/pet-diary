#!/usr/bin/env bash
#
# Proxmox VE 호스트(쉘)에서 실행하는 스크립트입니다.
# pet-diary 전용 LXC 컨테이너를 새로 만듭니다.
#
# 사용법 (Proxmox 호스트 쉘에서, 기본은 DHCP로 IP 자동 할당):
#   bash create-lxc-container.sh <VMID>
#   예) bash create-lxc-container.sh 210
#
#   고정 IP를 쓰고 싶다면 환경변수로 넘기세요 (선택 사항):
#   STATIC_IP=192.168.0.210/24 GATEWAY=192.168.0.1 bash create-lxc-container.sh 210
#
set -euo pipefail

VMID="${1:?VMID를 입력하세요. 예: 210}"
STATIC_IP="${STATIC_IP:-}"
GATEWAY="${GATEWAY:-}"

if [ -n "$STATIC_IP" ] && [ -n "$GATEWAY" ]; then
  NET_CONFIG="name=eth0,bridge=vmbr0,ip=${STATIC_IP},gw=${GATEWAY}"
else
  NET_CONFIG="name=eth0,bridge=vmbr0,ip=dhcp"
fi

TEMPLATE_STORE="local"
TEMPLATE="debian-12-standard_12.7-1_amd64.tar.zst"
ROOTFS_STORE="local-lvm"
HOSTNAME="pet-diary"

echo "== 1. Debian 템플릿 다운로드 (이미 있으면 건너뜀) =="
pveam update
if ! pveam list "$TEMPLATE_STORE" | grep -q "$TEMPLATE"; then
  pveam download "$TEMPLATE_STORE" "$TEMPLATE"
fi

echo "== 2. LXC 컨테이너 생성 (VMID: $VMID) =="
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

echo "== 3. 컨테이너 시작 =="
pct start "$VMID"
sleep 5
CONTAINER_IP=$(pct exec "$VMID" -- hostname -I 2>/dev/null | awk '{print $1}')
echo "컨테이너에 할당된 IP: ${CONTAINER_IP:-확인 필요, Proxmox 웹 UI에서 확인하세요}"

echo "== 4. git 설치 =="
pct exec "$VMID" -- bash -c "apt-get update -y && apt-get install -y git"

echo ""
echo "== 컨테이너 생성 완료 (VMID: $VMID) =="
echo "다음 단계:"
echo "  1) pct enter ${VMID}"
echo "  2) git clone <회원님의 비공개 저장소 주소> pet-diary && cd pet-diary"
echo "  3) cp .env.example .env && nano .env   (API 키 입력)"
echo "  4) bash scripts/install-lxc.sh"
