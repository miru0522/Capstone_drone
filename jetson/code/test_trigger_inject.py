"""
test_trigger_inject.py
데모/리허설용: 실행 중인 main.py에 "카메라 대신 지정된 영상을 일정 시간 재생"
하도록 신호를 보낸다.

main.py 자체를 재시작하지 않는다 - 실행 중인 캡처 루프(main.py의
TestVideoInjector)가 1초마다 신호파일을 확인해서 반영한다. 주입된 프레임도
RingBuffer -> VadCLIP 추론 -> 트리거(threshold/cooldown) -> hover ->
업로드까지 실제 카메라 프레임과 완전히 동일한 경로를 그대로 통과하므로,
데모에서 강제로 이상탐지 트리거~업로드~서버이벤트 흐름 전체를 시연할 때 쓴다.

사용법:
  python3 test_trigger_inject.py <영상경로> [--duration 15]

주의: main.py가 이미 실행 중이어야 한다(신호파일만 남기고 끝나는 스크립트라,
main.py가 안 떠있으면 아무 일도 일어나지 않는다).
"""

import argparse
import json
import os
import time


def main():
    parser = argparse.ArgumentParser(
        description="실행 중인 main.py에 테스트 영상 주입 신호를 보낸다 (데모/리허설 전용)"
    )
    parser.add_argument("video_path", help="주입할 영상 파일 경로")
    parser.add_argument(
        "--duration", type=float, default=15.0,
        help="영상을 카메라 대신 재생할 시간(초), 기본 15초"
    )
    parser.add_argument(
        "--state-path",
        default=os.environ.get("TEST_INJECT_STATE_PATH", "/tmp/drone_test_inject.json"),
        help="main.py와 공유하는 신호파일 경로 (main.py의 TEST_INJECT_STATE_PATH와 반드시 일치해야 함)",
    )
    args = parser.parse_args()

    video_path = os.path.abspath(args.video_path)
    if not os.path.exists(video_path):
        raise SystemExit(f"영상 파일을 찾을 수 없습니다: {video_path}")

    payload = {
        "video_path": video_path,
        "duration_sec": args.duration,
        "requested_at": time.time(),
    }
    with open(args.state_path, "w") as f:
        json.dump(payload, f)

    print("=" * 60)
    print("테스트 영상 주입 요청 기록 완료")
    print(f"  신호파일     = {args.state_path}")
    print(f"  video_path   = {video_path}")
    print(f"  duration_sec = {args.duration:.0f}")
    print("=" * 60)
    print("main.py가 실행 중이라면 다음 1초 체크 주기 안에 테스트 모드로")
    print("진입합니다. logs/main.log 에서 '[TestInject]' 로 시작하는 줄을 확인하세요.")
    print(f"{args.duration:.0f}초 후 자동으로 실제 카메라로 복귀합니다.")


if __name__ == "__main__":
    main()
