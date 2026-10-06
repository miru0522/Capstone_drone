"""실카메라와 VadCLIP 첫 실제 추론만 수행하는 격리 probe.

PYTHONPATH의 첫 경로에 condition별 후보 코드를 둔다. 서버 업로드, hover,
주기 녹화, 스트리밍은 실행하지 않는다.
"""

import json
import os
import time
import traceback
from pathlib import Path


CONDITION = os.environ["H264_PROBE_CONDITION"].strip().upper()
RESULT_PATH = Path(os.environ["H264_PROBE_RESULT_PATH"])


def main() -> None:
    import main as tested_main
    import uploader

    if CONDITION not in {"W", "C"}:
        raise ValueError(f"지원하지 않는 condition: {CONDITION}")

    events = []
    result = {
        "condition": CONDITION,
        "status": "RUNNING",
        "pid": os.getpid(),
        "events": events,
    }

    def mark(name: str, **fields) -> None:
        row = {"name": name, "wall_time": time.time(), "monotonic": time.monotonic()}
        row.update(fields)
        events.append(row)
        print("H264_PROBE_EVENT " + json.dumps(row, ensure_ascii=False), flush=True)

    # 시험에서 외부 동작을 만들 수 있는 부수 worker를 모두 비활성화한다.
    tested_main.StreamUploader.start = lambda self: None
    tested_main.StreamUploader.stop = lambda self: None
    tested_main.PeriodicRingRecorder.start = lambda self: None
    tested_main.PeriodicRingRecorder.stop = lambda self: None

    hover = tested_main.DroneHoverController()
    pipeline = tested_main.CameraAnomalyPipeline(hover)
    pipeline._handle_anomaly_score = lambda score: mark(
        "score_observed_trigger_blocked", score=float(score)
    )

    original_detect = tested_main.detect_anomaly

    def detect_once(window):
        mark("first_inference_start", frame_count=len(window))
        score = original_detect(window)
        mark("first_inference_end", score=float(score))
        pipeline._running = False
        return score

    tested_main.detect_anomaly = detect_once

    try:
        mark("camera_open_start")
        pipeline.initialize_camera()
        mark("camera_first_frame_ready")

        mark("vadclip_warmup_start")
        tested_main.get_anomaly_pipeline().warmup()
        mark("vadclip_warmup_end")

        mark("h264_prepare_start", condition=CONDITION)
        if CONDITION == "W":
            ok = uploader.warmup_clip_encoder(
                tested_main.UPLOAD_CLIP_WIDTH,
                tested_main.UPLOAD_CLIP_HEIGHT,
                tested_main.FPS,
            )
        else:
            ok = uploader.prepare_clip_encoder()
        mark("h264_prepare_end", condition=CONDITION, ok=bool(ok))

        mark("capture_loop_start")
        pipeline.run()
        mark("capture_loop_end")

        if not any(row["name"] == "first_inference_end" for row in events):
            raise RuntimeError("첫 실제 VadCLIP 추론 완료 이벤트가 없음")
        result["status"] = "PASS"
    except BaseException as exc:
        result["status"] = "FAIL"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
        mark("probe_exception", error=result["error"])
        raise
    finally:
        try:
            pipeline.stop()
        except Exception as exc:
            result["pipeline_stop_error"] = f"{type(exc).__name__}: {exc}"
        try:
            pipeline.release_camera()
        except Exception as exc:
            result["camera_release_error"] = f"{type(exc).__name__}: {exc}"
        try:
            uploader._stop_persistent_worker()
        except Exception as exc:
            result["worker_stop_error"] = f"{type(exc).__name__}: {exc}"
        result["completed_at"] = time.time()
        RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULT_PATH.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
