"""부모 종료 시 H264 worker의 PR_SET_PDEATHSIG 동작을 확인하는 Jetson용 검사."""

import subprocess
import sys
import os
import time


child_code = """
import sys
import time
sys.path.insert(0, '/tmp')
import codex_h264_encoder_worker_20260926 as worker
worker._install_parent_death_signal()
open('/tmp/codex_h264_pdeath_ready', 'w').close()
time.sleep(30)
"""
for path in ("/tmp/codex_h264_pdeath_ready", "/tmp/codex_h264_pdeath_child.pid"):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
child = subprocess.Popen([sys.executable, "-c", child_code])
with open("/tmp/codex_h264_pdeath_child.pid", "w", encoding="ascii") as pid_file:
    pid_file.write(str(child.pid))
for _ in range(50):
    if os.path.exists("/tmp/codex_h264_pdeath_ready"):
        break
    time.sleep(0.02)
else:
    raise RuntimeError("자식의 PDEATHSIG 설치 완료 신호를 받지 못함")
