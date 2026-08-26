"""
DAE AI Server — VideoMAE V2 + Qwen3-VL + MeloTTS 통합 파이프라인
================================================================
단일 FastAPI 서버에서 3개 모델을 순차 실행하여
영상 분류 → 상황 설명 → 경고 음성 합성 → Spring Boot 릴레이를 수행한다.

[파이프라인]
  영상 클립(mp4) 수신
    → [Step 1] VideoMAE V2: 5-class 계층 분류 (정상/폭력/응급/절도/배회·침입)
    → [Step 2] Qwen3-VL-4B: 상황 설명(admin_log) + 경고 방송문(audio_alert) 생성
    → [Step 3] MeloTTS: 경고 방송문 → WAV 음성 합성
    → [Step 4] Spring Boot 백엔드로 릴레이 전송

[실행]
  MOCK 모드: python -m uvicorn app:app --host 0.0.0.0 --port 8000
  REAL 모드: MOCK_MODE=False python -m uvicorn app:app --host 0.0.0.0 --port 8000
"""

import os
import sys
import re
import wave
import struct
import time
from datetime import datetime
import threading
import json
import tempfile
from contextlib import asynccontextmanager

# GPU 메모리 단편화 방지 (torch import 전에 설정해야 유효)
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import requests

# =========================================================
# 경로 설정
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_DIR = os.path.join(BASE_DIR, "weights")

# VideoMAE 추론 모듈(videomae_infer.py)을 import 하기 위한 경로 추가
sys.path.insert(0, os.path.join(WEIGHTS_DIR, "videomae"))

# =========================================================
# 환경 설정
# =========================================================
# 환경변수 로드
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8080")
DEVICE_KEY = os.getenv("DEVICE_KEY", "default-device-key")
print(f"[{datetime.now()}] AI Server started with BACKEND_URL={BACKEND_URL}")

# =========================================================
# 모델 가중치 경로
# =========================================================
VIDEOMAE_BINARY_CKPT = os.path.join(
    WEIGHTS_DIR, "videomae", "checkpoints", "binary_fold1_best_val_acc.pth"
)
VIDEOMAE_SUB_CKPT = os.path.join(
    WEIGHTS_DIR, "videomae", "checkpoints", "subclass_fold1_best_val_acc.pth"
)
QWEN_MODEL_PATH = os.path.join(WEIGHTS_DIR, "qwen", "Qwen3-VL-4B-Instruct")
TTS_CKPT_PATH = os.path.join(WEIGHTS_DIR, "tts", "MeloTTS-English", "checkpoint.pth")
TTS_CONFIG_PATH = os.path.join(WEIGHTS_DIR, "tts", "MeloTTS-English", "config.json")
TTS_OUTPUT_DIR = os.path.join(BASE_DIR, "tts_outputs")

# =========================================================
# 전역 모델 변수
# =========================================================
videomae_classifier = None  # VideoMAEHierClassifier 인스턴스
vlm_model = None             # Qwen3VLForConditionalGeneration
vlm_processor = None         # AutoProcessor
tts_model = None             # MeloTTS
tts_speaker_ids = None       # TTS 화자 ID 맵

# GPU 추론 직렬화 (GPU 1개 기준, 동시 요청 시 순차 처리)
INFERENCE_LOCK = threading.Lock()


# =========================================================
# VLM 프롬프트 & 파싱 유틸 (VLM_exec5.py에서 이식)
# =========================================================
VLM_NFRAMES = 16
VLM_MIN_PIXELS = 256 * 256
VLM_MAX_PIXELS = 512 * 512
VLM_MAX_NEW_TOKENS = 512

VLM_SYSTEM_PROMPT = (
    "You are a security monitoring assistant for a patrol-drone control system. "
    "An upstream classifier (VideoMAE) has already determined the anomaly category for "
    "this clip. Treat that category as CONFIRMED and correct. Your job is NOT to re-judge "
    "or question the category. Based on that category, describe the situation visible in "
    "the video for a control-room operator.\n\n"
    "Work as follows, writing each result into the matching section:\n"
    "1) ADMIN_LOG: An objective, chronological account of the situation consistent with "
    "the given category, so the operator can grasp it quickly. Include the people "
    "involved, their actions, and changes in position, and note what supports the "
    "category. If a detail is not clearly visible, do not invent it.\n"
    "2) AUDIO_ALERT: A warning message for automated drone-speaker broadcast, consistent "
    "with the category and the ADMIN_LOG. One natural English sentence. No labels, "
    "all-caps, emojis, or special characters; keep it neutral and immediate without "
    "asserting guilt or naming individuals.\n\n"
    "Output rules:\n"
    "- Write everything in English.\n"
    "- Output EXACTLY the two sections below, using the tags verbatim, and nothing else.\n"
    "- Reproduce the tags exactly; do not translate or modify them.\n"
    "- Do NOT add greetings, intros, or thinking logs outside the sections. "
    "Start immediately with the first tag.\n\n"
    "Format (follow exactly):\n"
    "---SECTION_1: ADMIN_LOG---\n"
    "(...)\n"
    "---END_SECTION_1---\n\n"
    "---SECTION_2: AUDIO_ALERT---\n"
    "(...)\n"
    "---END_SECTION_2---"
)


def _build_vlm_messages(video_path: str, predicted_category: str) -> list:
    """Qwen3-VL용 메시지 구성 (시스템 프롬프트 + 영상 + 카테고리)"""
    return [
        {"role": "system", "content": VLM_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "video",
                    "video": video_path,
                    "nframes": VLM_NFRAMES,
                    "min_pixels": VLM_MIN_PIXELS,
                    "max_pixels": VLM_MAX_PIXELS,
                },
                {
                    "type": "text",
                    "text": (
                        f"[Confirmed category from VideoMAE]: '{predicted_category}'\n"
                        f"Describe the situation in the attached video on the premise of "
                        f"this category. Write in English."
                    ),
                },
            ],
        },
    ]


def _grab_section(label: str, end_num: int, text: str) -> str:
    """VLM 출력에서 섹션 태그 기반으로 텍스트 추출"""
    m = re.search(rf"{label}[^\-]*?---(.*?)---\s*END_SECTION_{end_num}", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _parse_vlm_sections(answer: str) -> dict:
    """VLM 원문 → admin_log / audio_alert 분리"""
    admin_log = _grab_section("ADMIN_LOG", 1, answer) or "Admin log parsing failed."
    audio_alert = _grab_section("AUDIO_ALERT", 2, answer) or "Audio alert parsing failed."
    return {"admin_log": admin_log, "audio_alert": audio_alert}


def _run_vlm_inference(video_path: str, predicted_category: str) -> dict:
    """Qwen3-VL 추론: 영상 + 카테고리 → admin_log + audio_alert + 원문"""
    import torch
    from qwen_vl_utils import process_vision_info

    messages = _build_vlm_messages(video_path, predicted_category)
    text = vlm_processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = vlm_processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    ).to("cuda" if torch.cuda.is_available() else "cpu")

    with INFERENCE_LOCK:
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.no_grad():
            generated_ids = vlm_model.generate(
                **inputs, max_new_tokens=VLM_MAX_NEW_TOKENS, do_sample=False
            )
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        infer_sec = round(time.perf_counter() - t0, 3)

    trimmed = [out[len(inp) :] for inp, out in zip(inputs["input_ids"], generated_ids)]
    answer = vlm_processor.batch_decode(
        trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0].strip()

    result = _parse_vlm_sections(answer)
    result["raw"] = answer
    result["inference_seconds"] = infer_sec
    return result


def _synthesize_tts(text: str) -> str:
    """MeloTTS 합성: 텍스트 → WAV 파일 경로 반환"""
    os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
    timestamp = int(time.time())
    filename = f"alert_{timestamp}.wav"
    output_path = os.path.join(TTS_OUTPUT_DIR, filename)

    speaker_key = "EN-Default"
    if speaker_key not in tts_speaker_ids:
        speaker_key = list(tts_speaker_ids.keys())[0]

    tts_model.tts_to_file(
        text.strip(), tts_speaker_ids[speaker_key], output_path, speed=1.0
    )
    return output_path



# =========================================================
# lifespan: 서버 시작/종료 시 모델 로드/해제
# =========================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global videomae_classifier, vlm_model, vlm_processor, tts_model, tts_speaker_ids

    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    from melo.api import TTS
    # patch_app.py가 주입한 더미. 반복 실행으로 3중 중복되어 있던 것을 1개로 정리.
    class DummyLlamaConfig: pass
    import transformers
    transformers.LlamaConfig = DummyLlamaConfig
    from videomae_infer import VideoMAEHierClassifier

    print(f"[AI Server] CUDA available: {torch.cuda.is_available()}")
    print("[AI Server] 3개 모델 로딩 시작...")

    # 1) VideoMAE V2 (계층 분류)
    print("[AI Server] [1/3] VideoMAE V2 로딩...")
    videomae_classifier = VideoMAEHierClassifier(
        binary_ckpt=VIDEOMAE_BINARY_CKPT,
        sub_ckpt=VIDEOMAE_SUB_CKPT,
        device="cuda:0",
    )
    print("[AI Server] [1/3] VideoMAE V2 로드 완료.")

    # 2) Qwen3-VL-4B (상황 설명)
    print("[AI Server] [2/3] Qwen3-VL-4B 로딩...")
    vlm_processor = AutoProcessor.from_pretrained(QWEN_MODEL_PATH, trust_remote_code=True)
    vlm_model = Qwen3VLForConditionalGeneration.from_pretrained(
        QWEN_MODEL_PATH,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    vlm_model.eval()
    print("[AI Server] [2/3] Qwen3-VL-4B 로드 완료.")

    # 3) MeloTTS (음성 합성)
    print("[AI Server] [3/3] MeloTTS 로딩...")
    tts_model = TTS(
        language="EN",
        device="auto",
        ckpt_path=TTS_CKPT_PATH,
        config_path=TTS_CONFIG_PATH,
    )
    tts_speaker_ids = tts_model.hps.data.spk2id
    print(f"[AI Server] [3/3] MeloTTS 로드 완료. Speakers: {list(tts_speaker_ids.keys())}")

    os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
    print("[AI Server] 모든 모델 로딩 완료!")

    yield  # ← 서버 실행 구간

    # 종료 시 정리
    videomae_classifier = None
    vlm_model = None
    vlm_processor = None
    tts_model = None
    tts_speaker_ids = None

    import torch

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print("[AI Server] Shutdown 완료.")


# =========================================================
# FastAPI 앱 생성
# =========================================================
app = FastAPI(
    title="DAE AI Server (VideoMAE + Qwen3-VL + MeloTTS)",
    version="2.0.0",
    lifespan=lifespan,
)


# --- DTO ---
class AnalyzeRequest(BaseModel):
    image_url: str = None
    base64_image: str = None
    prompt: str = "이 영상에서 의심스러운 정황을 설명해줘."


class TtsRequest(BaseModel):
    text: str
    speaker: Optional[str] = None


# =========================================================
# API Endpoints
# =========================================================


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "models": {
            "videomae": videomae_classifier is not None,
            "vlm": vlm_model is not None,
            "tts": tts_model is not None,
        },
    }


@app.post("/analyze")
def analyze_vision(request: AnalyzeRequest):
    """단일 이미지 VLM 분석 (기존 엔드포인트 호환 유지)"""
    if not vlm_model or not vlm_processor:
        raise HTTPException(status_code=500, detail="VLM 모델이 초기화되지 않았습니다.")

    try:
        import torch
        from qwen_vl_utils import process_vision_info

        content = []
        if request.image_url:
            content.append({"type": "image", "image": request.image_url})
        elif request.base64_image:
            content.append({"type": "image", "image": request.base64_image})
        content.append({"type": "text", "text": request.prompt})
        messages = [{"role": "user", "content": content}]

        text = vlm_processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = vlm_processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to("cuda" if torch.cuda.is_available() else "cpu")

        with INFERENCE_LOCK:
            with torch.no_grad():
                generated_ids = vlm_model.generate(**inputs, max_new_tokens=512)
        generated_ids_trimmed = [
            out_ids[len(in_ids) :]
            for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = vlm_processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]

        return {"status": "success", "mock": False, "result": output_text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"VLM 처리 중 에러: {str(e)}")


@app.post("/tts")
def generate_tts(request: TtsRequest):
    """단일 TTS 합성 (기존 엔드포인트 호환 유지)"""
    if not request.text or request.text.strip() == "":
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    if not tts_model:
        raise HTTPException(status_code=500, detail="MeloTTS 모델이 초기화되지 않았습니다.")

    try:
        output_path = _synthesize_tts(request.text)
        return FileResponse(path=output_path, media_type="audio/wav", filename="alert.wav")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS 생성 중 에러: {str(e)}")


@app.post("/analyze-video")
async def analyze_video_pipeline(
    video: UploadFile = File(...),
    eventData: str = Form(None),
    drone_id: str = Form("DR-01")
):
    """
    ★ 메인 파이프라인 ★
    영상 클립 수신 → VideoMAE 분류 → Qwen3-VL 설명 → MeloTTS 합성 → Spring Boot 릴레이
    """
    # finally에서 참조하므로 try 진입 전에 정의해 둔다 (NameError 방지)
    temp_video_path = None

    try:
        # 1. 파일 임시 저장
        temp_dir = tempfile.gettempdir()
        temp_video_path = os.path.join(temp_dir, video.filename)
        with open(temp_video_path, "wb") as buffer:
            buffer.write(await video.read())
        print(f"[AI Server] 영상 수신: {video.filename}")

        # 2. 파이프라인 실행
        tts_wav_path = None

        # --- [Step 1] VideoMAE V2: 계층 분류 ---
        print("[AI Server] [Step 1/3] VideoMAE 분류 시작...")
        mae_result = videomae_classifier.predict(temp_video_path)

        if mae_result["status"] != "ok":
            raise Exception(f"VideoMAE 추론 실패: {mae_result.get('error', 'unknown')}")

        category = mae_result["result"]["category"]
        category_id = mae_result["result"]["category_id"]
        confidence = mae_result["result"]["confidence"]
        is_anomaly = mae_result["result"]["is_anomaly"]
        print(
            f"[AI Server] [Step 1/3] VideoMAE 결과: {category} "
            f"(ID: {category_id}, 신뢰도: {confidence:.4f}, 이상: {is_anomaly})"
        )

        # --- [Step 2] Qwen3-VL: 상황 설명 (이상 판정 시에만 실행) ---
        admin_log = "순찰 이상 없음."
        audio_alert = "Patrol area clear, no anomalies detected."

        if is_anomaly:
            print("[AI Server] [Step 2/3] Qwen3-VL 상황 설명 생성 시작...")
            video_abs_path = os.path.abspath(temp_video_path)
            vlm_result = _run_vlm_inference(video_abs_path, category)
            admin_log = vlm_result["admin_log"]
            audio_alert = vlm_result["audio_alert"]
            print(
                f"[AI Server] [Step 2/3] VLM 완료 "
                f"({vlm_result['inference_seconds']}s)"
            )
        else:
            print("[AI Server] [Step 2/3] 정상 판정 → VLM 생략")

        # --- [Step 3] MeloTTS: 음성 합성 (이상 판정 시에만 실행) ---
        if is_anomaly:
            print("[AI Server] [Step 3/3] MeloTTS 음성 합성 시작...")
            tts_wav_path = _synthesize_tts(audio_alert)
            print(f"[AI Server] [Step 3/3] TTS 완료: {tts_wav_path}")
        else:
            print("[AI Server] [Step 3/3] 정상 판정 → TTS 생략")

        event_data_dict = {
            "droneId": drone_id,
            "maeConfidence": confidence,
            "type": "CRITICAL" if is_anomaly else "INFO",
            "label": category,
            "categoryId": category_id,
            "description": admin_log,
            "ttsText": audio_alert,
        }

        # [수정 2026-08-05] eventData override를 MOCK/REAL 공통 경로로 이동.
        # 이전에는 REAL 분기 안에만 있어서 MOCK_MODE로 E2E 검증할 때
        # vadScore·label 주입이 조용히 무시됐다.
        # (가상 드론 설계의 1차 점수 동봉이 이 경로에 의존한다)
        if eventData:
            try:
                parsed = json.loads(eventData)
                event_data_dict.update(parsed)
            except Exception as parse_err:
                print(f"[AI Server] eventData 파싱 실패, 무시함: {parse_err}")

        event_data = event_data_dict

        # 3. Spring Boot 서버로 릴레이 전송
        backend_url = f"{BACKEND_URL}/events"
        headers = {"X-Device-Key": DEVICE_KEY}

        with open(temp_video_path, "rb") as vf:
            files = {"video": (video.filename, vf, video.content_type)}

            # TTS WAV가 생성된 경우 함께 전송
            audio_file_handle = None
            if tts_wav_path and os.path.exists(tts_wav_path):
                audio_file_handle = open(tts_wav_path, "rb")
                files["audio"] = (
                    os.path.basename(tts_wav_path),
                    audio_file_handle,
                    "audio/wav",
                )

            data = {"eventData": json.dumps(event_data)}

            print(f"[AI Server] Spring Boot 릴레이 전송 중... ({backend_url})")
            response = requests.post(backend_url, files=files, data=data, headers=headers, verify=False)

            if audio_file_handle:
                audio_file_handle.close()

        if response.status_code == 200:
            print("[AI Server] 백엔드 전송 성공")
            
            return {
                "status": "success",
                "message": "Pipeline completed",
                "event_data": event_data,
                "backend_response": response.text,
            }
        else:
            print(
                f"[AI Server] 백엔드 전송 실패: "
                f"{response.status_code} - {response.text}"
            )
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Backend Error: {response.text}",
            )

    except Exception as e:
        print(f"[AI Server] 파이프라인 에러: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # [수정 2026-08-05] 임시 mp4 정리를 finally로 이동.
        # 이전에는 해피패스에만 있어서 추론·릴레이 도중 예외가 나면
        # 업로드된 클립이 temp에 계속 쌓였다.
        try:
            if temp_video_path and os.path.exists(temp_video_path):
                os.remove(temp_video_path)
        except OSError as cleanup_err:
            print(f"[AI Server] 임시 파일 삭제 실패: {cleanup_err}")
