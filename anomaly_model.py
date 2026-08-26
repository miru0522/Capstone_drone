"""
anomaly_model.py
YOLOv5n(TensorRT) + WideBranchNet(Jigsaw-VAD, TensorRT) 파이프라인.

흐름:
  프레임(BGR, HxW) -> YOLOv5n으로 사람 검출 -> 최대 conf bbox 크롭
  -> 64x64 리사이즈 -> 9프레임 스택 -> WideBranchNet -> spatial score
  -> 1 - score 로 뒤집어서 반환 (원본은 낮을수록 이상)

모델 담당자 제공 스펙 근거:
  - YOLO 전처리: /home/hpc/work/scripts/14_jetson_detect_tensorrt.py
    (letterbox 640x640, BGR->RGB, /255, person(class=0) conf0.25 iou0.45)
  - WideBranchNet: /home/yunseon/Jigsaw-VAD (jigsaw_smoke_test.py 근거)
    입력 (1,3,9,64,64), 출력 softmax대각 min = score(낮을수록 이상)
    -> spat_logits만 사용 (담당자 지정)
  - 엔진 로딩 패턴: measure_widebranchnet_trt.py 참고
"""

import os
import time
import logging
from typing import Optional, Tuple

import numpy as np
import cv2

# NumPy 1.24+ 호환 shim (TensorRT 8.5 trt.nptype 참조용)
if not hasattr(np, "bool"):
    np.bool = bool

import tensorrt as trt
import pycuda.driver as cuda
import pycuda.autoinit  # noqa: F401  CUDA 컨텍스트 자동 초기화

logger = logging.getLogger("anomaly_model")

# ─── 경로/설정 ──────────────────────────────────────────────────
YOLO_ENGINE_PATH = os.environ.get(
    "YOLO_ENGINE_PATH",
    "/home/hpc/drone_2026/code/yolov5n_fp16_local.engine",
)
WBN_ENGINE_PATH = os.environ.get(
    "WBN_ENGINE_PATH",
    "/home/hpc/drone_2026/code/widebranchnet_n9_fp16_local.engine",
)

YOLO_INPUT_SIZE = 640
YOLO_CONF_THRES = 0.25
YOLO_IOU_THRES = 0.45
YOLO_TARGET_CLASS = 0  # person

WBN_NUM_FRAMES = 9
WBN_CROP_SIZE = 64

TRT_LOGGER = trt.Logger(trt.Logger.WARNING)
trt.init_libnvinfer_plugins(TRT_LOGGER, "")  # 커스텀 플러그인(WideBranchNet 등) 레지스트리 등록


# ══════════════════════════════════════════════════════════════
#  YOLOv5n TensorRT 검출기
#  (14_jetson_detect_tensorrt.py 의 TRTDetector/전처리/후처리 그대로 이식)
# ══════════════════════════════════════════════════════════════

class TRTDetector:
    def __init__(self, engine_path: str):
        with open(engine_path, "rb") as f:
            runtime = trt.Runtime(TRT_LOGGER)
            self.engine = runtime.deserialize_cuda_engine(f.read())
        self.context = self.engine.create_execution_context()
        self.stream = cuda.Stream()
        self.bindings = []
        self.inputs = []
        self.outputs = []
        for i in range(self.engine.num_bindings):
            name = self.engine.get_binding_name(i)
            shape = tuple(self.engine.get_binding_shape(i))
            shape = tuple(max(d, 1) for d in shape)
            dtype = trt.nptype(self.engine.get_binding_dtype(i))
            size = int(np.prod(shape))
            host = cuda.pagelocked_empty(size, dtype)
            dev = cuda.mem_alloc(host.nbytes)
            self.bindings.append(int(dev))
            entry = {"name": name, "host": host, "device": dev, "shape": shape, "dtype": dtype}
            if self.engine.binding_is_input(i):
                self.inputs.append(entry)
                self.context.set_binding_shape(i, shape)
            else:
                self.outputs.append(entry)

    def infer(self, batch: np.ndarray):
        np.copyto(self.inputs[0]["host"], batch.ravel())
        cuda.memcpy_htod_async(self.inputs[0]["device"], self.inputs[0]["host"], self.stream)
        self.context.execute_async_v2(bindings=self.bindings, stream_handle=self.stream.handle)
        for o in self.outputs:
            cuda.memcpy_dtoh_async(o["host"], o["device"], self.stream)
        self.stream.synchronize()
        return [o["host"].reshape(o["shape"]) for o in self.outputs]


def _yolo_preprocess(img_bgr: np.ndarray, size: int = YOLO_INPUT_SIZE):
    h, w = img_bgr.shape[:2]
    r = size / max(h, w)
    nh, nw = int(round(h * r)), int(round(w * r))
    resized = cv2.resize(img_bgr, (nw, nh))
    padded = np.zeros((size, size, 3), dtype=np.uint8)
    padded[:nh, :nw] = resized
    rgb = padded[:, :, ::-1]
    x = rgb.transpose(2, 0, 1).astype(np.float32) / 255.0
    x = np.ascontiguousarray(x[None])
    return x, (r, h, w)


def _nms_numpy(boxes, scores, iou_thres):
    keep = []
    order = scores.argsort()[::-1]
    while order.size > 0:
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(boxes[i, 0], boxes[order[1:], 0])
        yy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[order[1:], 2])
        yy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        a_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        a_o = (boxes[order[1:], 2] - boxes[order[1:], 0]) * (boxes[order[1:], 3] - boxes[order[1:], 1])
        iou = inter / np.maximum(a_i + a_o - inter, 1e-8)
        order = order[1:][iou <= iou_thres]
    return np.array(keep, dtype=np.int64)


def _to_xyxy_scaled(boxes_cxcywh, scale_info):
    r, h, w = scale_info
    xy = np.zeros_like(boxes_cxcywh)
    xy[:, 0] = boxes_cxcywh[:, 0] - boxes_cxcywh[:, 2] / 2.0
    xy[:, 1] = boxes_cxcywh[:, 1] - boxes_cxcywh[:, 3] / 2.0
    xy[:, 2] = boxes_cxcywh[:, 0] + boxes_cxcywh[:, 2] / 2.0
    xy[:, 3] = boxes_cxcywh[:, 1] + boxes_cxcywh[:, 3] / 2.0
    xy /= r
    xy[:, 0::2] = xy[:, 0::2].clip(0, w)
    xy[:, 1::2] = xy[:, 1::2].clip(0, h)
    return xy


def _yolo_postprocess_v5(outputs, scale_info, conf=YOLO_CONF_THRES, iou=YOLO_IOU_THRES, target_class=YOLO_TARGET_CLASS):
    pred = outputs[0]
    if pred.ndim == 3:
        pred = pred[0]
    if pred.shape[-1] != 85 and pred.shape[0] == 85:
        pred = pred.transpose(1, 0)
    boxes_cxcywh = pred[:, :4]
    obj_conf = pred[:, 4]
    cls_scores = pred[:, 5:]
    cls_id = cls_scores.argmax(axis=1)
    cls_score = cls_scores.max(axis=1) * obj_conf
    mask = (cls_id == target_class) & (cls_score >= conf)
    if not mask.any():
        return np.zeros((0, 5), dtype=np.float32)
    bx = boxes_cxcywh[mask]
    cs = cls_score[mask]
    xy = _to_xyxy_scaled(bx, scale_info)
    keep = _nms_numpy(xy, cs, iou)
    if keep.size == 0:
        return np.zeros((0, 5), dtype=np.float32)
    return np.concatenate([xy[keep], cs[keep, None]], axis=1).astype(np.float32)


# ══════════════════════════════════════════════════════════════
#  WideBranchNet(Jigsaw-VAD) TensorRT 추론기
# ══════════════════════════════════════════════════════════════

class WideBranchNetTRT:
    def __init__(self, engine_path: str, num_frames: int = WBN_NUM_FRAMES):
        self.num_frames = num_frames
        with open(engine_path, "rb") as f:
            runtime = trt.Runtime(TRT_LOGGER)
            self.engine = runtime.deserialize_cuda_engine(f.read())
        self.context = self.engine.create_execution_context()
        self.stream = cuda.Stream()

        self.input_idx = None
        self.output_idxs = []
        for i in range(self.engine.num_bindings):
            if self.engine.binding_is_input(i):
                self.input_idx = i
            else:
                self.output_idxs.append(i)

        input_shape = (1, 3, num_frames, WBN_CROP_SIZE, WBN_CROP_SIZE)
        h_in = np.zeros(input_shape, dtype=np.float32)
        self.h_in = h_in
        self.d_in = cuda.mem_alloc(h_in.nbytes)

        self.d_outs = []
        self.out_shapes = []
        for oi in self.output_idxs:
            shape = tuple(self.context.get_binding_shape(oi))
            # ★2026-08-26: TRTDetector와 동일하게 동적 shape(-1) 방어 클램프.
            # 지금 쓰는 로컬 고정엔진은 해당 없어 보이지만, 엔진을 재생성할 때
            # 대비해 두 클래스의 shape 처리를 일관되게 맞춰둠.
            shape = tuple(max(d, 1) for d in shape)
            dtype = trt.nptype(self.engine.get_binding_dtype(oi))
            nbytes = int(np.prod(shape)) * np.dtype(dtype).itemsize
            self.d_outs.append(cuda.mem_alloc(nbytes))
            self.out_shapes.append((shape, dtype))

        self.bindings = [None] * self.engine.num_bindings
        self.bindings[self.input_idx] = int(self.d_in)
        for oi, dout in zip(self.output_idxs, self.d_outs):
            self.bindings[oi] = int(dout)

        # 워밍업
        cuda.memcpy_htod(self.d_in, h_in)
        for _ in range(3):
            self.context.execute_async_v2(bindings=self.bindings, stream_handle=self.stream.handle)
        self.stream.synchronize()
        logger.info(f"WideBranchNet TRT 엔진 로드+워밍업 완료 ({engine_path})")

    def infer_spatial_score(self, clip: np.ndarray) -> float:
        """
        clip: (3, T, 64, 64) float32, [0,1] 범위. T == self.num_frames.
        Returns: anomaly_score (0~1, 클수록 이상). 원본 score는 낮을수록
        이상이므로 1 - score 로 반환.
        """
        x = np.ascontiguousarray(clip[None].astype(np.float32))  # (1,3,T,64,64)
        cuda.memcpy_htod_async(self.d_in, x, self.stream)
        self.context.execute_async_v2(bindings=self.bindings, stream_handle=self.stream.handle)

        outs = []
        for dout, (shape, dtype) in zip(self.d_outs, self.out_shapes):
            host = np.empty(shape, dtype=dtype)
            cuda.memcpy_dtoh_async(host, dout, self.stream)
            outs.append(host)
        self.stream.synchronize()

        # 담당자 지정: spat_logits 만 사용. num_classes=[T**2, 81] 이므로
        # 보통 outs[0]=temp_logits(T,T), outs[1]=spat_logits(81,) 형태.
        # 바인딩 순서는 엔진 export 시점에 따라 다를 수 있어 both 확인.
        spat_logits = None
        for o in outs:
            if o.size == 81 or (o.ndim >= 1 and o.shape[-1] == 81):
                spat_logits = o
        if spat_logits is None:
            spat_logits = outs[-1]  # 폴백: 마지막 출력 사용

        spat_logits = spat_logits.reshape(-1, 9, 9).astype(np.float32)
        # softmax
        e = np.exp(spat_logits - spat_logits.max(axis=-1, keepdims=True))
        soft = e / e.sum(axis=-1, keepdims=True)
        diag = np.diagonal(soft, axis1=-2, axis2=-1)  # (batch, 9)
        raw_score = float(diag.min())  # 낮을수록 이상

        anomaly_score = 1.0 - raw_score
        return max(0.0, min(1.0, anomaly_score))


# ══════════════════════════════════════════════════════════════
#  통합 파이프라인
# ══════════════════════════════════════════════════════════════

class AnomalyPipeline:
    """
    main.py의 detect_anomaly(window)에서 사용할 통합 파이프라인.
    window: (T, H, W, C) uint8 BGR, T는 main.py의 INFER_WINDOW_LEN(=9, 1초).
    """

    def __init__(self):
        logger.info(f"YOLOv5n 엔진 로드 중: {YOLO_ENGINE_PATH}")
        self.detector = TRTDetector(YOLO_ENGINE_PATH)
        logger.info(f"WideBranchNet 엔진 로드 중: {WBN_ENGINE_PATH}")
        self.wbn = WideBranchNetTRT(WBN_ENGINE_PATH, num_frames=WBN_NUM_FRAMES)
        logger.info("✅ AnomalyPipeline 초기화 완료")

        # ★2026-08-26 진단용: 스트리밍 끊김/프레임드롭 원인 확인을 위한
        # 단계별 소요시간 계측. 9회(약 1초, FPS=9 기준)마다 평균/최대를 요약 로그.
        self._diag_count = 0
        self._diag_sum_bbox = 0.0
        self._diag_sum_prep = 0.0
        self._diag_sum_wbn = 0.0
        self._diag_max_total = 0.0

    def _detect_person_bbox(self, frame_bgr: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """프레임에서 최대 confidence의 person bbox 반환. 없으면 None."""
        x, scale_info = _yolo_preprocess(frame_bgr)
        outs = self.detector.infer(x)
        dets = _yolo_postprocess_v5(outs, scale_info)
        if dets.shape[0] == 0:
            return None
        best = dets[dets[:, 4].argmax()]
        x1, y1, x2, y2 = best[:4].astype(int)
        return (x1, y1, x2, y2)

    def compute_score(self, window: np.ndarray) -> float:
        """
        window: (T, H, W, C) BGR uint8, T frames (main.py에서 9프레임 전달 예정)
        Returns: anomaly_score 0.0~1.0 (높을수록 이상)
        """
        t0 = time.time()

        T = window.shape[0]
        if T != WBN_NUM_FRAMES:
            # 프레임 수가 다르면 균등 샘플링으로 맞춤 (안전장치)
            idx = np.linspace(0, T - 1, WBN_NUM_FRAMES).astype(int)
            window = window[idx]

        # 첫 프레임 기준으로 사람 bbox 검출 (매 프레임 검출은 비용이 크므로
        # 첫 프레임 bbox를 시퀀스 전체에 재사용 - 1초 윈도우라 위치변화 적음)
        bbox = self._detect_person_bbox(window[0])
        t1 = time.time()
        if bbox is None:
            # 사람이 없으면 이상 없음으로 처리
            return 0.0

        x1, y1, x2, y2 = bbox
        crops = []
        for i in range(WBN_NUM_FRAMES):
            frame = window[i]
            h, w = frame.shape[:2]
            cx1, cy1 = max(0, x1), max(0, y1)
            cx2, cy2 = min(w, x2), min(h, y2)
            if cx2 <= cx1 or cy2 <= cy1:
                crop = frame  # bbox 이상 시 전체 프레임 폴백
            else:
                crop = frame[cy1:cy2, cx1:cx2]
            crop = cv2.resize(crop, (WBN_CROP_SIZE, WBN_CROP_SIZE))
            crop_rgb = crop[:, :, ::-1]  # BGR->RGB
            crop_norm = (crop_rgb.astype(np.float32) / 255.0)
            crops.append(crop_norm)

        # (T, H, W, 3) -> (3, T, H, W)
        clip = np.stack(crops, axis=0)  # (T,64,64,3)
        clip = clip.transpose(3, 0, 1, 2)  # (3,T,64,64)
        clip = np.clip(clip, 0.0, 1.0)
        t2 = time.time()

        score = self.wbn.infer_spatial_score(clip)
        t3 = time.time()

        # ★2026-08-26 진단: 단계별 소요시간 누적, 9회(≈1초)마다 요약 로그
        self._diag_count += 1
        self._diag_sum_bbox += (t1 - t0)
        self._diag_sum_prep += (t2 - t1)
        self._diag_sum_wbn += (t3 - t2)
        self._diag_max_total = max(self._diag_max_total, t3 - t0)
        if self._diag_count >= 9:
            n = self._diag_count
            logger.info(
                f"[진단] 추론 소요시간(최근 {n}회 평균, 목표프레임간격=111ms) - "
                f"YOLO검출={self._diag_sum_bbox / n * 1000:.1f}ms, "
                f"크롭전처리={self._diag_sum_prep / n * 1000:.1f}ms, "
                f"WBN추론={self._diag_sum_wbn / n * 1000:.1f}ms, "
                f"최대total={self._diag_max_total * 1000:.1f}ms"
            )
            self._diag_count = 0
            self._diag_sum_bbox = 0.0
            self._diag_sum_prep = 0.0
            self._diag_sum_wbn = 0.0
            self._diag_max_total = 0.0

        return score
