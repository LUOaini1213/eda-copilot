#!/usr/bin/env bash
# 用官方 docker 镜像跑一次真实的 RTL -> GDSII 流程，把产物拷出来。
#
#   bash scripts/run_orfs_flow.sh [PLATFORM] [DESIGN]
#   默认 nangate45 / gcd（最小的设计，几分钟内跑完）
#
#   IMAGE=openroad/orfs@sha256:<digest> bash scripts/run_orfs_flow.sh   指定镜像
#   OUTDIR=/some/dir bash scripts/run_orfs_flow.sh                      指定产物目录
#
# 为什么用 docker 而不是源码编译：官方镜像 openroad/orfs 约 1.6 GB，
# 源码编译 OpenROAD + Yosys 在 8 核上要 40-90 分钟。
#
# 版本：corpus/run_nangate45_gcd/ 里的日志记的是 OpenROAD 26Q3-1836-g39a75ec608。
# 默认的 :latest 会随上游更新，跑出来的 TNS / 实例数 / 耗时可能和 README 不同；
# 当时的镜像 digest 没有记下来，要对上 README 的数需要自己找到对应版本的镜像，
# 用 IMAGE= 传进来。脚本结束时会打印这次实际用到的镜像 digest 和 OpenROAD 版本。
#
# 需要一个已经在运行的 docker daemon（Docker Desktop，或 WSL2 / Linux 里自己起的 dockerd）；
# 脚本不会替你启动它，也不需要 root。
set -euo pipefail

PLATFORM="${1:-nangate45}"
DESIGN="${2:-gcd}"
IMAGE="${IMAGE:-openroad/orfs:latest}"
OUTDIR="${OUTDIR:-$PWD/orfs_out/${PLATFORM}_${DESIGN}}"

echo "==> 确认 docker daemon"
if ! docker info >/dev/null 2>&1; then
  echo "    docker daemon 没有在运行。先启动 Docker Desktop 或 dockerd，再重跑本脚本。" >&2
  exit 1
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
echo "==> 这次用的镜像与工具版本（和 README 的 OpenROAD 26Q3-1836-g39a75ec608 对一下）"
docker image inspect --format '    image: {{index .RepoDigests 0}}' "$IMAGE" || true
grep -rhom1 "OpenROAD [0-9][^ ]*" "$OUTDIR/logs" 2>/dev/null | sort -u | sed 's/^/    /' || true
