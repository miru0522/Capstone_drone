import json
from pathlib import Path

from persistent_h264_pipeline_prototype import PersistentH264Pipeline
from persistent_pipeline_test import BITRATE, FPS, HEIGHT, WIDTH, make_frames


output_dir = Path("/tmp/h264_pipeline_reuse_20261002/timing_probe")
output_dir.mkdir(parents=True, exist_ok=True)
encoder = PersistentH264Pipeline(WIDTH, HEIGHT, FPS, BITRATE)
results = {"startup": encoder.start(), "requests": []}
try:
    for index, count in enumerate((2, 81, 81)):
        frames = make_frames(index)[:count]
        results["requests"].append(
            encoder.encode(frames, output_dir / f"request_{index}_{count}.mp4")
        )
finally:
    encoder.close()
print(json.dumps(results, ensure_ascii=False, indent=2))
