"""
audio_receiver.py  (서버 명세 v최종 기준)
백엔드 서버가 보내는 경고방송 오디오(.wav)를 수신하여 드론 스피커로 재생.

서버 명세 (drone_integration_spec.md 4번):
  드론이 여는 엔드포인트 : POST /audio/play
  요청 주체             : 백엔드 서버가 드론 IP로 전송
  전송 방식             : multipart/form-data
  필드                 : file = .wav 오디오 파일
  동작                 : 저장 후 aplay로 즉시 스피커 재생

주의: 이 컴포넌트만 드론이 "서버 역할"을 함 (수신 대기).
      나머지(영상/텔레메트리/명령)는 드론이 클라이언트로 밖에 연결.
"""

import os
import time
import logging
import tempfile
import subprocess
import threading

from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("audio_receiver")

app = Flask(__name__)

# ─── 설정값 ──────────────────────────────────────────────────────
LISTEN_HOST = os.environ.get("AUDIO_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("AUDIO_PORT", "5001"))
SAVE_DIR = os.environ.get("AUDIO_SAVE_DIR", "/tmp/drone_audio")

os.makedirs(SAVE_DIR, exist_ok=True)


def play_wav(path: str):
    """aplay로 wav 재생 (블로킹). 별도 스레드에서 호출됨."""
    try:
        logger.info(f"🔊 재생 시작: {path}")
        subprocess.run(["aplay", path], check=True)
        logger.info(f"✅ 재생 완료: {path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"aplay 재생 실패: {e}")
    except Exception as e:
        logger.error(f"재생 오류: {e}")
    # finally:
    #     # 재생 후 임시 파일 삭제 (디버깅을 위해 주석 처리함)
    #     try:
    #         os.remove(path)
    #     except Exception:
    #         pass


@app.route("/audio/play", methods=["POST"])
def audio_play():
    """
    명세: multipart/form-data, 필드명 'file' = wav
    저장 후 즉시 재생 (재생은 백그라운드 스레드).
    """
    if "file" not in request.files:
        logger.warning("요청에 'file' 필드 없음")
        return jsonify({"status": "error", "msg": "no file field"}), 400

    f = request.files["file"]
    if f.filename == "":
        return jsonify({"status": "error", "msg": "empty filename"}), 400

    # 저장 (파일명 서버측 재생성, 경로 조작 방지)
    fname = f"tts_{int(time.time()*1000)}.wav"
    save_path = os.path.join(SAVE_DIR, fname)
    f.save(save_path)
    logger.info(f"📥 오디오 수신: {save_path} ({os.path.getsize(save_path)} bytes)")

    # 재생은 백그라운드 스레드 (HTTP 응답 즉시 반환)
    threading.Thread(target=play_wav, args=(save_path,), daemon=True).start()

    return jsonify({"status": "ok", "played": fname}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    logger.info(f"오디오 수신 서버 시작: http://{LISTEN_HOST}:{LISTEN_PORT}/audio/play")
    app.run(host=LISTEN_HOST, port=LISTEN_PORT, threaded=True)
