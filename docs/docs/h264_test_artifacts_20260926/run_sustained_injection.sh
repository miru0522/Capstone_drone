#!/bin/bash
# 신뢰도 100% 트리거 영상 5개를 각 6회씩(총 30회), 재시작 없이 지속 투입
set -u
cd /home/hpc/drone_2026/code

FILES=(
  "/home/hpc/drone_2026/video/kakao_20260914.mp4"
  "/home/hpc/drone_2026/video/top5_both_models/01_Violence_Assault_Assault006_x264.mp4"
  "/home/hpc/drone_2026/video/top5_both_models/02_Violence_Fighting_Fighting003_x264.mp4"
  "/home/hpc/drone_2026/video/top5_both_models/03_Violence_Fighting_Fighting033_x264.mp4"
  "/home/hpc/drone_2026/video/top5_both_models/04_Violence_Fighting_Fighting018_x264.mp4"
)

echo "5개 파일 x 6회 = 30회 지속 투입 시작 $(date '+%H:%M:%S')"
count=0
for rep in 1 2 3 4 5 6; do
  for f in "${FILES[@]}"; do
    count=$((count+1))
    dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")
    dur_ceil=$(python3 -c "import math; print(math.ceil(float('$dur')))")
    echo "[$count/30][rep$rep] $(date '+%H:%M:%S') 주입: $(basename "$f") (duration=${dur_ceil}s)"
    python3 test_trigger_inject.py "$f" --duration "$dur_ceil" >/dev/null 2>&1
    sleep "$dur_ceil"
    sleep 3
  done
done
echo "지속 투입 전체 완료 $(date '+%H:%M:%S')"
