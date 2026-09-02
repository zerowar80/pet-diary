#!/usr/bin/env bash
#
# Proxmox VE 호스트(쉘)에서 실행하는 스크립트입니다.
# pet-diary 전용 LXC 컨테이너를 새로 만듭니다.
#
# 사용법 (Proxmox 호스트 쉘에서, 기본은 DHCP로 IP 자동 할당):
#   bash create-lxc-container.sh <VMID>
#   예) bash create-lxc-container.sh 210
#
#   고정 IP나 템플릿 저장소를 쓰고 싶다면 환경변수로 넘기세요 (선택 사항):
#   STATIC_IP=192.168.0.210/24 GATEWAY=192.168.0.1 TEMPLATE_STORAGE=local STORAGE=local-lvm bash create-lxc-container.sh 210
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

HOSTNAME="pet-diary"

TEMPLATE_STORE="${TEMPLATE_STORAGE:-}"
if [ -z "$TEMPLATE_STORE" ]; then
  TEMPLATE_STORE=$(pvesm status --content vztmpl 2>/dev/null | awk 'NR>1 && $3=="active" {print $1; exit}')
fi
[ -z "$TEMPLATE_STORE" ] && TEMPLATE_STORE="local"

ROOTFS_STORE="${STORAGE:-}"
if [ -z "$ROOTFS_STORE" ]; then
  ROOTFS_STORE=$(pvesm status --content rootdir 2>/dev/null | awk 'NR>1 && $3=="active" {print $1; exit}')
fi
if [ -z "$ROOTFS_STORE" ]; then
  ROOTFS_STORE=$(pvesm status 2>/dev/null | awk 'NR>1 && $3=="active" {print $1; exit}')
fi
if [ -z "$ROOTFS_STORE" ]; then
  echo "!! 사용 가능한 저장소를 찾지 못했습니다. STORAGE=이름 환경변수로 직접 지정해주세요."
  pvesm status
  exit 1
fi
echo "사용할 템플릿 저장소: ${TEMPLATE_STORE} / 컨테이너 저장소: ${ROOTFS_STORE}"

echo "== 1. Debian 템플릿 확인/다운로드 =="
pveam update
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
echo "  3) bash scripts/install-lxc.sh   (실행 중 AI API 키를 화면에서 바로 입력받습니다)"
