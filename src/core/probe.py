"""Reading what's in a file: quality with ffprobe, frames with ffmpeg, pictures with Pillow.

Only files that look like duplicates are read, and results are cached by
path, size and modification time, so later scans are quick.
"""

import hashlib
import json
import os
import shutil
import subprocess

from PIL import Image

import utils.config as config

FRAME_POINTS = (0.2, 0.35, 0.5, 0.65, 0.8)


def wrap(command):
    """Run at idle CPU and disk priority when "Run at low priority" is on."""
    if not getattr(config, "low_priority", True):
        return list(command)
    prefix = []
    if shutil.which("nice"):
        prefix += ["nice", "-n", "19"]
    if shutil.which("ionice"):
        prefix += ["ionice", "-c", "3"]
    return prefix + list(command)


def quick_hash(path, size):
    """A fingerprint from the size and the first and last megabyte: equal for identical copies."""
    h = hashlib.sha1(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
        if size > 2 << 20:
            f.seek(-(1 << 20), os.SEEK_END)
            h.update(f.read(1 << 20))
    return h.hexdigest()


def full_hash(path):
    """A fingerprint of the whole file."""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def video_info(path):
    """Resolution, HDR, audio and length, or {"error": ...}."""
    try:
        out = subprocess.run(wrap(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]),
                             capture_output=True, timeout=120, check=True).stdout
        data = json.loads(out)
    except (subprocess.SubprocessError, ValueError, OSError) as e:
        return {"error": f"ffprobe couldn't read it ({e.__class__.__name__})"}
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not (s.get("disposition") or {}).get("attached_pic")), {})
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    transfer = video.get("color_transfer", "")
    side = " ".join(str(d.get("side_data_type", "")) for d in video.get("side_data_list") or [])
    dolby_vision = "DOVI" in side or video.get("codec_tag_string", "") in ("dvhe", "dvh1")
    best_audio = max(audio, key=lambda a: a.get("channels", 0), default={})
    try:
        duration = float((data.get("format") or {}).get("duration") or video.get("duration") or 0)
    except ValueError:
        duration = 0.0
    return {
        "duration": duration,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "codec": video.get("codec_name", ""),
        "hdr": "DV" if dolby_vision else "HDR10" if transfer == "smpte2084" else "HLG" if transfer == "arib-std-b67" else "",
        "audio": best_audio.get("codec_name", ""),
        "audio_profile": best_audio.get("profile", "") or "",
        "channels": int(best_audio.get("channels") or 0),
        "audio_tracks": len(audio),
    }


def _dhash(gray_pixels, width=9, height=8):
    bits = 0
    for y in range(height):
        row = gray_pixels[y * width:(y + 1) * width]
        for x in range(width - 1):
            bits = (bits << 1) | (row[x] > row[x + 1])
    return bits


def frame_hashes(path, duration):
    """A small fingerprint of frames at fixed points through the video.

    The middle of each frame is used, so black bars and slightly different crops don't matter.
    """
    hashes = []
    for point in FRAME_POINTS:
        try:
            raw = subprocess.run(wrap([
                "ffmpeg", "-v", "error", "-ss", f"{duration * point:.2f}", "-i", path, "-frames:v", "1",
                "-vf", "crop=iw*0.8:ih*0.6,scale=9:8:flags=area,format=gray", "-f", "rawvideo", "-"]),
                capture_output=True, timeout=120, check=True).stdout
        except (subprocess.SubprocessError, OSError):
            raw = b""
        hashes.append(_dhash(raw) if len(raw) == 72 else None)
    return hashes


def bits_apart(a, b):
    return bin(a ^ b).count("1")


def same_frames(a, b, limit=12):
    """True when most of the frames match, False when most don't, None when it can't tell."""
    pairs = [(x, y) for x, y in zip(a or [], b or []) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    matches = sum(bits_apart(x, y) <= limit for x, y in pairs)
    if matches >= len(pairs) - 1:
        return True
    return False if matches <= 1 else None


def image_size(path):
    """(width, height) from the picture's header, without decoding it, or None."""
    try:
        with Image.open(path) as im:
            return im.size
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def image_hash(path):
    """(dhash, width, height) of a picture, or None if it can't be read."""
    try:
        with Image.open(path) as im:
            width, height = im.size
            # JPEGs can be decoded at an eighth of the size, which is much quicker and plenty for a 9x8 fingerprint
            im.draft("L", (64, 64))
            small = im.convert("L").resize((9, 8), Image.BOX)
            return _dhash(list(small.tobytes())), width, height
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
