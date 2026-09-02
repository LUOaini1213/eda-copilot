#!/usr/bin/env bash
# 在 WSL2 里用官方 docker 镜像跑一次真实的 RTL -> GDSII 流程，把产物拷出来。
#
#   bash scripts/run_orfs_flow.sh [PLATFORM] [DESIGN]
#   默认 nangate45 / gcd（最小的设计，几分钟内跑完）
#
# 为什么用 docker 而不是源码编译：官方镜像 openroad/orfs 约 1.6 GB，
# 源码编译 OpenROAD + Yosys 在 8 核上要 40-90 分钟。
set -euo pipefail

PLATFORM="${1:-nangate45}"
DESIGN="${2:-gcd}"
IMAGE="openroad/orfs:latest"
OUTDIR="${OUTDIR:-/root/orfs_out/${PLATFORM}_${DESIGN}}"

echo "==> 确认 docker daemon"
if ! docker info >/dev/null 2>&1; then
  echo "    daemon 没起，尝试启动"
  (dockerd >/var/log/dockerd.log 2>&1 &) || true
  for i in $(seq 1 30); do
    docker info >/dev/null 2>&1 && break
    sleep 2
  done
fi
docker info --format '    daemon OK: {{.ServerVersion}} ({{.OSType}})'

echo "==> 拉镜像 $IMAGE"
docker pull -q "$IMAGE"

echo "==> 跑 ${PLATFORM}/${DESIGN}"
mkdir -p "$OUTDIR"
docker run --rm \
  -v "$OUTDIR":/out \
  "$IMAGE" \
  bash -lc "
    set -e
    cd \$(find / -maxdepth 3 -name flow -type d -path '*OpenROAD-flow-scripts*' | head -1)
    echo '--- flow 目录:' \$(pwd)
    make DESIGN_CONFIG=./designs/${PLATFORM}/${DESIGN}/config.mk
    echo '--- 拷产物 ---'
    for d in logs reports results objects; do
      [ -d \$d ] && cp -r \$d /out/ || true
    done
  "

echo "==> 产物在 $OUTDIR"
find "$OUTDIR" -type f | head -40
echo "..."
echo "文件总数: $(find "$OUTDIR" -type f | wc -l)"
