"""
vadclip_adapter.py
Jetson live camera frame window -> VadCLIP t1 anomaly score adapter.

This module extracts only the production path already validated in
90_edge_runtime_jetson_v2.py:
  BGR frame -> official image_crop(frame, 5) -> official CLIP preprocess
  -> ViT-B/16 image feature -> rolling 256-snippet feature buffer
  -> VadCLIP C-branch (forward_mode=b) -> latest 10-snippet top-k mean.

The live camera is 9fps while the UCF feature convention is 30fps with
stride 16. To preserve the temporal interval, one inference consumes a
48-frame (~5.33s) live window and samples 10 representative frames at
approximately 0.533s intervals.
"""

from __future__ import annotations

import gc
import importlib
import logging
import os
import sys
from collections import deque
from pathlib import Path
from typing import Callable, Iterable, Tuple

import numpy as np

from ring_buffer import (
    FPS,
    INFER_WINDOW_LEN,
    VADCLIP_REFERENCE_FPS,
    VADCLIP_SNIPPETS_PER_WINDOW,
    VADCLIP_STRIDE,
)

logger = logging.getLogger("vadclip_adapter")

# Official VadCLIP UCF-Crime model configuration.
CLASSES_NUM = 14
EMBED_DIM = 512
VISUAL_LENGTH = 256
VISUAL_WIDTH = 512
VISUAL_HEAD = 1
VISUAL_LAYERS = 2
ATTN_WINDOW = 8
PROMPT_PREFIX = 10
PROMPT_POSTFIX = 10

DEFAULT_REPO = "/home/hpc/edge_vadclip_2026/VadCLIP"
DEFAULT_CKPT = "/home/hpc/edge_vadclip_2026/VadCLIP/assets/model_ucf.pth"
DEFAULT_CLIP_MODEL = "/home/hpc/edge_vadclip_2026/VadCLIP/assets/ViT-B-16.pt"


class FeatureRingBuffer:
    """Keep the latest VadCLIP snippet features and zero-pad to visual_length."""

    def __init__(self, maxlen: int = VISUAL_LENGTH, dim: int = EMBED_DIM):
        self.maxlen = maxlen
        self.dim = dim
        self.buf = deque(maxlen=maxlen)

    def push(self, feats: np.ndarray) -> None:
        arr = np.atleast_2d(np.asarray(feats, dtype=np.float32))
        if arr.shape[1] != self.dim:
            raise ValueError(f"feature dim mismatch: got {arr.shape}, expected (*,{self.dim})")
        for f in arr:
            self.buf.append(f.copy())

    def __len__(self) -> int:
        return len(self.buf)

    def clear(self) -> None:
        self.buf.clear()

    def as_input(self) -> Tuple[np.ndarray, int]:
        n = len(self.buf)
        x = np.zeros((self.maxlen, self.dim), dtype=np.float32)
        if n:
            x[:n] = np.stack(self.buf, axis=0)
        return x, n


def _prepend_repo_paths(repo: Path) -> None:
    """Put vendored VadCLIP modules ahead of site-packages/current directory."""
    candidates = [repo / "src", repo]
    for p in reversed(candidates):
        s = str(p)
        if p.exists() and s not in sys.path:
            sys.path.insert(0, s)


def _resolve_symbol(name: str) -> Callable:
    for module_name in ("crop", "utils.tools", "tools", "utils.dataset", "utils", "model"):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        if hasattr(module, name):
            return getattr(module, name)
    raise ImportError(f"VadCLIP symbol not found: {name}")


def _sample_indices() -> np.ndarray:
    """Map 30fps stride-16 representatives to the 9fps live window by time."""
    step_live_frames = VADCLIP_STRIDE * FPS / VADCLIP_REFERENCE_FPS
    idx = np.rint(
        np.arange(VADCLIP_SNIPPETS_PER_WINDOW, dtype=np.float64) * step_live_frames
    ).astype(np.int64)
    if idx[-1] >= INFER_WINDOW_LEN:
        raise RuntimeError(
            f"sampling index {idx[-1]} outside INFER_WINDOW_LEN={INFER_WINDOW_LEN}"
        )
    return idx


class _VadCLIPHead:
    """VadCLIP C-branch only, equivalent to validated forward_mode=b runtime."""

    def __init__(self, repo: Path, ckpt: Path, clip_model: Path, device: str):
        import torch

        self.torch = torch
        self.device = device

        _prepend_repo_paths(repo)

        # Force the CLIPVAD constructor to use the shipped ViT-B/16 asset instead
        # of depending on ~/.cache/clip or network access.
        clip_impl = importlib.import_module("clip.clip")
        original_clip_load = clip_impl.load

        def _local_clip_load(name, *args, **kwargs):
            if name == "ViT-B/16":
                name = str(clip_model)
            return original_clip_load(name, *args, **kwargs)

        clip_impl.load = _local_clip_load
        try:
            model_mod = importlib.import_module("model")
            model_file = Path(getattr(model_mod, "__file__", "")).resolve()
            expected_src = (repo / "src").resolve()
            if expected_src not in model_file.parents:
                raise RuntimeError(
                    f"wrong 'model' module imported: {model_file}; expected under {expected_src}"
                )
            Model = getattr(model_mod, "CLIPVAD")
            self.model = Model(
                CLASSES_NUM,
                EMBED_DIM,
                VISUAL_LENGTH,
                VISUAL_WIDTH,
                VISUAL_HEAD,
                VISUAL_LAYERS,
                ATTN_WINDOW,
                PROMPT_PREFIX,
                PROMPT_POSTFIX,
                device,
            ).to(device)
        finally:
            clip_impl.load = original_clip_load

        state = torch.load(str(ckpt), map_location="cpu")
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        self.model.load_state_dict(state, strict=True)
        self.model.eval()
        logger.info("VadCLIP checkpoint strict load PASS (%d keys)", len(state))

        self.get_batch_mask = _resolve_symbol("get_batch_mask")

        # t1-only path does not use the text CLIP branch. Release it before
        # loading the separate image encoder to keep Xavier NX memory bounded.
        del state
        if hasattr(self.model, "clipmodel"):
            del self.model.clipmodel
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def prob1(self, x: np.ndarray, valid_len: int) -> np.ndarray:
        torch = self.torch
        with torch.no_grad():
            v = torch.from_numpy(x).unsqueeze(0).to(self.device)
            lengths = torch.tensor([valid_len], dtype=torch.long)
            mask = self.get_batch_mask(lengths, VISUAL_LENGTH)
            if hasattr(mask, "to"):
                mask = mask.to(self.device)

            feats = self.model.encode_video(v, mask, lengths)
            if isinstance(feats, (tuple, list)):
                feats = feats[0]
            logits = self.model.classifier(feats + self.model.mlp2(feats))
            return torch.sigmoid(logits).squeeze().float().cpu().numpy().ravel()


class _ClipFeatureExtractor:
    """Official crop-5 + official CLIP preprocessing on BGR frames."""

    def __init__(self, repo: Path, clip_model: Path, device: str, crop_index: int):
        import torch
        from PIL import Image

        _prepend_repo_paths(repo)
        clip_pkg = importlib.import_module("clip")

        self.torch = torch
        self.Image = Image
        self.device = device
        self.crop_index = crop_index
        self.model, self.preprocess = clip_pkg.load(str(clip_model), device=device)
        self.model.eval()
        self.image_crop = _resolve_symbol("image_crop")

        logger.info(
            "CLIP image encoder loaded: %s, crop_index=%d",
            clip_model,
            crop_index,
        )

    def _crop(self, frame_bgr: np.ndarray):
        # IMPORTANT: image_crop performs BGR->RGB internally. Do not pre-swap.
        out = self.image_crop(frame_bgr, self.crop_index)
        if isinstance(out, self.Image.Image):
            return out
        arr = np.asarray(out)
        if arr.dtype != np.uint8:
            arr = np.clip(arr * 255 if arr.max() <= 1.0 else arr, 0, 255).astype(np.uint8)
        return self.Image.fromarray(arr)

    def encode_bgr(self, frames_bgr: Iterable[np.ndarray]) -> np.ndarray:
        torch = self.torch
        tensors = [self.preprocess(self._crop(frame)) for frame in frames_bgr]
        if not tensors:
            return np.zeros((0, EMBED_DIM), dtype=np.float32)
        x = torch.stack(tensors).to(self.device)
        if next(self.model.parameters()).dtype == torch.float16:
            x = x.half()
        with torch.no_grad():
            out = self.model.encode_image(x)
        return out.float().cpu().numpy().astype(np.float32)


class VadCLIPScorer:
    """Stateful live VadCLIP scorer used by anomaly_model.AnomalyPipeline."""

    def __init__(self):
        self.repo = Path(os.environ.get("VADCLIP_REPO", DEFAULT_REPO)).resolve()
        self.ckpt = Path(os.environ.get("VADCLIP_CKPT", DEFAULT_CKPT)).resolve()
        self.clip_model = Path(
            os.environ.get("VADCLIP_CLIP_MODEL", DEFAULT_CLIP_MODEL)
        ).resolve()
        self.device = os.environ.get("VADCLIP_DEVICE", "cuda")
        self.crop_index = int(os.environ.get("VADCLIP_CROP_INDEX", "5"))
        self.topk = int(os.environ.get("VADCLIP_TOPK", "3"))

        self._validate_paths()

        import torch

        if self.device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("VADCLIP_DEVICE requests CUDA but torch.cuda.is_available() is False")

        self.sample_indices = _sample_indices()
        logger.info(
            "VadCLIP live temporal mapping: FPS=%d, window=%d frames (%.3fs), sample_indices=%s",
            FPS,
            INFER_WINDOW_LEN,
            INFER_WINDOW_LEN / FPS,
            self.sample_indices.tolist(),
        )

        self.feature_buffer = FeatureRingBuffer(VISUAL_LENGTH, EMBED_DIM)

        # Order matters for Xavier NX peak memory: construct head, strict-load,
        # release its unused text CLIP, then load the image encoder.
        self.head = _VadCLIPHead(self.repo, self.ckpt, self.clip_model, self.device)
        self.extractor = _ClipFeatureExtractor(
            self.repo, self.clip_model, self.device, self.crop_index
        )

    @property
    def feature_buffer_len(self) -> int:
        return len(self.feature_buffer)

    @property
    def visual_length(self) -> int:
        return VISUAL_LENGTH

    def warmup(self) -> float:
        """Warm CUDA/CLIP/VadCLIP once without contaminating live history."""
        dummy = np.zeros((INFER_WINDOW_LEN, 224, 224, 3), dtype=np.uint8)
        score = self.compute_score(dummy)
        self.feature_buffer.clear()
        logger.info("VadCLIP warmup PASS: score=%.6f, feature_buffer reset to 0", score)
        return score

    def _validate_paths(self) -> None:
        required = {
            "VADCLIP_REPO": self.repo,
            "VADCLIP_CKPT": self.ckpt,
            "VADCLIP_CLIP_MODEL": self.clip_model,
            "VadCLIP src/model.py": self.repo / "src" / "model.py",
            "VadCLIP src/crop.py": self.repo / "src" / "crop.py",
            "VadCLIP src/utils/tools.py": self.repo / "src" / "utils" / "tools.py",
        }
        missing = [f"{name}={path}" for name, path in required.items() if not path.exists()]
        if missing:
            raise FileNotFoundError("VadCLIP required asset(s) missing: " + "; ".join(missing))
        if not 1 <= self.topk <= VADCLIP_SNIPPETS_PER_WINDOW:
            raise ValueError(
                f"VADCLIP_TOPK must be 1..{VADCLIP_SNIPPETS_PER_WINDOW}, got {self.topk}"
            )

    def compute_score(self, window: np.ndarray) -> float:
        arr = np.asarray(window)
        if arr.ndim != 4 or arr.shape[-1] != 3:
            raise ValueError(f"expected (T,H,W,3) BGR window, got {arr.shape}")
        if arr.shape[0] < INFER_WINDOW_LEN:
            raise ValueError(
                f"VadCLIP needs at least {INFER_WINDOW_LEN} live frames, got {arr.shape[0]}"
            )
        if arr.dtype != np.uint8:
            raise ValueError(f"VadCLIP expects uint8 BGR frames, got {arr.dtype}")

        # If a caller supplies more than the configured window, use the latest
        # complete window so the score corresponds to the newest live interval.
        arr = arr[-INFER_WINDOW_LEN:]
        representative_frames = arr[self.sample_indices]

        feats = self.extractor.encode_bgr(representative_frames)
        if feats.shape != (VADCLIP_SNIPPETS_PER_WINDOW, EMBED_DIM):
            raise RuntimeError(
                f"CLIP feature shape mismatch: {feats.shape}, "
                f"expected ({VADCLIP_SNIPPETS_PER_WINDOW},{EMBED_DIM})"
            )

        self.feature_buffer.push(feats)
        x, valid_len = self.feature_buffer.as_input()
        prob1 = self.head.prob1(x, valid_len)

        n = min(valid_len, len(prob1))
        lo = max(0, n - VADCLIP_SNIPPETS_PER_WINDOW)
        seg = np.asarray(prob1[lo:n], dtype=np.float64)
        if seg.size == 0:
            return 0.0
        ordered = np.sort(seg)[::-1]
        score = float(ordered[: min(self.topk, ordered.size)].mean())
        return max(0.0, min(1.0, score))
