#!/bin/bash
# 젯슨 testermain.py 대상: video 폴더 전체를 3초 간격으로 2회 반복 투입
set -u
cd /home/hpc/drone_2026/code

VIDEO_DIR=/home/hpc/drone_2026/video
mapfile -t FILES < <(find "$VIDEO_DIR" -type f -iname "*.mp4" | sort)

echo "총 ${#FILES[@]}개 파일, 2회 반복"

for pass in 1 2; do
  echo "=== PASS $pass 시작 $(date '+%H:%M:%S') ==="
  for f in "${FILES[@]}"; do
    dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")
    dur_ceil=$(python3 -c "import math; print(math.ceil(float('$dur')))")
    echo "[$pass] $(date '+%H:%M:%S') 주입: $f (길이 ${dur}s -> duration=${dur_ceil}s)"
    python3 test_trigger_inject.py "$f" --duration "$dur_ceil" >/dev/null 2>&1
    sleep "$dur_ceil"
    sleep 3
  done
  echo "=== PASS $pass 종료 $(date '+%H:%M:%S') ==="
done
echo "배치 투입 전체 완료 $(date '+%H:%M:%S')"
