"""Frame extraction tests. We generate a tiny real video with ffmpeg
so the test exercises the actual pipeline, and skip cleanly on
machines without ffmpeg installed."""

import subprocess

import pytest

from app.scope import Attachment
from app.video import extract_frames, ffmpeg_available

pytestmark = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")


@pytest.fixture(scope="module")
def tiny_video(tmp_path_factory) -> bytes:
    """A 2-second synthetic test-pattern clip, ~a phone video in miniature."""
    path = tmp_path_factory.mktemp("vid") / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=12",
            "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
        timeout=60,
    )
    return path.read_bytes()


def test_video_kind_is_detected():
    assert Attachment("walkthrough.MOV", b"x").kind == "video"
    assert Attachment("clip.mp4", b"x").kind == "video"


def test_frames_are_extracted_and_are_jpegs(tiny_video):
    frames = extract_frames(tiny_video, max_frames=5)
    assert 1 <= len(frames) <= 5
    for f in frames:
        assert f[:2] == b"\xff\xd8"  # JPEG magic bytes


def test_garbage_bytes_yield_no_frames_not_an_error():
    assert extract_frames(b"this is not a video") == []


def test_empty_input_yields_no_frames():
    assert extract_frames(b"") == []
