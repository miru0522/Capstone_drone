"""1단계 연구용: 운영 worker를 재사용하고 내부 encode 시간만 응답에 추가한다."""

import json
import sys
import time
from types import SimpleNamespace

import h264_encoder_worker as base


def serve() -> int:
    for line in sys.stdin:
        response_path = None
        try:
            line_received_at = time.monotonic()
            request = json.loads(line)
            parsed_at = time.monotonic()
            response_path = request.pop("response_path")
            started = time.monotonic()
            base.encode(SimpleNamespace(**request))
            encode_ended_at = time.monotonic()
            response_write_started_at = time.monotonic()
            base._write_response(
                response_path,
                {
                    "ok": True,
                    "worker_line_received_at": line_received_at,
                    "worker_parsed_at": parsed_at,
                    "worker_encode_started_at": started,
                    "worker_encode_ended_at": encode_ended_at,
                    "worker_encode_sec": encode_ended_at - started,
                    "response_write_started_at": response_write_started_at,
                },
            )
        except Exception as exc:
            if response_path:
                base._write_response(
                    response_path,
                    {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                )
            print(f"H264_RESEARCH_WORKER_ERROR: {exc}", file=sys.stderr, flush=True)
            return 1
    return 0


if __name__ == "__main__":
    try:
        base._install_parent_death_signal()
        raise SystemExit(serve())
    except Exception as exc:
        print(f"H264_RESEARCH_WORKER_ERROR: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
