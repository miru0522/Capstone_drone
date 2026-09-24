"""
videomae_infer.py — Server 2차 분류(VideoMAE V2-Base, 계층 분류) 추론 래퍼

[목적]
  FastAPI 서버가 Edge로부터 받은 이벤트 클립(5초 mp4 또는 frame 디렉터리)을 입력하면,
  계층 분류(정상↔이상 → 이상 4-class)로 최종 5-class 카테고리와 확률을 JSON으로 반환.

[FastAPI 사용 예]
  from videomae_infer import VideoMAEHierClassifier
  clf = VideoMAEHierClassifier(            # 서버 기동 시 1회 로드 (재사용)
      binary_ckpt="/path/binary/fold_1/best_val_acc.pth",
      sub_ckpt="/path/subclass/fold_1/best_val_acc.pth",
      device="cuda:0")
  result = clf.predict("/data/events/evt_001.mp4")   # 요청마다 호출
  # result = dict (아래 OUTPUT 스키마). JSON 직렬화 그대로 응답에 사용 가능.

[중요 — 역할 구분]
  - 본 모듈은 "카테고리 분류"만 수행한다. category(정상/폭력/응급/절도/배회·침입)와 confidence 반환.
  - 위험도 Anomaly Score(정상/의심/이상 분기)는 Edge(Jigsaw-VAD)에서 산출되어 이벤트와 함께 전달되는
    별개 값이다. 본 출력의 confidence와 혼동하지 말 것.

[의존성] torch, transformers(trust_remote_code), torchvision, numpy, (mp4 입력 시) decord
[모델 가중치] OpenGVLab/VideoMAEv2-Base 백본은 최초 1회 자동 다운로드. 분류 head 2개(.pth)는 별도 전달.
"""
from __future__ import annotations
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torchvision.transforms.v2.functional as TF
from transformers import AutoConfig, AutoModel

MODEL_ID = "OpenGVLab/VideoMAEv2-Base"
NUM_FRAMES = 16
IMG_SIZE = 224
FEAT_DIM = 768
# 최종 5-class 순서 (고정)
CLASS_NAMES = ["정상", "폭력", "응급", "절도", "배회·침입"]
SUBCLASS_NAMES = ["폭력", "응급", "절도", "배회·침입"]   # subclass 0~3 → 최종 1~4
IMAGENET_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
IMAGENET_STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
SCHEMA_VERSION = "1.0"


class _Head(nn.Module):
    """VideoMAE V2 backbone + Linear classifier (학습 시와 동일 구조)."""
    def __init__(self, num_classes: int):
        super().__init__()
        cfg = AutoConfig.from_pretrained(MODEL_ID, trust_remote_code=True)
        from transformers.modeling_utils import PreTrainedModel
        PreTrainedModel.all_tied_weights_keys = {}
        import torch
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.backbone = AutoModel.from_pretrained(MODEL_ID, config=cfg, trust_remote_code=True)
        
        # FIX FOR META TENSOR BUG IN VIDEOMAEV2
        import sys
        if hasattr(self.backbone, "model") and hasattr(self.backbone.model, "pos_embed"):
            if self.backbone.model.pos_embed.device.type == "meta":
                mod = sys.modules[self.backbone.__class__.__module__]
                new_pos = mod.get_sinusoid_encoding_table(self.backbone.model.patch_embed.num_patches, self.backbone.model.embed_dim)
                self.backbone.model.pos_embed = new_pos.to(device)
                
        feat = getattr(cfg, "num_features", FEAT_DIM) or FEAT_DIM
        self.dropout = nn.Identity()
        self.classifier = nn.Linear(feat, num_classes)

    def forward(self, x_bcthw):
        return self.classifier(self.dropout(self.backbone(pixel_values=x_bcthw)))


def _load_head(ckpt_path: str, device: str) -> _Head:
    ck = torch.load(ckpt_path, map_location=device)
    sd = ck.get("model", ck)
    nc = ck.get("num_classes") or int(sd["classifier.weight"].shape[0])
    m = _Head(nc).to(device).eval()
    m.load_state_dict(sd, strict=True, assign=True)
    return m


def _sample_indices(n: int, k: int = NUM_FRAMES) -> np.ndarray:
    if n <= k:
        return np.concatenate([np.arange(n), np.full(k - n, n - 1, dtype=np.int64)])
    step = n / k
    return np.clip((np.arange(k) * step + step / 2.0).astype(np.int64), 0, n - 1)


def _frames_from_mp4(path: str) -> np.ndarray:
    from decord import VideoReader, cpu
    vr = VideoReader(path, ctx=cpu(0))
    idx = _sample_indices(len(vr))
    return vr.get_batch(idx).asnumpy()           # (T,H,W,3) RGB uint8


def _frames_from_dir(path: str) -> np.ndarray:
    import cv2
    jpgs = sorted(Path(path).glob("*.jpg"), key=lambda p: int(p.stem) if p.stem.isdigit() else 0)
    if not jpgs:
        raise FileNotFoundError(f"no jpg in {path}")
    idx = _sample_indices(len(jpgs))
    out = []
    for i in idx:
        im = cv2.imread(str(jpgs[int(i)]))
        out.append(im[:, :, ::-1])               # BGR→RGB
    return np.stack(out, 0)


def _preprocess(frames_rgb: np.ndarray, device: str) -> torch.Tensor:
    """(T,H,W,3) uint8 → (1,3,T,224,224) 정규화. 학습 eval 전처리와 동일."""
    t = torch.from_numpy(np.ascontiguousarray(frames_rgb)).permute(0, 3, 1, 2)  # (T,3,H,W)
    t = TF.resize(t, int(IMG_SIZE * 1.15), antialias=True)
    t = TF.center_crop(t, [IMG_SIZE, IMG_SIZE]).float().div_(255.0)
    t = (t - IMAGENET_MEAN) / IMAGENET_STD
    return t.unsqueeze(0).permute(0, 2, 1, 3, 4).contiguous().to(device)         # (1,3,T,224,224)


class VideoMAEHierClassifier:
    def __init__(self, binary_ckpt: str, sub_ckpt: str, device: str = "cuda:0"):
        self.device = device if torch.cuda.is_available() else "cpu"
        self.binary = _load_head(binary_ckpt, self.device)
        self.sub = _load_head(sub_ckpt, self.device)
        self.binary_ckpt, self.sub_ckpt = binary_ckpt, sub_ckpt

    @torch.no_grad()
    def predict(self, clip_path: str, event_id: str | None = None) -> dict:
        t0 = time.time()
        try:
            p = str(clip_path)
            frames = _frames_from_dir(p) if Path(p).is_dir() else _frames_from_mp4(p)
            x = _preprocess(frames, self.device)

            pb = torch.softmax(self.binary(x), dim=-1)[0]            # [p_normal, p_anomaly]
            p_normal, p_anom = float(pb[0]), float(pb[1])
            ps = torch.softmax(self.sub(x), dim=-1)[0].cpu().numpy() # 4-class

            # 통합 5-class 확률: 정상=p_normal, 이상 k = p_anomaly * p_sub(k)
            scores5 = [p_normal] + [p_anom * float(ps[k]) for k in range(4)]

            if pb.argmax().item() == 0:                              # 계층 라우팅(이진 argmax)
                cat_id, conf = 0, p_normal
            else:
                sub_id = int(ps.argmax())
                cat_id, conf = sub_id + 1, p_anom * float(ps[sub_id])

            return {
                "schema_version": SCHEMA_VERSION,
                "status": "ok",
                "event_id": event_id,
                "model": {"name": "VideoMAE-V2-Base-hier",
                          "stage1_ckpt": self.binary_ckpt, "stage2_ckpt": self.sub_ckpt},
                "input": {"clip_path": p, "num_frames": NUM_FRAMES, "sampling": "uniform"},
                "result": {
                    "category_id": cat_id,                  # 0~4
                    "category": CLASS_NAMES[cat_id],        # 정상/폭력/응급/절도/배회·침입
                    "is_anomaly": cat_id != 0,
                    "confidence": round(conf, 4),
                    "stage1": {"label": "정상" if cat_id == 0 else "이상",
                               "p_normal": round(p_normal, 4), "p_anomaly": round(p_anom, 4)},
                    "stage2": None if cat_id == 0 else {
                        "top1": SUBCLASS_NAMES[int(ps.argmax())],
                        "probs": {SUBCLASS_NAMES[k]: round(float(ps[k]), 4) for k in range(4)}},
                    "scores_5class": {CLASS_NAMES[i]: round(float(scores5[i]), 4) for i in range(5)},
                },
                "latency_ms": int((time.time() - t0) * 1000),
            }
        except Exception as e:
            return {"schema_version": SCHEMA_VERSION, "status": "error",
                    "event_id": event_id, "error": f"{type(e).__name__}: {e}",
                    "latency_ms": int((time.time() - t0) * 1000)}


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary_ckpt", required=True)
    ap.add_argument("--sub_ckpt", required=True)
    ap.add_argument("--clip", required=True, help="mp4 파일 또는 frame 디렉터리")
    ap.add_argument("--device", default="cuda:0")
    a = ap.parse_args()
    clf = VideoMAEHierClassifier(a.binary_ckpt, a.sub_ckpt, a.device)
    print(json.dumps(clf.predict(a.clip), ensure_ascii=False, indent=2))
