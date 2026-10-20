"""Video -> frames: the recorded half of the guided-video tier.

A 30-60 second walkthrough carries far more scope information than
photos, but the vision model reads images, so we sample the video into
8-10 evenly spaced JPEG frames with ffmpeg and feed those through the
same photo pipeline. (Phase 2's LIVE direction - Jev telling the
homeowner "pan left" in real time - builds on exactly this sampling.)

Requires the ffmpeg system binary. When it's missing we return no
frames and the gate records the gap instead of crashing - degrade
toward less commitment, never toward a bad guarantee.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}
MAX_VIDEO_BYTES = 60 * 1024 * 1024  # a minute of phone video fits easily
MAX_FRAMES = 8


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def extract_frames(video_bytes: bytes, max_frames: int = MAX_FRAMES) -> list[bytes]:
    """Sample a video into up to max_frames JPEGs, spread evenly.

    Returns [] when ffmpeg is missing or the file can't be decoded -
    callers treat an empty result as a visibility gap, not an error."""
    if not ffmpeg_available() or not video_bytes:
        return []
    if len(video_bytes) > MAX_VIDEO_BYTES:
        return []

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "input.video"
        src.write_bytes(video_bytes)

        duration = _duration_seconds(src)
        if duration <= 0:
            return []
        # One frame every duration/max_frames seconds covers the whole clip.
        fps = max_frames / duration

        out_pattern = Path(tmp) / "frame_%02d.jpg"
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", str(src),
                "-vf", f"fps={fps:.6f},scale='min(1280,iw)':-2",
                "-frames:v", str(max_frames),
                "-q:v", "4",  # decent JPEG quality, small files
                str(out_pattern),
            ],
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0:
            return []
        frames = sorted(Path(tmp).glob("frame_*.jpg"))
        return [f.read_bytes() for f in frames]


def _duration_seconds(path: Path) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float(result.stdout.strip())
    except (ValueError, subprocess.SubprocessError):
        return 0.0
