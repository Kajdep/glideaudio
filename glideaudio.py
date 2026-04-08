from __future__ import annotations

import io
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import customtkinter as ctk
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import COPY, DND_FILES, TkinterDnD

if os.name == "nt":
    import ctypes


APP_NAME = "GlideAudio"
APP_MARKETING_VERSION = "0.1.0"
WINDOW_SIZE = "1480x1040"
MIN_WINDOW_SIZE = (1220, 860)
SOURCE_PREVIEW_SIZE = (520, 286)
AB_PREVIEW_SIZE = (520, 170)
SOURCE_PREVIEW_ASPECT = SOURCE_PREVIEW_SIZE[0] / SOURCE_PREVIEW_SIZE[1]
AB_PREVIEW_ASPECT = AB_PREVIEW_SIZE[0] / AB_PREVIEW_SIZE[1]
ANALYSIS_SAMPLE_RATE = 16000
ANALYSIS_MAX_SECONDS = 90.0
DEFAULT_PREVIEW_SECONDS = 10.0
MIN_PREVIEW_SECONDS = 4.0
PREVIEW_MCI_ALIAS = "glideaudio_preview"

MEDIA_FILE_TYPES = "*.mp4;*.mov;*.mkv;*.avi;*.webm;*.m4v;*.mp3;*.wav;*.m4a;*.aac;*.flac;*.ogg;*.opus"

COLORS = {
    "bg_primary": "#050505",
    "bg_secondary": "#111111",
    "bg_tertiary": "#181818",
    "surface": "#151515",
    "surface_alt": "#202020",
    "primary": "#D86B21",
    "primary_hover": "#F28135",
    "primary_soft": "#FFB36B",
    "text_primary": "#F5EFE6",
    "text_secondary": "#B59C84",
    "text_muted": "#7C6E61",
    "border": "#2D2118",
    "track": "#24170F",
    "success": "#38C172",
    "warning": "#F4C95D",
    "error": "#FF6B6B",
}

PRESET_VALUES: dict[str, dict[str, float]] = {
    "Custom": {
        "noise": 0.28,
        "clarity": 0.36,
        "de_echo": 0.10,
        "de_hum": 0.14,
        "leveling": 0.38,
        "limiter": 0.64,
    },
    "Clean Voice": {
        "noise": 0.28,
        "clarity": 0.36,
        "de_echo": 0.08,
        "de_hum": 0.10,
        "leveling": 0.32,
        "limiter": 0.62,
    },
    "Noisy Room": {
        "noise": 0.68,
        "clarity": 0.48,
        "de_echo": 0.44,
        "de_hum": 0.34,
        "leveling": 0.42,
        "limiter": 0.74,
    },
    "Screen Recording Voiceover": {
        "noise": 0.20,
        "clarity": 0.50,
        "de_echo": 0.04,
        "de_hum": 0.18,
        "leveling": 0.44,
        "limiter": 0.58,
    },
    "Podcast Speech": {
        "noise": 0.16,
        "clarity": 0.38,
        "de_echo": 0.04,
        "de_hum": 0.12,
        "leveling": 0.48,
        "limiter": 0.66,
    },
    "Social Clip Speech": {
        "noise": 0.34,
        "clarity": 0.56,
        "de_echo": 0.14,
        "de_hum": 0.18,
        "leveling": 0.60,
        "limiter": 0.80,
    },
    "Loudness Match Only": {
        "noise": 0.00,
        "clarity": 0.08,
        "de_echo": 0.00,
        "de_hum": 0.00,
        "leveling": 0.66,
        "limiter": 0.72,
    },
}

LOUDNESS_TARGETS: dict[str, Optional[float]] = {
    "YouTube / Social (-14 LUFS)": -14.0,
    "Podcast Speech (-16 LUFS)": -16.0,
    "Broadcast-ish (-19 LUFS)": -19.0,
    "Preserve Source Loudness": None,
}

EXPORT_MODE_AUDIO = "Cleaned Audio"
EXPORT_MODE_VIDEO = "Repaired Video"
EXPORT_FORMATS = {
    EXPORT_MODE_AUDIO: ["WAV", "MP3", "AAC"],
    EXPORT_MODE_VIDEO: ["MP4"],
}

PREVIEW_LENGTHS = ["6 sec", "10 sec", "15 sec", "20 sec"]
SLIDER_KEYS = [
    ("noise", "Noise Reduction"),
    ("clarity", "Voice Clarity"),
    ("de_echo", "De-Echo"),
    ("de_hum", "De-Hum"),
    ("leveling", "Leveling"),
    ("limiter", "Limiter"),
]


@dataclass
class MediaInfo:
    path: Path
    duration: float
    has_video: bool
    has_audio: bool
    width: int
    height: int
    sample_rate: int
    channels: int
    audio_codec: str
    video_codec: str


@dataclass
class AudioDiagnostics:
    peak_dbfs: float
    average_lufs: float
    noise_floor_dbfs: float
    clipping_risk: str
    speech_presence: str
    speech_score: float
    clip_events: int


@dataclass
class BatchQueueItem:
    item_id: str
    path: Path
    status: str = "Queued"
    detail: str = "Waiting to export."
    output_path: Optional[Path] = None


def ui_font(size: int, weight: str = "normal"):
    return ("Space Grotesk", size, weight)


def mono_font(size: int, weight: str = "normal"):
    return ("JetBrains Mono", size, weight)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def format_seconds(seconds: float) -> str:
    total = max(0.0, float(seconds))
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = total % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"
    return f"{minutes:02d}:{secs:05.2f}"


def shorten_middle(text: str, max_length: int = 72) -> str:
    if len(text) <= max_length:
        return text
    lead = max(16, (max_length - 3) // 2)
    tail = max(12, max_length - 3 - lead)
    return f"{text[:lead]}...{text[-tail:]}"


def compact_path_text(path: Path) -> str:
    parent = path.parent.name or str(path.parent)
    return f"{parent} | {shorten_middle(path.name, 58)}"


def parse_preview_length(label: str) -> float:
    match = re.search(r"(\d+)", label)
    if not match:
        return DEFAULT_PREVIEW_SECONDS
    return float(match.group(1))


def audio_mode_description(info: MediaInfo) -> str:
    if info.has_video:
        return f"Video source | {info.width}x{info.height}"
    return "Audio-only source"


def dbfs(value: float) -> float:
    return 20.0 * math.log10(max(float(value), 1e-9))


def odd_int(value: float, minimum: int = 3) -> int:
    rounded = max(minimum, int(round(value)))
    if rounded % 2 == 0:
        rounded += 1
    return rounded


def fit_aspect_size(aspect_ratio: float, max_width: int, max_height: Optional[int] = None) -> tuple[int, int]:
    bounded_width = max(80, int(max_width))
    height = max(60, int(round(bounded_width / max(aspect_ratio, 1e-6))))
    if max_height is not None and height > max_height:
        height = max(60, int(max_height))
        bounded_width = max(80, int(round(height * aspect_ratio)))
    return bounded_width, height


def load_brand_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Users/kajal/AppData/Local/Microsoft/Windows/Fonts/SpaceGrotesk-VariableFont_wght.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/bahnschrift.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def subprocess_window_kwargs() -> dict:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {
        "startupinfo": startupinfo,
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }


def _binary_filenames(binary_name: str) -> list[str]:
    if os.name == "nt":
        return [f"{binary_name}.exe", binary_name]
    return [binary_name]


def _iter_ffmpeg_roots() -> list[Path]:
    roots: list[Path] = []

    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass).resolve())

    script_dir = Path(__file__).resolve().parent
    roots.extend([script_dir, *script_dir.parents])

    for env_key in ("GLIDEAUDIO_FFMPEG_DIR", "FFMPEG_DIR", "FFMPEG_ROOT"):
        raw_value = os.environ.get(env_key)
        if raw_value:
            roots.append(Path(raw_value).expanduser())

    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        try:
            normalized = root.resolve()
        except FileNotFoundError:
            continue
        if normalized.exists() and normalized not in seen:
            unique_roots.append(normalized)
            seen.add(normalized)
    return unique_roots


@lru_cache(maxsize=None)
def resolve_binary(binary_name: str) -> str:
    explicit_env = os.environ.get(f"{binary_name.upper()}_PATH")
    if explicit_env:
        explicit_path = Path(explicit_env).expanduser()
        if explicit_path.exists():
            return str(explicit_path.resolve())

    for root in _iter_ffmpeg_roots():
        for relative in (Path("ffmpeg") / "bin", Path("ffmpeg"), Path("bin"), Path(".")):
            candidate_dir = (root / relative).resolve()
            if not candidate_dir.exists():
                continue
            for filename in _binary_filenames(binary_name):
                candidate = candidate_dir / filename
                if candidate.exists():
                    return str(candidate)

    located = shutil.which(binary_name)
    if located:
        return located

    raise FileNotFoundError(
        f"Could not find {binary_name}. Install FFmpeg, bundle it in an ffmpeg/bin folder, "
        f"or set {binary_name.upper()}_PATH."
    )


def parse_drop_paths(widget, raw_data: str) -> list[Path]:
    try:
        parts = widget.tk.splitlist(raw_data)
    except Exception:
        parts = [raw_data]
    parsed: list[Path] = []
    for item in parts:
        cleaned = item.strip().strip('"').strip("{}")
        if cleaned:
            parsed.append(Path(cleaned))
    return parsed


def parse_frame_rate(value: str | None) -> Optional[float]:
    if not value or value in {"0/0", "N/A"}:
        return None
    numerator, denominator = value.split("/")
    denominator_value = float(denominator)
    if denominator_value == 0:
        return None
    return float(numerator) / denominator_value


def probe_media(path: Path, ffprobe_path: str) -> MediaInfo:
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        **subprocess_window_kwargs(),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(detail or f"Could not read media metadata from {path}.")

    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams", [])
    video_stream = next(
        (
            stream
            for stream in streams
            if stream.get("codec_type") == "video"
            and not bool((stream.get("disposition") or {}).get("attached_pic"))
            and int(stream.get("width") or 0) > 0
            and int(stream.get("height") or 0) > 0
        ),
        None,
    )
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)

    duration = float(
        payload.get("format", {}).get("duration")
        or (video_stream or {}).get("duration")
        or (audio_stream or {}).get("duration")
        or 0.0
    )
    if duration <= 0:
        raise RuntimeError("Could not determine the media duration.")

    sample_rate = int((audio_stream or {}).get("sample_rate") or 0)
    channels = int((audio_stream or {}).get("channels") or 0)
    width = int((video_stream or {}).get("width") or 0)
    height = int((video_stream or {}).get("height") or 0)

    return MediaInfo(
        path=path,
        duration=duration,
        has_video=video_stream is not None,
        has_audio=audio_stream is not None,
        width=width,
        height=height,
        sample_rate=sample_rate,
        channels=channels,
        audio_codec=str((audio_stream or {}).get("codec_name") or "unknown"),
        video_codec=str((video_stream or {}).get("codec_name") or "unknown"),
    )


def decode_audio_samples(
    path: Path,
    ffmpeg_path: str,
    *,
    start: float = 0.0,
    duration: Optional[float] = None,
    sample_rate: int = ANALYSIS_SAMPLE_RATE,
    channels: int = 1,
    filter_chain: Optional[str] = None,
) -> np.ndarray:
    command = [ffmpeg_path, "-hide_banner", "-loglevel", "error"]
    if start > 0:
        command.extend(["-ss", f"{start:.3f}"])
    command.extend(["-i", str(path)])
    if duration is not None:
        command.extend(["-t", f"{duration:.3f}"])
    command.extend(["-vn", "-ac", str(channels), "-ar", str(sample_rate)])
    if filter_chain:
        command.extend(["-af", filter_chain])
    command.extend(["-f", "f32le", "-acodec", "pcm_f32le", "-"])
    result = subprocess.run(command, capture_output=True, check=False, **subprocess_window_kwargs())
    if result.returncode != 0:
        detail = (result.stderr or b"").decode("utf-8", errors="ignore").strip()
        raise RuntimeError(detail or "FFmpeg could not decode the source audio.")
    samples = np.frombuffer(result.stdout, dtype=np.float32)
    if channels > 1:
        if samples.size == 0:
            return np.zeros((0, channels), dtype=np.float32)
        trimmed = samples[: samples.size - (samples.size % channels)]
        return trimmed.reshape(-1, channels)
    return samples


def _frame_rms(samples: np.ndarray, sample_rate: int, frame_ms: float = 50.0) -> np.ndarray:
    frame_size = max(64, int(sample_rate * frame_ms / 1000.0))
    usable = samples[: samples.size - (samples.size % frame_size)]
    if usable.size == 0:
        return np.asarray([], dtype=np.float32)
    frames = usable.reshape(-1, frame_size)
    return np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)


def estimate_speech_score(samples: np.ndarray, sample_rate: int) -> float:
    if samples.size < sample_rate:
        return 0.0

    frame_size = min(2048, max(512, 2 ** int(math.log2(max(512, sample_rate // 4)))))
    hop_size = frame_size // 2
    window_count = 1 + max(0, (samples.size - frame_size) // hop_size)
    if window_count <= 0:
        return 0.0

    frame_indexes = np.arange(window_count) * hop_size
    if frame_indexes.size > 160:
        frame_indexes = frame_indexes[:: max(1, frame_indexes.size // 160)]

    frames = np.stack([samples[index : index + frame_size] for index in frame_indexes], axis=0)
    window = np.hanning(frame_size).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2
    freqs = np.fft.rfftfreq(frame_size, d=1.0 / sample_rate)

    total_energy = spectrum.sum(axis=1) + 1e-12
    speech_band = spectrum[:, (freqs >= 150.0) & (freqs <= 4000.0)].sum(axis=1)
    low_band = spectrum[:, freqs < 120.0].sum(axis=1)
    hiss_band = spectrum[:, freqs > 7000.0].sum(axis=1)

    band_ratio = np.mean(speech_band / total_energy)
    low_ratio = np.mean(low_band / total_energy)
    hiss_ratio = np.mean(hiss_band / total_energy)

    rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    activity_threshold = max(np.percentile(rms, 35), 0.003)
    activity_ratio = float(np.mean(rms > activity_threshold))
    dynamic_ratio = float(np.std(rms) / max(np.mean(rms), 1e-6))

    score = (
        0.48 * band_ratio
        + 0.28 * activity_ratio
        + 0.22 * clamp(dynamic_ratio / 0.9, 0.0, 1.0)
        - 0.16 * clamp(low_ratio / 0.4, 0.0, 1.0)
        - 0.10 * clamp(hiss_ratio / 0.2, 0.0, 1.0)
    )
    return clamp(score, 0.0, 1.0)


def loudnorm_probe(path: Path, ffmpeg_path: str, max_seconds: float = ANALYSIS_MAX_SECONDS) -> Optional[float]:
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "info",
        "-i",
        str(path),
        "-t",
        f"{max_seconds:.3f}",
        "-vn",
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        **subprocess_window_kwargs(),
    )
    combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if not combined:
        return None
    match = re.search(r"\{\s*\"input_i\".*?\}", combined, flags=re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
        return float(payload["input_i"])
    except Exception:
        return None


def peak_volume_probe(path: Path, ffmpeg_path: str, max_seconds: float = ANALYSIS_MAX_SECONDS) -> Optional[float]:
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "info",
        "-i",
        str(path),
        "-t",
        f"{max_seconds:.3f}",
        "-vn",
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        **subprocess_window_kwargs(),
    )
    combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
    match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", combined)
    if not match:
        return None
    try:
        return float(match.group(1))
    except Exception:
        return None


def analyze_audio_samples(
    samples: np.ndarray,
    sample_rate: int,
    *,
    average_lufs: Optional[float] = None,
    peak_dbfs: Optional[float] = None,
) -> AudioDiagnostics:
    if samples.size == 0:
        raise RuntimeError("The selected file does not contain readable audio samples.")

    peak = float(np.max(np.abs(samples)))
    peak_db = peak_dbfs if peak_dbfs is not None else dbfs(peak)
    rms = float(np.sqrt(np.mean(samples * samples) + 1e-12))
    rms_db = dbfs(rms)

    frame_rms = _frame_rms(samples, sample_rate)
    if frame_rms.size:
        noise_threshold = max(np.percentile(frame_rms, 40), 1e-6)
        noise_windows = frame_rms[frame_rms <= noise_threshold]
        noise_floor = float(np.percentile(noise_windows if noise_windows.size else frame_rms, 25))
    else:
        noise_floor = rms
    noise_floor_db = dbfs(noise_floor)

    clip_events = int(np.count_nonzero(np.abs(samples) >= 0.9995))
    if peak_dbfs is not None and peak_dbfs <= -1.5:
        clip_events = 0
    if peak_db >= -0.3 or clip_events > 24:
        clipping_risk = "High"
    elif peak_db >= -1.5 or clip_events > 0:
        clipping_risk = "Watch"
    else:
        clipping_risk = "Low"

    speech_score = float(estimate_speech_score(samples, sample_rate))
    if speech_score >= 0.66:
        speech_presence = "Strong"
    elif speech_score >= 0.44:
        speech_presence = "Moderate"
    else:
        speech_presence = "Weak"

    return AudioDiagnostics(
        peak_dbfs=peak_db,
        average_lufs=average_lufs if average_lufs is not None else rms_db,
        noise_floor_dbfs=noise_floor_db,
        clipping_risk=clipping_risk,
        speech_presence=speech_presence,
        speech_score=speech_score,
        clip_events=clip_events,
    )


def suggest_cleanup_preset(info: MediaInfo, diagnostics: AudioDiagnostics) -> tuple[str, str]:
    if diagnostics.peak_dbfs >= -1.2 and diagnostics.average_lufs >= -14.8:
        return "Loudness Match Only", "already loud and close to finished"
    if diagnostics.noise_floor_dbfs > -20.5 or (
        diagnostics.speech_score < 0.46 and diagnostics.noise_floor_dbfs > -23.0
    ):
        return "Noisy Room", "speech sits in noticeable room noise"
    if not info.has_video and diagnostics.noise_floor_dbfs <= -25.0 and diagnostics.speech_score >= 0.56:
        return "Podcast Speech", "audio-only speech is already fairly clean"
    if info.has_video and diagnostics.noise_floor_dbfs <= -23.5 and diagnostics.speech_score >= 0.58:
        return "Screen Recording Voiceover", "voice track is controlled and fairly clean"
    return "Clean Voice", "speech needs a light cleanup pass"


def fit_cover(image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    target_w, target_h = target_size
    if image.width <= 0 or image.height <= 0:
        return Image.new("RGBA", target_size, COLORS["bg_secondary"])
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize(
        (max(1, int(round(image.width * scale))), max(1, int(round(image.height * scale)))),
        Image.Resampling.LANCZOS,
    )
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def extract_video_frame(path: Path, ffmpeg_path: str, timestamp: float) -> Optional[Image.Image]:
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, check=False, **subprocess_window_kwargs())
    if result.returncode != 0 or not result.stdout:
        return None
    try:
        image = Image.open(io.BytesIO(result.stdout)).convert("RGBA")
        return image
    except Exception:
        return None


def waveform_card_image(samples: np.ndarray, size: tuple[int, int], *, title: str, subtitle: str) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size, COLORS["bg_secondary"])
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=COLORS["border"], width=1)

    plot_left = max(14, int(width * 0.035))
    plot_right = width - plot_left
    plot_top = max(12, int(height * 0.16))
    plot_bottom = height - plot_top
    mid_y = (plot_top + plot_bottom) // 2

    draw.line((plot_left, mid_y, plot_right, mid_y), fill=COLORS["track"], width=1)

    if samples.size > 0:
        mono = samples
        if mono.ndim > 1:
            mono = mono.mean(axis=1)
        chunk = max(1, mono.size // max(1, plot_right - plot_left))
        usable = mono[: mono.size - (mono.size % chunk)]
        if usable.size > 0:
            columns = usable.reshape(-1, chunk)
            peaks = np.max(np.abs(columns), axis=1)
            for index, peak in enumerate(peaks[: plot_right - plot_left]):
                x = plot_left + index
                amplitude = int(round(peak * ((plot_bottom - plot_top) / 2.0)))
                draw.line((x, mid_y - amplitude, x, mid_y + amplitude), fill=COLORS["primary"], width=1)
    else:
        idle_top = mid_y - max(8, int((plot_bottom - plot_top) * 0.12))
        idle_bottom = mid_y + max(8, int((plot_bottom - plot_top) * 0.12))
        draw.line((plot_left, idle_top, plot_right, idle_top), fill=COLORS["track"], width=1)
        draw.line((plot_left, idle_bottom, plot_right, idle_bottom), fill=COLORS["track"], width=1)
    return image


def frame_overlay_image(frame: Image.Image, *, title: str, line_one: str, line_two: str) -> Image.Image:
    image = Image.new("RGBA", SOURCE_PREVIEW_SIZE, COLORS["bg_secondary"])
    fitted = fit_cover(frame.convert("RGBA"), SOURCE_PREVIEW_SIZE)
    image.alpha_composite(fitted, (0, 0))
    ImageDraw.Draw(image).rectangle((0, 0, SOURCE_PREVIEW_SIZE[0] - 1, SOURCE_PREVIEW_SIZE[1] - 1), outline=COLORS["border"], width=1)
    return image


def build_source_preview_image(
    info: MediaInfo,
    *,
    ffmpeg_path: str,
    preview_samples: np.ndarray,
    thumbnail_time: float,
) -> Image.Image:
    if info.has_video:
        frame = extract_video_frame(info.path, ffmpeg_path, thumbnail_time)
        if frame is not None:
            return frame_overlay_image(
                frame,
                title=APP_NAME,
                line_one=shorten_middle(info.path.name, 46),
                line_two=f"{audio_mode_description(info)} | {format_seconds(info.duration)}",
            )
    return waveform_card_image(
        preview_samples,
        SOURCE_PREVIEW_SIZE,
        title="Source Overview",
        subtitle=f"{shorten_middle(info.path.name, 44)} | {format_seconds(info.duration)}",
    )


def build_preview_image(samples: np.ndarray, *, label: str, subtitle: str, size: tuple[int, int] = AB_PREVIEW_SIZE) -> Image.Image:
    return waveform_card_image(samples, size, title=label, subtitle=subtitle)


def build_audio_filter_chain(
    noise: float,
    clarity: float,
    de_echo: float,
    de_hum: float,
    leveling: float,
    limiter: float,
    *,
    loudness_target: Optional[float],
) -> str:
    filters: list[str] = []

    if de_hum > 0.02:
        highpass = 55.0 + de_hum * 45.0
        notch = 6.0 + de_hum * 12.0
        harmonic = 3.0 + de_hum * 7.0
        filters.extend(
            [
                f"highpass=f={highpass:.1f}",
                f"equalizer=f=50:t=q:w=1.0:g=-{notch:.1f}",
                f"equalizer=f=60:t=q:w=1.0:g=-{notch:.1f}",
                f"equalizer=f=100:t=q:w=1.2:g=-{harmonic:.1f}",
                f"equalizer=f=120:t=q:w=1.2:g=-{harmonic:.1f}",
            ]
        )

    if noise > 0.02:
        reduction = 4.0 + noise * 14.0
        noise_floor = -60.0 + noise * 16.0
        filters.append(f"afftdn=nr={reduction:.1f}:nf={noise_floor:.1f}")

    if de_echo > 0.02:
        mud_cut = 1.2 + de_echo * 4.0
        gate_ratio = 1.15 + de_echo * 1.65
        threshold = 0.0026 + (1.0 - de_echo) * 0.0014
        filters.extend(
            [
                f"equalizer=f=180:t=q:w=1.1:g=-{mud_cut:.1f}",
                f"equalizer=f=420:t=q:w=1.0:g=-{mud_cut * 0.8:.1f}",
                f"agate=threshold={threshold:.4f}:ratio={gate_ratio:.2f}:attack=8:release=220",
            ]
        )

    if clarity > 0.02:
        presence = 1.6 + clarity * 3.4
        air = 0.8 + clarity * 2.2
        low_mid_cut = clarity * 1.8
        filters.extend(
            [
                f"equalizer=f=250:t=q:w=1.1:g=-{low_mid_cut:.1f}",
                f"equalizer=f=2500:t=q:w=1.0:g={presence:.1f}",
                f"equalizer=f=6200:t=q:w=1.2:g={air:.1f}",
            ]
        )

    if leveling > 0.02:
        gaussian_size = odd_int(9 + leveling * 20, minimum=5)
        max_gain = 2.4 + leveling * 10.5
        peak = 0.78 + leveling * 0.08
        filters.append(f"dynaudnorm=f=200:g={gaussian_size}:m={max_gain:.1f}:p={peak:.2f}")

    if loudness_target is not None:
        filters.append(f"loudnorm=I={loudness_target:.1f}:TP=-2.0:LRA=11")

    if limiter > 0.02:
        filters.append("aresample=96000")
        limit = 0.95 - limiter * 0.08
        release = 45.0 + limiter * 95.0
        filters.append(f"alimiter=limit={limit:.2f}:attack=4:release={release:.0f}:level=0:latency=1:asc=1:asc_level=0.35")

    filters.append("aresample=48000")
    return ",".join(filters)


def create_preview_wav(
    input_path: Path,
    output_path: Path,
    ffmpeg_path: str,
    *,
    start: float,
    duration: float,
    filter_chain: Optional[str] = None,
) -> None:
    command = [
        ffmpeg_path,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(input_path),
        "-t",
        f"{duration:.3f}",
        "-vn",
        "-ac",
        "2",
        "-ar",
        "44100",
    ]
    if filter_chain:
        command.extend(["-af", filter_chain])
    command.extend(["-c:a", "pcm_s16le", str(output_path)])
    result = subprocess.run(command, capture_output=True, check=False, **subprocess_window_kwargs())
    if result.returncode != 0:
        detail = (result.stderr or b"").decode("utf-8", errors="ignore").strip()
        raise RuntimeError(detail or "FFmpeg could not create the preview audio.")


def build_audio_export_command(
    input_path: Path,
    output_path: Path,
    ffmpeg_path: str,
    *,
    filter_chain: str,
    format_name: str,
) -> list[str]:
    command = [
        ffmpeg_path,
        "-y",
        "-hide_banner",
        "-i",
        str(input_path),
        "-map",
        "0:a:0",
        "-vn",
        "-af",
        filter_chain,
    ]
    format_key = format_name.upper()
    if format_key == "WAV":
        command.extend(["-c:a", "pcm_s16le"])
    elif format_key == "MP3":
        command.extend(["-c:a", "libmp3lame", "-q:a", "2"])
    elif format_key == "AAC":
        command.extend(["-c:a", "aac", "-b:a", "192k"])
    else:
        raise ValueError(f"Unsupported audio format: {format_name}")
    command.append(str(output_path))
    return command


def build_video_export_command(
    input_path: Path,
    output_path: Path,
    ffmpeg_path: str,
    *,
    filter_chain: str,
) -> list[str]:
    return [
        ffmpeg_path,
        "-y",
        "-hide_banner",
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-shortest",
        "-c:v",
        "copy",
        "-af",
        filter_chain,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def run_ffmpeg_with_progress(
    command: list[str],
    *,
    duration: float,
    cancel_event: threading.Event,
    log_callback,
    progress_callback,
    process_callback=None,
) -> None:
    command_with_progress = [*command[:-1], "-progress", "pipe:1", "-nostats", command[-1]]
    process = subprocess.Popen(
        command_with_progress,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        universal_newlines=True,
        **subprocess_window_kwargs(),
    )
    if process_callback is not None:
        process_callback(process)

    tail_lines: list[str] = []
    try:
        assert process.stdout is not None
        for raw_line in process.stdout:
            if cancel_event.is_set():
                process.terminate()
                raise RuntimeError("cancelled")
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("out_time_ms="):
                out_time_ms = int(line.split("=", 1)[1] or "0")
                progress_callback(clamp((out_time_ms / 1_000_000.0) / max(duration, 0.01), 0.0, 1.0))
                continue
            if line == "progress=end":
                progress_callback(1.0)
                continue
            tail_lines.append(line)
            if len(tail_lines) > 60:
                tail_lines = tail_lines[-60:]
            if "=" not in line:
                log_callback(line)

        process.wait()
        if process.returncode != 0:
            detail = "\n".join(tail_lines[-20:]).strip()
            raise RuntimeError(detail or f"FFmpeg exited with code {process.returncode}.")
    finally:
        if process_callback is not None:
            process_callback(None)


def friendly_export_error(detail: str, *, output_path: Optional[Path] = None, format_name: Optional[str] = None) -> str:
    lowered = detail.lower()
    if "permission denied" in lowered or "access is denied" in lowered:
        location = f"\n{output_path}" if output_path is not None else ""
        return (
            "GlideAudio could not write the export file. Close any app using that file and choose a writable folder."
            f"{location}"
        )
    if "unknown encoder" in lowered or "encoder not found" in lowered:
        format_hint = f" for {format_name}" if format_name else ""
        return f"FFmpeg on this machine cannot encode the selected export format{format_hint}. Try WAV or install a fuller FFmpeg build."
    if "invalid argument" in lowered:
        return "The selected export settings produced an invalid FFmpeg command. Try another format or output path."
    if "no such file or directory" in lowered:
        return "GlideAudio could not find the selected source file or export folder."
    if "error opening output" in lowered:
        return "GlideAudio could not open the export destination. Check the file name, extension, and folder permissions."
    if "conversion failed" in lowered:
        return "FFmpeg failed while rendering the cleaned output. Try a simpler format like WAV and review the source media."
    return detail.strip() or "FFmpeg failed while exporting the cleaned output."


def verify_rendered_output(
    output_path: Path,
    *,
    ffprobe_path: str,
    expected_video: bool,
    expected_audio: bool,
    source_duration: float,
) -> MediaInfo:
    if not output_path.exists():
        raise RuntimeError("The export finished without creating an output file.")
    if output_path.stat().st_size <= 0:
        raise RuntimeError("The export file was created but is empty.")

    info = probe_media(output_path, ffprobe_path)
    if expected_audio and not info.has_audio:
        raise RuntimeError("The exported file does not contain a readable audio stream.")
    if expected_video and not info.has_video:
        raise RuntimeError("The repaired video export does not contain a readable video stream.")
    if expected_video and abs(info.duration - source_duration) > 1.5:
        raise RuntimeError("The repaired video duration does not match the source closely enough to trust the export.")
    if not expected_video and info.duration <= 0.1:
        raise RuntimeError("The cleaned audio export is too short to trust.")
    return info


def app_settings_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / APP_NAME / "settings.json"
    return Path.home() / f".{APP_NAME.lower()}" / "settings.json"


def load_app_settings() -> dict[str, str]:
    path = app_settings_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_app_settings(settings: dict[str, str]) -> None:
    path = app_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def suggested_output_filename(source_path: Path, *, mode: str, format_name: str) -> str:
    extension = format_name.lower() if mode == EXPORT_MODE_AUDIO else "mp4"
    return f"{source_path.stem}_glideaudio_cleaned.{extension}"


def next_available_output_path(path: Path) -> Path:
    if not path.exists():
        return path

    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


class GlideAudioApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        TkinterDnD._require(self)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(APP_NAME)
        self.geometry(WINDOW_SIZE)
        self.minsize(*MIN_WINDOW_SIZE)
        self.configure(fg_color=COLORS["bg_primary"])

        self.ffmpeg_path: Optional[str] = None
        self.ffprobe_path: Optional[str] = None

        self.media_path: Optional[Path] = None
        self.media_info: Optional[MediaInfo] = None
        self.diagnostics: Optional[AudioDiagnostics] = None
        self.analysis_samples = np.asarray([], dtype=np.float32)
        self.preview_original_samples = np.asarray([], dtype=np.float32)
        self.preview_cleaned_samples = np.asarray([], dtype=np.float32)

        self.source_pil_image: Optional[Image.Image] = None
        self.preview_original_pil_image: Optional[Image.Image] = None
        self.preview_cleaned_pil_image: Optional[Image.Image] = None
        self.preview_original_payload: Optional[tuple[np.ndarray, str, str]] = None
        self.preview_cleaned_payload: Optional[tuple[np.ndarray, str, str]] = None
        self.source_image: Optional[ctk.CTkImage] = None
        self.preview_original_image: Optional[ctk.CTkImage] = None
        self.preview_cleaned_image: Optional[ctk.CTkImage] = None

        self.preview_dir: Optional[Path] = None
        self.preview_original_wav: Optional[Path] = None
        self.preview_cleaned_wav: Optional[Path] = None
        self.preview_active_variant: Optional[str] = None
        self.preview_last_variant: Optional[str] = None
        self.preview_playback_state = "stopped"
        self.preview_loop_after_id: Optional[str] = None
        self.preview_is_stale = True
        self.suggested_preset_name: Optional[str] = None

        self.mode = "idle"
        self.active_process: Optional[subprocess.Popen] = None
        self.cancel_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None
        self.ui_queue: queue.SimpleQueue = queue.SimpleQueue()
        self.batch_queue: list[BatchQueueItem] = []
        self.batch_queue_index = 0

        self.app_settings = load_app_settings()
        default_output_dir = Path.home() / "Videos" / "GlideAudio Exports"
        saved_output_dir = self.app_settings.get("output_dir")
        self.output_dir = Path(saved_output_dir) if saved_output_dir else default_output_dir
        self.output_path: Optional[Path] = None

        self.source_status_var = ctk.StringVar(value="Start here: drop one audio or video file, or browse to begin.")
        self.source_meta_var = ctk.StringVar(value="GlideAudio will inspect the source, suggest a preset, and prepare a short compare loop.")
        self.audio_meta_var = ctk.StringVar(value="Single-file workflow first. Use batch only after the result sounds right.")
        self.source_preview_caption_var = ctk.StringVar(value="Load media to inspect waveform or poster frame.")
        self.preview_status_var = ctk.StringVar(value="GlideAudio will build a short original-vs-cleaned preview after analysis.")
        self.preview_transport_var = ctk.StringVar(value="Idle")
        self.preview_original_caption_var = ctk.StringVar(value="Original reference loop appears here after analysis.")
        self.preview_cleaned_caption_var = ctk.StringVar(value="Cleaned loop appears here after preview render.")
        self.suggested_preset_var = ctk.StringVar(value="Waiting for analysis.")
        self.preset_hint_var = ctk.StringVar(value="GlideAudio will recommend a simple starting preset after analysis.")
        self.batch_status_var = ctk.StringVar(value="Optional: queue extra files after you trust the single-file result.")
        self.export_status_var = ctk.StringVar(value="Step 3: choose where to save the result, then export the final cleaned file.")
        self.next_step_var = ctk.StringVar(value="Next: load one audio or video file. GlideAudio analyzes it automatically.")
        self.status_var = ctk.StringVar(value="Ready.")

        saved_preset = self.app_settings.get("preset")
        saved_preview_length = self.app_settings.get("preview_length")
        saved_export_mode = self.app_settings.get("export_mode")
        saved_format = self.app_settings.get("export_format")
        saved_target = self.app_settings.get("loudness_target")
        self.preset_var = ctk.StringVar(value=saved_preset if saved_preset in PRESET_VALUES else "Clean Voice")
        self.preview_length_var = ctk.StringVar(value=saved_preview_length if saved_preview_length in PREVIEW_LENGTHS else "10 sec")
        self.export_mode_var = ctk.StringVar(value=saved_export_mode if saved_export_mode in EXPORT_FORMATS else EXPORT_MODE_AUDIO)
        default_format = self.export_mode_var.get()
        self.export_format_var = ctk.StringVar(
            value=saved_format if saved_format in EXPORT_FORMATS.get(default_format, []) else EXPORT_FORMATS[default_format][0]
        )
        self.loudness_target_var = ctk.StringVar(
            value=saved_target if saved_target in LOUDNESS_TARGETS else "YouTube / Social (-14 LUFS)"
        )
        self.preview_start_var = ctk.DoubleVar(value=0.0)

        self.slider_vars = {key: ctk.DoubleVar(value=PRESET_VALUES["Clean Voice"][key]) for key, _ in SLIDER_KEYS}
        self.slider_value_labels: dict[str, ctk.CTkLabel] = {}

        self.metric_vars = {
            "peak": ctk.StringVar(value="-- dBFS"),
            "loudness": ctk.StringVar(value="-- LUFS"),
            "noise": ctk.StringVar(value="-- dBFS"),
            "clipping": ctk.StringVar(value="--"),
            "speech": ctk.StringVar(value="--"),
        }

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(40, self._drain_ui_events)
        self._apply_preset(self.preset_var.get())
        self._set_source_placeholder()
        self._set_preview_placeholders()
        self._refresh_action_states()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)

        header = ctk.CTkFrame(self, fg_color=COLORS["bg_primary"])
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(20, 12))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text=APP_NAME,
            font=ui_font(32, "bold"),
            text_color=COLORS["text_primary"],
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Repair spoken audio fast, compare the fix, and export clean audio or video.",
            font=ui_font(14),
            text_color=COLORS["text_secondary"],
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        next_step_frame = ctk.CTkFrame(
            header,
            fg_color=COLORS["bg_tertiary"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        next_step_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        next_step_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            next_step_frame,
            text="Next",
            font=ui_font(12, "bold"),
            text_color=COLORS["primary_soft"],
        ).grid(row=0, column=0, sticky="w", padx=(14, 10), pady=10)
        ctk.CTkLabel(
            next_step_frame,
            textvariable=self.next_step_var,
            font=ui_font(12),
            text_color=COLORS["text_primary"],
            justify="left",
            wraplength=880,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=10)
        ctk.CTkLabel(
            header,
            text=f"v{APP_MARKETING_VERSION}",
            font=mono_font(12),
            text_color=COLORS["text_muted"],
        ).grid(row=0, column=1, sticky="e")

        content_scroller = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
        )
        content_scroller.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 18))
        content_scroller.grid_columnconfigure(0, weight=1)

        content = ctk.CTkFrame(content_scroller, fg_color="transparent")
        content.grid(row=0, column=0, sticky="ew")
        content.grid_columnconfigure(0, weight=0)
        content.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(content, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 18))

        right = ctk.CTkFrame(content, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)

        self.source_card = self._build_card(left, "1. Load Source")
        self.source_card.pack(fill="x", pady=(0, 14))

        self.analysis_card = self._build_card(left, "Checks")
        self.analysis_card.pack(fill="x", pady=(0, 14))

        self.cleanup_card = self._build_card(left, "Tune Cleanup")
        self.cleanup_card.pack(fill="x")

        self.preview_card = self._build_card(right, "2. Preview Before / After")
        self.preview_card.pack(fill="x", pady=(0, 14))

        self.export_card = self._build_card(right, "3. Export Final File")
        self.export_card.pack(fill="x", pady=(0, 14))

        self.batch_card = self._build_card(right, "Batch Queue (Optional)")
        self.batch_card.pack(fill="x")

        self.log_card = self._build_card(self, "Log")
        self.log_card.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 22))

        self._build_source_section()
        self._build_analysis_section()
        self._build_cleanup_section()
        self._build_preview_section()
        self._build_export_section()
        self._build_batch_section()
        self._build_log_section()

    def _build_card(self, parent, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=COLORS["surface"], corner_radius=24, border_width=1, border_color=COLORS["border"])
        ctk.CTkLabel(
            card,
            text=title,
            font=ui_font(18, "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", padx=18, pady=(16, 10))
        return card

    def _build_source_section(self) -> None:
        controls = ctk.CTkFrame(self.source_card, fg_color="transparent")
        controls.pack(fill="x", padx=18, pady=(0, 12))
        controls.grid_columnconfigure(0, weight=1)

        self.browse_button = ctk.CTkButton(
            controls,
            text="Browse Source",
            command=self._select_source,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            font=ui_font(13, "bold"),
            height=38,
            corner_radius=14,
        )
        self.browse_button.grid(row=0, column=0, sticky="ew")

        self.analyze_button = ctk.CTkButton(
            controls,
            text="Analyze Again",
            command=self._start_analysis,
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(13, "bold"),
            height=38,
            corner_radius=14,
        )
        self.analyze_button.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        ctk.CTkLabel(
            self.source_card,
            text="Browse or drop one file. GlideAudio analyzes it automatically so you can go straight into listening and export.",
            font=ui_font(12),
            text_color=COLORS["text_secondary"],
            justify="left",
            wraplength=430,
        ).pack(fill="x", padx=18, pady=(0, 12))

        self.source_drop_frame = ctk.CTkFrame(
            self.source_card,
            fg_color=COLORS["bg_tertiary"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
            height=110,
        )
        self.source_drop_frame.pack(fill="x", padx=18, pady=(0, 12))
        self.source_drop_frame.pack_propagate(False)
        self.source_drop_label = ctk.CTkLabel(
            self.source_drop_frame,
            textvariable=self.source_status_var,
            font=ui_font(14),
            text_color=COLORS["text_secondary"],
            justify="left",
            wraplength=380,
        )
        self.source_drop_label.pack(fill="both", expand=True, padx=18, pady=14)

        for widget in (self.source_drop_frame, self.source_drop_label):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
            widget.dnd_bind("<<DragEnter>>", lambda _event: COPY)

        self.source_preview_frame = ctk.CTkFrame(
            self.source_card,
            fg_color=COLORS["bg_tertiary"],
            corner_radius=20,
            border_width=1,
            border_color=COLORS["border"],
        )
        self.source_preview_frame.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(
            self.source_preview_frame,
            text="Source Overview",
            font=ui_font(13, "bold"),
            text_color=COLORS["primary_soft"],
        ).pack(anchor="w", padx=16, pady=(14, 8))
        self.source_preview_label = ctk.CTkLabel(
            self.source_preview_frame,
            text="",
            fg_color=COLORS["bg_secondary"],
            corner_radius=16,
            anchor="center",
        )
        self.source_preview_label.pack(fill="x", padx=14, pady=(0, 10))
        ctk.CTkLabel(
            self.source_preview_frame,
            textvariable=self.source_preview_caption_var,
            font=ui_font(12),
            text_color=COLORS["text_primary"],
            justify="left",
            wraplength=430,
        ).pack(fill="x", padx=16, pady=(0, 14))
        self.source_card.bind("<Configure>", lambda _event: self._refresh_source_image())

        ctk.CTkLabel(
            self.source_card,
            textvariable=self.source_meta_var,
            font=ui_font(13),
            text_color=COLORS["text_primary"],
            justify="left",
            wraplength=450,
        ).pack(fill="x", padx=18)
        ctk.CTkLabel(
            self.source_card,
            textvariable=self.audio_meta_var,
            font=mono_font(12),
            text_color=COLORS["text_secondary"],
            justify="left",
            wraplength=450,
        ).pack(fill="x", padx=18, pady=(6, 18))

    def _build_analysis_section(self) -> None:
        grid = ctk.CTkFrame(self.analysis_card, fg_color="transparent")
        grid.pack(fill="x", padx=18, pady=(0, 18))
        for column in range(2):
            grid.grid_columnconfigure(column, weight=1)

        self._build_metric_tile(grid, 0, 0, "Peak", self.metric_vars["peak"])
        self._build_metric_tile(grid, 0, 1, "Average Loudness", self.metric_vars["loudness"])
        self._build_metric_tile(grid, 1, 0, "Noise Floor", self.metric_vars["noise"])
        self._build_metric_tile(grid, 1, 1, "Clipping Risk", self.metric_vars["clipping"])
        self._build_metric_tile(grid, 2, 0, "Speech Presence", self.metric_vars["speech"], column_span=2)

    def _build_metric_tile(self, parent, row: int, column: int, label: str, variable, column_span: int = 1) -> None:
        tile = ctk.CTkFrame(parent, fg_color=COLORS["bg_tertiary"], corner_radius=18, border_width=1, border_color=COLORS["border"])
        tile.grid(row=row, column=column, columnspan=column_span, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(tile, text=label, font=ui_font(12, "bold"), text_color=COLORS["text_secondary"]).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(tile, textvariable=variable, font=ui_font(18, "bold"), text_color=COLORS["text_primary"]).pack(anchor="w", padx=14, pady=(0, 12))

    def _build_cleanup_section(self) -> None:
        recommendation = ctk.CTkFrame(
            self.cleanup_card,
            fg_color=COLORS["bg_tertiary"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        recommendation.pack(fill="x", padx=18, pady=(0, 12))
        recommendation.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            recommendation,
            text="Recommended Start",
            font=ui_font(12, "bold"),
            text_color=COLORS["primary_soft"],
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            recommendation,
            textvariable=self.suggested_preset_var,
            font=ui_font(16, "bold"),
            text_color=COLORS["text_primary"],
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 12))
        self.reapply_suggested_button = ctk.CTkButton(
            recommendation,
            text="Use Suggestion",
            command=self._apply_suggested_preset,
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(12, "bold"),
            height=32,
            corner_radius=12,
            width=120,
        )
        self.reapply_suggested_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=14, pady=12)

        preset_row = ctk.CTkFrame(self.cleanup_card, fg_color="transparent")
        preset_row.pack(fill="x", padx=18, pady=(0, 14))
        preset_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(preset_row, text="Current Preset", font=ui_font(13, "bold"), text_color=COLORS["text_secondary"]).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.preset_menu = ctk.CTkOptionMenu(
            preset_row,
            variable=self.preset_var,
            values=list(PRESET_VALUES.keys()),
            command=self._apply_preset,
            fg_color=COLORS["bg_tertiary"],
            button_color=COLORS["primary"],
            button_hover_color=COLORS["primary_hover"],
            text_color=COLORS["text_primary"],
            dropdown_fg_color=COLORS["surface_alt"],
        )
        self.preset_menu.grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(
            self.cleanup_card,
            textvariable=self.preset_hint_var,
            font=ui_font(12),
            text_color=COLORS["text_secondary"],
            justify="left",
            wraplength=430,
        ).pack(fill="x", padx=18, pady=(0, 10))

        sliders = ctk.CTkFrame(self.cleanup_card, fg_color="transparent")
        sliders.pack(fill="x", padx=18, pady=(0, 18))

        for key, label in SLIDER_KEYS:
            row = ctk.CTkFrame(sliders, fg_color="transparent")
            row.pack(fill="x", pady=6)
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(row, text=label, font=ui_font(13), text_color=COLORS["text_primary"]).grid(row=0, column=0, sticky="w", padx=(0, 10))
            slider = ctk.CTkSlider(
                row,
                from_=0.0,
                to=1.0,
                variable=self.slider_vars[key],
                command=lambda _value, slider_key=key: self._on_slider_changed(slider_key),
                progress_color=COLORS["primary"],
                button_color=COLORS["primary_soft"],
                button_hover_color=COLORS["primary_hover"],
                fg_color=COLORS["track"],
            )
            slider.grid(row=0, column=1, sticky="ew", padx=(0, 12))
            value_label = ctk.CTkLabel(row, text="0%", font=mono_font(12), text_color=COLORS["text_secondary"])
            value_label.grid(row=0, column=2, sticky="e")
            self.slider_value_labels[key] = value_label

    def _build_preview_section(self) -> None:
        controls = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        controls.pack(fill="x", padx=18, pady=(0, 12))
        controls.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(controls, text="Loop Start", font=ui_font(13, "bold"), text_color=COLORS["text_secondary"]).grid(row=0, column=0, sticky="w")
        self.preview_slider = ctk.CTkSlider(
            controls,
            from_=0.0,
            to=1.0,
            variable=self.preview_start_var,
            command=self._on_preview_slider_changed,
            progress_color=COLORS["primary"],
            button_color=COLORS["primary_soft"],
            button_hover_color=COLORS["primary_hover"],
            fg_color=COLORS["track"],
        )
        self.preview_slider.grid(row=0, column=1, sticky="ew", padx=(12, 12))
        self.preview_time_label = ctk.CTkLabel(controls, text="00:00.00", font=mono_font(12), text_color=COLORS["text_secondary"])
        self.preview_time_label.grid(row=0, column=2, sticky="e")

        second_row = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        second_row.pack(fill="x", padx=18, pady=(0, 12))

        ctk.CTkLabel(second_row, text="Loop Length", font=ui_font(13, "bold"), text_color=COLORS["text_secondary"]).pack(side="left")
        self.preview_length_menu = ctk.CTkOptionMenu(
            second_row,
            variable=self.preview_length_var,
            values=PREVIEW_LENGTHS,
            command=lambda _value: self._on_preview_length_changed(),
            fg_color=COLORS["bg_tertiary"],
            button_color=COLORS["primary"],
            button_hover_color=COLORS["primary_hover"],
            text_color=COLORS["text_primary"],
            dropdown_fg_color=COLORS["surface_alt"],
            width=120,
        )
        self.preview_length_menu.pack(side="left", padx=(10, 18))

        self.refresh_preview_button = ctk.CTkButton(
            second_row,
            text="Build Preview",
            command=self._start_preview_generation,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            font=ui_font(13, "bold"),
            height=36,
            corner_radius=14,
        )
        self.refresh_preview_button.pack(side="left")

        transport_state = ctk.CTkLabel(
            second_row,
            textvariable=self.preview_transport_var,
            font=mono_font(12, "bold"),
            text_color=COLORS["primary_soft"],
            fg_color=COLORS["bg_tertiary"],
            corner_radius=12,
            width=124,
            height=34,
        )
        transport_state.pack(side="right")

        self.reset_preview_button = ctk.CTkButton(
            second_row,
            text="Reset",
            command=self._reset_preview_audio,
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(13, "bold"),
            height=36,
            corner_radius=14,
            width=88,
        )
        self.reset_preview_button.pack(side="right", padx=(0, 10))

        self.stop_preview_button = ctk.CTkButton(
            second_row,
            text="Stop",
            command=lambda: self._stop_preview_audio(announce=True),
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(13, "bold"),
            height=36,
            corner_radius=14,
            width=88,
        )
        self.stop_preview_button.pack(side="right", padx=(0, 10))

        ctk.CTkLabel(
            self.preview_card,
            textvariable=self.preview_status_var,
            font=ui_font(13),
            text_color=COLORS["text_secondary"],
            justify="left",
            wraplength=760,
        ).pack(fill="x", padx=18, pady=(0, 12))

        images = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        images.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        images.grid_columnconfigure(0, weight=1)
        images.grid_columnconfigure(1, weight=1)
        images.grid_rowconfigure(0, weight=1)
        self.preview_images_frame = images

        self.preview_original_frame = ctk.CTkFrame(
            images,
            fg_color=COLORS["bg_tertiary"],
            corner_radius=20,
            border_width=1,
            border_color=COLORS["border"],
        )
        self.preview_original_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.preview_original_frame.grid_columnconfigure(0, weight=1)
        original_header = ctk.CTkFrame(self.preview_original_frame, fg_color="transparent")
        original_header.pack(fill="x", padx=16, pady=(14, 8))
        ctk.CTkLabel(
            original_header,
            text="Original",
            font=ui_font(13, "bold"),
            text_color=COLORS["primary_soft"],
        ).pack(side="left")
        self.preview_original_toggle_button = ctk.CTkButton(
            original_header,
            text="Play",
            width=86,
            height=30,
            corner_radius=12,
            command=lambda: self._toggle_preview_playback("original"),
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(12, "bold"),
        )
        self.preview_original_toggle_button.pack(side="right")
        self.preview_original_label = ctk.CTkLabel(
            self.preview_original_frame,
            text="",
            fg_color=COLORS["bg_secondary"],
            corner_radius=16,
            anchor="center",
        )
        self.preview_original_label.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(
            self.preview_original_frame,
            textvariable=self.preview_original_caption_var,
            font=ui_font(12),
            text_color=COLORS["text_primary"],
            justify="left",
            wraplength=330,
        ).pack(fill="x", padx=16, pady=(0, 14))

        self.preview_cleaned_frame = ctk.CTkFrame(
            images,
            fg_color=COLORS["bg_tertiary"],
            corner_radius=20,
            border_width=1,
            border_color=COLORS["border"],
        )
        self.preview_cleaned_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.preview_cleaned_frame.grid_columnconfigure(0, weight=1)
        cleaned_header = ctk.CTkFrame(self.preview_cleaned_frame, fg_color="transparent")
        cleaned_header.pack(fill="x", padx=16, pady=(14, 8))
        ctk.CTkLabel(
            cleaned_header,
            text="Cleaned",
            font=ui_font(13, "bold"),
            text_color=COLORS["primary_soft"],
        ).pack(side="left")
        self.preview_cleaned_toggle_button = ctk.CTkButton(
            cleaned_header,
            text="Play",
            width=86,
            height=30,
            corner_radius=12,
            command=lambda: self._toggle_preview_playback("cleaned"),
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(12, "bold"),
        )
        self.preview_cleaned_toggle_button.pack(side="right")
        self.preview_cleaned_label = ctk.CTkLabel(
            self.preview_cleaned_frame,
            text="",
            fg_color=COLORS["bg_secondary"],
            corner_radius=16,
            anchor="center",
        )
        self.preview_cleaned_label.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(
            self.preview_cleaned_frame,
            textvariable=self.preview_cleaned_caption_var,
            font=ui_font(12),
            text_color=COLORS["text_primary"],
            justify="left",
            wraplength=330,
        ).pack(fill="x", padx=16, pady=(0, 14))
        self.preview_images_frame.bind("<Configure>", lambda _event: self._refresh_preview_images())
        self._update_preview_transport_buttons()

    def _build_export_section(self) -> None:
        grid = ctk.CTkFrame(self.export_card, fg_color="transparent")
        grid.pack(fill="x", padx=18, pady=(0, 14))
        grid.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(grid, text="Mode", font=ui_font(13, "bold"), text_color=COLORS["text_secondary"]).grid(row=0, column=0, sticky="w", pady=4)
        self.export_mode_menu = ctk.CTkOptionMenu(
            grid,
            variable=self.export_mode_var,
            values=[EXPORT_MODE_AUDIO, EXPORT_MODE_VIDEO],
            command=lambda _value: self._on_export_mode_changed(),
            fg_color=COLORS["bg_tertiary"],
            button_color=COLORS["primary"],
            button_hover_color=COLORS["primary_hover"],
            text_color=COLORS["text_primary"],
            dropdown_fg_color=COLORS["surface_alt"],
        )
        self.export_mode_menu.grid(row=0, column=1, sticky="ew", pady=4)

        ctk.CTkLabel(grid, text="Format", font=ui_font(13, "bold"), text_color=COLORS["text_secondary"]).grid(row=1, column=0, sticky="w", pady=4)
        self.export_format_menu = ctk.CTkOptionMenu(
            grid,
            variable=self.export_format_var,
            values=EXPORT_FORMATS[EXPORT_MODE_AUDIO],
            command=lambda _value: self._on_export_format_changed(),
            fg_color=COLORS["bg_tertiary"],
            button_color=COLORS["primary"],
            button_hover_color=COLORS["primary_hover"],
            text_color=COLORS["text_primary"],
            dropdown_fg_color=COLORS["surface_alt"],
        )
        self.export_format_menu.grid(row=1, column=1, sticky="ew", pady=4)

        ctk.CTkLabel(grid, text="Loudness Target", font=ui_font(13, "bold"), text_color=COLORS["text_secondary"]).grid(row=2, column=0, sticky="w", pady=4)
        self.loudness_target_menu = ctk.CTkOptionMenu(
            grid,
            variable=self.loudness_target_var,
            values=list(LOUDNESS_TARGETS.keys()),
            command=lambda _value: self._on_loudness_target_changed(),
            fg_color=COLORS["bg_tertiary"],
            button_color=COLORS["primary"],
            button_hover_color=COLORS["primary_hover"],
            text_color=COLORS["text_primary"],
            dropdown_fg_color=COLORS["surface_alt"],
        )
        self.loudness_target_menu.grid(row=2, column=1, sticky="ew", pady=4)

        ctk.CTkLabel(
            self.export_card,
            textvariable=self.export_status_var,
            font=ui_font(13),
            text_color=COLORS["text_secondary"],
            justify="left",
            wraplength=760,
        ).pack(fill="x", padx=18, pady=(0, 12))

        self.output_label = ctk.CTkLabel(
            self.export_card,
            text=str(self.output_dir),
            font=mono_font(12),
            text_color=COLORS["text_primary"],
            justify="left",
            wraplength=760,
        )
        self.output_label.pack(fill="x", padx=18)

        button_row = ctk.CTkFrame(self.export_card, fg_color="transparent")
        button_row.pack(fill="x", padx=18, pady=(12, 10))

        self.output_button = ctk.CTkButton(
            button_row,
            text="Choose Save Location",
            command=self._choose_output_path,
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(13, "bold"),
            height=38,
            corner_radius=14,
        )
        self.output_button.pack(side="left")

        self.export_button = ctk.CTkButton(
            button_row,
            text="Export Final File",
            command=self._start_export,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            font=ui_font(13, "bold"),
            height=38,
            corner_radius=14,
        )
        self.export_button.pack(side="left", padx=(10, 10))

        self.stop_export_button = ctk.CTkButton(
            button_row,
            text="Stop",
            command=self._stop_export,
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(13, "bold"),
            height=38,
            corner_radius=14,
        )
        self.stop_export_button.pack(side="left")

        self.progress = ctk.CTkProgressBar(self.export_card, progress_color=COLORS["primary"], fg_color=COLORS["track"])
        self.progress.pack(fill="x", padx=18, pady=(0, 18))
        self.progress.set(0.0)

    def _build_batch_section(self) -> None:
        ctk.CTkLabel(
            self.batch_card,
            text="Optional after the single-file result sounds right. Batch exports reuse the current cleanup and export settings.",
            font=ui_font(12),
            text_color=COLORS["text_secondary"],
            justify="left",
            wraplength=760,
        ).pack(fill="x", padx=18, pady=(0, 12))

        controls_top = ctk.CTkFrame(self.batch_card, fg_color="transparent")
        controls_top.pack(fill="x", padx=18, pady=(0, 10))

        self.batch_add_button = ctk.CTkButton(
            controls_top,
            text="Add Files",
            command=self._add_batch_files,
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(13, "bold"),
            height=36,
            corner_radius=14,
            width=118,
        )
        self.batch_add_button.pack(side="left")

        self.batch_queue_current_button = ctk.CTkButton(
            controls_top,
            text="Queue Current",
            command=self._queue_current_source,
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(13, "bold"),
            height=36,
            corner_radius=14,
            width=126,
        )
        self.batch_queue_current_button.pack(side="left", padx=(10, 0))

        self.batch_load_button = ctk.CTkButton(
            controls_top,
            text="Load Selected",
            command=self._load_selected_batch_item,
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(13, "bold"),
            height=36,
            corner_radius=14,
            width=126,
        )
        self.batch_load_button.pack(side="right")

        controls_bottom = ctk.CTkFrame(self.batch_card, fg_color="transparent")
        controls_bottom.pack(fill="x", padx=18, pady=(0, 10))

        self.batch_remove_button = ctk.CTkButton(
            controls_bottom,
            text="Remove",
            command=self._remove_selected_batch_items,
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(13, "bold"),
            height=36,
            corner_radius=14,
            width=96,
        )
        self.batch_remove_button.pack(side="left")

        self.batch_clear_button = ctk.CTkButton(
            controls_bottom,
            text="Clear",
            command=self._clear_batch_queue,
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(13, "bold"),
            height=36,
            corner_radius=14,
            width=88,
        )
        self.batch_clear_button.pack(side="left", padx=(10, 0))

        self.batch_stop_button = ctk.CTkButton(
            controls_bottom,
            text="Stop Queue",
            command=self._stop_batch_queue,
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(13, "bold"),
            height=36,
            corner_radius=14,
            width=112,
        )
        self.batch_stop_button.pack(side="right")

        self.batch_run_button = ctk.CTkButton(
            controls_bottom,
            text="Run Queue",
            command=self._start_batch_queue,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            font=ui_font(13, "bold"),
            height=36,
            corner_radius=14,
            width=112,
        )
        self.batch_run_button.pack(side="right", padx=(0, 10))

        batch_table_frame = ctk.CTkFrame(
            self.batch_card,
            fg_color=COLORS["bg_tertiary"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        batch_table_frame.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        style = ttk.Style(self)
        try:
            style.theme_use("default")
        except tk.TclError:
            pass
        style.configure(
            "GlideAudio.Treeview",
            background=COLORS["bg_tertiary"],
            fieldbackground=COLORS["bg_tertiary"],
            foreground=COLORS["text_primary"],
            borderwidth=0,
            rowheight=30,
            font=mono_font(11),
        )
        style.configure(
            "GlideAudio.Treeview.Heading",
            background=COLORS["surface_alt"],
            foreground=COLORS["text_secondary"],
            relief="flat",
            font=ui_font(12, "bold"),
        )
        style.map(
            "GlideAudio.Treeview",
            background=[("selected", COLORS["primary"])],
            foreground=[("selected", COLORS["bg_primary"])],
        )

        tree_container = tk.Frame(batch_table_frame, background=COLORS["bg_tertiary"])
        tree_container.pack(fill="both", expand=True, padx=12, pady=12)

        self.batch_tree = ttk.Treeview(
            tree_container,
            style="GlideAudio.Treeview",
            columns=("status", "source", "detail"),
            show="headings",
            selectmode="extended",
            height=7,
        )
        self.batch_tree.heading("status", text="Status")
        self.batch_tree.heading("source", text="Source")
        self.batch_tree.heading("detail", text="Detail")
        self.batch_tree.column("status", width=110, anchor="w", stretch=False)
        self.batch_tree.column("source", width=250, anchor="w")
        self.batch_tree.column("detail", width=360, anchor="w")
        self.batch_tree.pack(side="left", fill="both", expand=True)
        self.batch_tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_action_states())

        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.batch_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.batch_tree.configure(yscrollcommand=scrollbar.set)

        ctk.CTkLabel(
            self.batch_card,
            textvariable=self.batch_status_var,
            font=ui_font(13),
            text_color=COLORS["text_secondary"],
            justify="left",
            wraplength=760,
        ).pack(fill="x", padx=18, pady=(0, 18))

    def _build_log_section(self) -> None:
        self.log_box = ctk.CTkTextbox(
            self.log_card,
            height=170,
            fg_color=COLORS["bg_tertiary"],
            text_color=COLORS["text_primary"],
            border_width=1,
            border_color=COLORS["border"],
            font=mono_font(12),
            wrap="word",
        )
        self.log_box.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self.log_box.insert("end", "GlideAudio ready.\n")
        self.log_box.configure(state="disabled")

        footer = ctk.CTkFrame(self.log_card, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(0, 16))
        ctk.CTkLabel(footer, textvariable=self.status_var, font=ui_font(13), text_color=COLORS["text_secondary"]).pack(side="left")
        ctk.CTkButton(
            footer,
            text="Clear Log",
            command=self._clear_log,
            fg_color="transparent",
            hover_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
            font=ui_font(12, "bold"),
            height=34,
            corner_radius=12,
            width=100,
        ).pack(side="right")

    def _get_ffmpeg_path(self) -> str:
        if self.ffmpeg_path is None:
            self.ffmpeg_path = resolve_binary("ffmpeg")
        return self.ffmpeg_path

    def _get_ffprobe_path(self) -> str:
        if self.ffprobe_path is None:
            self.ffprobe_path = resolve_binary("ffprobe")
        return self.ffprobe_path

    def _default_output_path(self, source_path: Path, *, mode: str, format_name: str, allow_existing: bool) -> Path:
        candidate = self.output_dir / suggested_output_filename(source_path, mode=mode, format_name=format_name)
        return candidate if allow_existing else next_available_output_path(candidate)

    def _batch_item_values(self, item: BatchQueueItem) -> tuple[str, str, str]:
        detail = item.detail
        if item.output_path is not None:
            detail = f"{detail} | {item.output_path.name}"
        return (item.status, compact_path_text(item.path), detail)

    def _upsert_batch_item(self, item: BatchQueueItem) -> None:
        values = self._batch_item_values(item)
        if self.batch_tree.exists(item.item_id):
            self.batch_tree.item(item.item_id, values=values)
        else:
            self.batch_tree.insert("", "end", iid=item.item_id, values=values)

    def _selected_batch_item_ids(self) -> list[str]:
        return list(self.batch_tree.selection()) if hasattr(self, "batch_tree") else []

    def _update_batch_status(self, message: str) -> None:
        self.batch_status_var.set(message)

    def _enqueue_paths(self, paths: list[Path]) -> None:
        if not paths:
            return

        existing = {
            item.path.resolve(strict=False) if item.path.exists() else item.path
            for item in self.batch_queue
        }
        added = 0
        for raw_path in paths:
            path = Path(raw_path)
            if not path.exists() or not path.is_file():
                self._log(f"Skipped queue add, file missing: {path}")
                continue
            normalized = path.resolve(strict=False)
            if normalized in existing:
                self._log(f"Skipped queue add, already queued: {path}")
                continue
            self.batch_queue_index += 1
            item = BatchQueueItem(item_id=f"batch-{self.batch_queue_index}", path=normalized)
            self.batch_queue.append(item)
            self._upsert_batch_item(item)
            existing.add(normalized)
            added += 1

        if added:
            self._update_batch_status(f"{len(self.batch_queue)} file(s) queued. Batch exports reuse the current cleanup and export settings.")
        else:
            self._update_batch_status("No new files were added to the queue.")
        self._refresh_action_states()

    def _add_batch_files(self) -> None:
        if self.mode != "idle":
            return
        chosen = filedialog.askopenfilenames(
            title="Add Files to GlideAudio Batch Queue",
            filetypes=[("Media Files", MEDIA_FILE_TYPES), ("All Files", "*.*")],
        )
        if chosen:
            self._enqueue_paths([Path(path) for path in chosen])

    def _queue_current_source(self) -> None:
        if self.mode != "idle" or self.media_path is None:
            return
        self._enqueue_paths([self.media_path])

    def _load_selected_batch_item(self) -> None:
        if self.mode != "idle":
            return
        selection = self._selected_batch_item_ids()
        if not selection:
            return
        item = next((queued for queued in self.batch_queue if queued.item_id == selection[0]), None)
        if item is not None:
            self._load_source(item.path)

    def _remove_selected_batch_items(self) -> None:
        if self.mode != "idle":
            return
        selection = set(self._selected_batch_item_ids())
        if not selection:
            return
        self.batch_queue = [item for item in self.batch_queue if item.item_id not in selection]
        for item_id in selection:
            if self.batch_tree.exists(item_id):
                self.batch_tree.delete(item_id)
        if self.batch_queue:
            self._update_batch_status(f"{len(self.batch_queue)} file(s) remain queued.")
        else:
            self._update_batch_status("Queue idle. Add files to batch export.")
        self._refresh_action_states()

    def _clear_batch_queue(self) -> None:
        if self.mode != "idle":
            return
        self.batch_queue.clear()
        for item_id in self.batch_tree.get_children():
            self.batch_tree.delete(item_id)
        self._update_batch_status("Queue idle. Add files to batch export.")
        self._refresh_action_states()

    def _select_source(self) -> None:
        if self.mode != "idle":
            return
        chosen = filedialog.askopenfilename(
            title="Select Audio or Video Source",
            filetypes=[("Media Files", MEDIA_FILE_TYPES), ("All Files", "*.*")],
        )
        if chosen:
            self._load_source(Path(chosen))

    def _on_drop(self, event) -> str:
        if self.mode != "idle":
            return COPY
        paths = parse_drop_paths(self, event.data)
        if not paths:
            return COPY
        self._load_source(paths[0])
        return COPY

    def _load_source(self, path: Path) -> None:
        if not path.exists():
            messagebox.showerror(APP_NAME, f"File not found:\n{path}")
            return
        self._stop_preview_audio()
        self._cleanup_preview_files()
        self.media_path = path
        self.media_info = None
        self.diagnostics = None
        self.analysis_samples = np.asarray([], dtype=np.float32)
        self.preview_original_samples = np.asarray([], dtype=np.float32)
        self.preview_cleaned_samples = np.asarray([], dtype=np.float32)
        self.output_path = None
        self.suggested_preset_name = None
        self.suggested_preset_var.set("Inspecting the source...")
        self.output_label.configure(text=str(self.output_dir))
        self.source_status_var.set(f"Loading {shorten_middle(path.name, 44)} ...")
        self.source_meta_var.set("Inspecting file and audio stream.")
        self.audio_meta_var.set(str(path))
        self.preview_is_stale = True
        self._set_preview_feedback("Analyzing source before preview generation.", "Analyzing")
        self.preset_hint_var.set("Inspecting the source to recommend the simplest good starting point.")
        self._set_next_step("GlideAudio is inspecting the source and preparing a recommended preview.")
        self.export_status_var.set("Step 3: after the preview sounds right, choose where to save the final cleaned file.")
        self._set_source_placeholder()
        self._set_preview_placeholders()
        self._start_analysis()

    def _start_analysis(self) -> None:
        if self.media_path is None or self.mode != "idle":
            return

        try:
            ffmpeg_path = self._get_ffmpeg_path()
            ffprobe_path = self._get_ffprobe_path()
        except FileNotFoundError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return

        path = self.media_path
        self._set_mode("analysis")
        self._set_status("Analyzing source...")
        self._log(f"Selected source: {path}")
        self._log(f"Using ffmpeg: {ffmpeg_path}")
        self._log(f"Using ffprobe: {ffprobe_path}")

        def worker() -> None:
            try:
                info = probe_media(path, ffprobe_path)
                if not info.has_audio:
                    raise RuntimeError("The selected file has no audio stream to clean.")
                analysis_window = min(info.duration, ANALYSIS_MAX_SECONDS)
                analysis_sample_rate = min(max(info.sample_rate or ANALYSIS_SAMPLE_RATE, ANALYSIS_SAMPLE_RATE), 48000)
                samples = decode_audio_samples(
                    path,
                    ffmpeg_path,
                    duration=analysis_window,
                    sample_rate=analysis_sample_rate,
                    channels=1,
                )
                loudness = loudnorm_probe(path, ffmpeg_path, max_seconds=analysis_window)
                peak_db = peak_volume_probe(path, ffmpeg_path, max_seconds=analysis_window)
                diagnostics = analyze_audio_samples(
                    samples,
                    analysis_sample_rate,
                    average_lufs=loudness,
                    peak_dbfs=peak_db,
                )
                thumbnail_time = clamp(info.duration * 0.25, 0.0, max(0.0, info.duration - 0.1))
                image = build_source_preview_image(
                    info,
                    ffmpeg_path=ffmpeg_path,
                    preview_samples=samples,
                    thumbnail_time=thumbnail_time,
                )
                self._post_ui(lambda: self._complete_analysis(info, diagnostics, samples, image))
            except Exception as exc:
                self._post_ui(lambda error_text=str(exc), trace_text=traceback.format_exc(): self._fail_task(error_text, trace_text))

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def _complete_analysis(self, info: MediaInfo, diagnostics: AudioDiagnostics, samples: np.ndarray, image: Image.Image) -> None:
        self.media_info = info
        self.diagnostics = diagnostics
        self.analysis_samples = samples
        self.source_pil_image = image
        self.source_preview_caption_var.set(f"{shorten_middle(info.path.name, 42)} | {format_seconds(info.duration)}")
        self._refresh_source_image()

        preview_length = min(parse_preview_length(self.preview_length_var.get()), max(MIN_PREVIEW_SECONDS, info.duration))
        max_start = max(0.0, info.duration - preview_length)
        preview_start = clamp(info.duration * 0.2, 0.0, max_start)
        self.preview_start_var.set(preview_start)
        self.preview_slider.configure(from_=0.0, to=max(max_start, 1e-3), number_of_steps=max(1, int(max(max_start, 0.0) * 4) + 1))
        self.preview_time_label.configure(text=format_seconds(preview_start))

        self.source_status_var.set(shorten_middle(info.path.name, 56))
        self.source_meta_var.set(
            f"{audio_mode_description(info)} | Duration {format_seconds(info.duration)} | "
            f"Audio codec {info.audio_codec}"
        )
        self.audio_meta_var.set(
            f"Sample rate {info.sample_rate or 'unknown'} Hz | "
            f"Channels {info.channels or 'unknown'} | "
            f"{'Video codec ' + info.video_codec if info.has_video else 'Audio-only workflow'}"
        )

        self.metric_vars["peak"].set(f"{diagnostics.peak_dbfs:.1f} dBFS")
        self.metric_vars["loudness"].set(f"{diagnostics.average_lufs:.1f} LUFS")
        self.metric_vars["noise"].set(f"{diagnostics.noise_floor_dbfs:.1f} dBFS")
        clip_text = diagnostics.clipping_risk
        if diagnostics.clip_events:
            clip_text += f" ({diagnostics.clip_events} clips)"
        self.metric_vars["clipping"].set(clip_text)
        self.metric_vars["speech"].set(f"{diagnostics.speech_presence} ({int(round(diagnostics.speech_score * 100))}%)")

        suggested_preset, suggestion_reason = suggest_cleanup_preset(info, diagnostics)
        self.suggested_preset_name = suggested_preset
        self.suggested_preset_var.set(suggested_preset)
        self._apply_preset(suggested_preset)
        self.preset_hint_var.set(
            f"Why this start works: {suggestion_reason}. Leave the sliders here unless something still sounds off."
        )

        export_modes = [EXPORT_MODE_AUDIO, EXPORT_MODE_VIDEO] if info.has_video else [EXPORT_MODE_AUDIO]
        self.export_mode_menu.configure(values=export_modes)
        if self.export_mode_var.get() not in export_modes:
            self.export_mode_var.set(export_modes[0])
        self._on_export_mode_changed()

        self._set_mode("idle")
        self._set_status("Analysis ready.")
        self._set_next_step("GlideAudio is building a quick compare loop. When it finishes, listen to Original and Cleaned.")
        self._set_preview_feedback(
            "Diagnostics are ready. GlideAudio is preparing a quick loop so you can compare Original and Cleaned.",
            "Ready",
        )
        self._log(
            f"Analysis ready | Peak {diagnostics.peak_dbfs:.1f} dBFS | "
            f"Loudness {diagnostics.average_lufs:.1f} LUFS | "
            f"Noise floor {diagnostics.noise_floor_dbfs:.1f} dBFS | "
            f"Speech {diagnostics.speech_presence}"
        )
        self._log(f"Suggested preset: {suggested_preset} ({suggestion_reason})")
        self.after(80, self._start_preview_generation)

    def _current_filter_chain(self) -> str:
        target = LOUDNESS_TARGETS.get(self.loudness_target_var.get())
        return build_audio_filter_chain(
            self.slider_vars["noise"].get(),
            self.slider_vars["clarity"].get(),
            self.slider_vars["de_echo"].get(),
            self.slider_vars["de_hum"].get(),
            self.slider_vars["leveling"].get(),
            self.slider_vars["limiter"].get(),
            loudness_target=target,
        )

    def _start_preview_generation(self) -> None:
        if self.media_info is None or self.media_path is None or self.mode != "idle":
            return

        ffmpeg_path = self._get_ffmpeg_path()
        start = self.preview_start_var.get()
        preview_length = min(parse_preview_length(self.preview_length_var.get()), self.media_info.duration)
        start = clamp(start, 0.0, max(0.0, self.media_info.duration - preview_length))
        filter_chain = self._current_filter_chain()
        self.preview_is_stale = True

        self._set_mode("preview")
        self._set_status("Building A/B preview...")
        self._set_next_step("Wait for the compare loop, then listen to Original and Cleaned before you export.")
        self._set_preview_feedback(
            f"Rendering {preview_length:.0f}-second preview loop from {format_seconds(start)} for A/B listening.",
            "Generating",
        )
        self._stop_preview_audio()
        self._cleanup_preview_files()

        def worker() -> None:
            try:
                temp_dir = Path(tempfile.mkdtemp(prefix="glideaudio-preview-"))
                original_wav = temp_dir / "original.wav"
                cleaned_wav = temp_dir / "cleaned.wav"
                create_preview_wav(self.media_path, original_wav, ffmpeg_path, start=start, duration=preview_length)
                create_preview_wav(self.media_path, cleaned_wav, ffmpeg_path, start=start, duration=preview_length, filter_chain=filter_chain)
                original_samples = decode_audio_samples(
                    self.media_path,
                    ffmpeg_path,
                    start=start,
                    duration=preview_length,
                    sample_rate=ANALYSIS_SAMPLE_RATE,
                    channels=1,
                )
                cleaned_samples = decode_audio_samples(
                    self.media_path,
                    ffmpeg_path,
                    start=start,
                    duration=preview_length,
                    sample_rate=ANALYSIS_SAMPLE_RATE,
                    channels=1,
                    filter_chain=filter_chain,
                )
                original_image = build_preview_image(
                    original_samples,
                    label="Original",
                    subtitle=f"Loop {format_seconds(start)} to {format_seconds(start + preview_length)}",
                )
                cleaned_image = build_preview_image(
                    cleaned_samples,
                    label="Cleaned",
                    subtitle=f"Preset {self.preset_var.get()} | Target {self.loudness_target_var.get()}",
                )
                self._post_ui(
                    lambda: self._complete_preview_generation(
                        temp_dir,
                        original_wav,
                        cleaned_wav,
                        original_samples,
                        cleaned_samples,
                        original_image,
                        cleaned_image,
                        preview_length,
                        start,
                    )
                )
            except Exception as exc:
                self._post_ui(lambda error_text=str(exc), trace_text=traceback.format_exc(): self._fail_task(error_text, trace_text))

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def _complete_preview_generation(
        self,
        preview_dir: Path,
        original_wav: Path,
        cleaned_wav: Path,
        original_samples: np.ndarray,
        cleaned_samples: np.ndarray,
        original_image: Image.Image,
        cleaned_image: Image.Image,
        preview_length: float,
        start: float,
    ) -> None:
        self.preview_dir = preview_dir
        self.preview_original_wav = original_wav
        self.preview_cleaned_wav = cleaned_wav
        self.preview_original_samples = original_samples
        self.preview_cleaned_samples = cleaned_samples
        self.preview_original_payload = (
            original_samples,
            "Original",
            f"Loop {format_seconds(start)} to {format_seconds(start + preview_length)}",
        )
        self.preview_cleaned_payload = (
            cleaned_samples,
            "Cleaned",
            f"Preset {self.preset_var.get()} | Target {self.loudness_target_var.get()}",
        )
        self.preview_original_caption_var.set(self.preview_original_payload[2])
        self.preview_cleaned_caption_var.set(self.preview_cleaned_payload[2])
        self.preview_is_stale = False
        self._refresh_preview_images()
        self._set_preview_feedback(
            f"Preview ready. Audition {preview_length:.0f} seconds from {format_seconds(start)} as Original and Cleaned.",
            "Ready",
        )
        self._set_mode("idle")
        self._set_status("Preview ready.")
        self._set_next_step("Listen to Original and Cleaned. If the result sounds right, export the final file.")
        self._log(
            f"A/B preview ready | Start {format_seconds(start)} | Length {preview_length:.0f}s | "
            f"Preset {self.preset_var.get()}"
        )

    def _play_preview(self, variant: str) -> None:
        if os.name != "nt":
            messagebox.showinfo(APP_NAME, "Preview transport is currently implemented for Windows WAV playback.")
            return

        target = self.preview_original_wav if variant == "original" else self.preview_cleaned_wav
        if target is None or not target.exists():
            messagebox.showinfo(APP_NAME, "Generate the preview loop first.")
            return

        try:
            if self.preview_active_variant != variant or self.preview_playback_state == "stopped":
                self._close_preview_transport()
                self._mci_send_command(
                    f'open "{str(target)}" type waveaudio alias {PREVIEW_MCI_ALIAS}'
                )
                self._mci_send_command(f"set {PREVIEW_MCI_ALIAS} time format milliseconds")
            elif self.preview_playback_state == "paused":
                self._resume_preview_audio()
                return

            self._mci_send_command(f"play {PREVIEW_MCI_ALIAS}")
            self.preview_active_variant = variant
            self.preview_last_variant = variant
            self.preview_playback_state = "playing"
            self._schedule_preview_loop_restart()
            self._set_preview_feedback(
                f"Playing the {variant} preview loop. Switch cards instantly to compare the same section.",
                f"Playing {variant.capitalize()}",
            )
            self._set_status(f"Playing {variant} preview loop.")
            self._log(f"Playing {variant} preview loop: {target.name}")
            self._update_preview_transport_buttons()
        except RuntimeError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self._close_preview_transport()

    def _toggle_preview_playback(self, variant: str) -> None:
        if self.preview_active_variant == variant and self.preview_playback_state == "playing":
            self._pause_preview_audio()
            return
        self._play_preview(variant)

    def _pause_preview_audio(self) -> None:
        if os.name != "nt" or self.preview_playback_state != "playing":
            return
        try:
            self._mci_send_command(f"pause {PREVIEW_MCI_ALIAS}")
            self._cancel_preview_loop_restart()
            self.preview_playback_state = "paused"
            variant = self.preview_active_variant or "current"
            self._set_preview_feedback(
                f"{variant.capitalize()} preview paused. Press Resume to continue the loop from the same point.",
                f"Paused {variant.capitalize()}",
            )
            self._set_status(f"Paused {variant} preview.")
            self._log(f"Paused {variant} preview loop.")
            self._update_preview_transport_buttons()
        except RuntimeError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self._close_preview_transport()

    def _resume_preview_audio(self) -> None:
        if os.name != "nt" or self.preview_playback_state != "paused":
            return
        try:
            self._mci_send_command(f"resume {PREVIEW_MCI_ALIAS}")
            self.preview_playback_state = "playing"
            self._schedule_preview_loop_restart()
            variant = self.preview_active_variant or "current"
            self._set_preview_feedback(
                f"Playing the {variant} preview loop. Pause or switch cards to compare quickly.",
                f"Playing {variant.capitalize()}",
            )
            self._set_status(f"Playing {variant} preview loop.")
            self._log(f"Resumed {variant} preview loop.")
            self._update_preview_transport_buttons()
        except RuntimeError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self._close_preview_transport()

    def _stop_preview_audio(self, announce: bool = False) -> None:
        self._close_preview_transport()
        if announce:
            self._set_preview_feedback(
                "Preview stopped. Use Play on Original or Cleaned to audition the loop again.",
                "Stopped",
            )
            self._set_status("Preview stopped.")
            self._log("Stopped preview playback.")

    def _reset_preview_audio(self) -> None:
        variant = self.preview_active_variant or self.preview_last_variant
        if variant is None:
            self._set_preview_feedback(
                "No active preview to reset yet. Start Original or Cleaned first.",
                "Ready",
            )
            self._set_status("Preview ready.")
            return

        target = self.preview_original_wav if variant == "original" else self.preview_cleaned_wav
        if target is None or not target.exists():
            self._set_preview_feedback(
                "Preview files are missing. Refresh the preview loop first.",
                "Needs Refresh",
            )
            return

        try:
            if self.preview_playback_state == "stopped":
                self._play_preview(variant)
                return

            self._mci_send_command(f"seek {PREVIEW_MCI_ALIAS} to start")
            self._mci_send_command(f"play {PREVIEW_MCI_ALIAS}")
            self.preview_playback_state = "playing"
            self._schedule_preview_loop_restart()
            self._set_preview_feedback(
                f"Restarted the {variant} preview loop from the beginning.",
                f"Playing {variant.capitalize()}",
            )
            self._set_status(f"Restarted {variant} preview loop.")
            self._log(f"Restarted {variant} preview loop.")
            self._update_preview_transport_buttons()
        except RuntimeError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self._close_preview_transport()

    def _close_preview_transport(self) -> None:
        self._cancel_preview_loop_restart()
        if os.name == "nt":
            self._mci_send_command(f"stop {PREVIEW_MCI_ALIAS}", allow_error=True)
            self._mci_send_command(f"close {PREVIEW_MCI_ALIAS}", allow_error=True)
        self.preview_active_variant = None
        self.preview_playback_state = "stopped"
        self._update_preview_transport_buttons()

    def _cancel_preview_loop_restart(self) -> None:
        if self.preview_loop_after_id is not None:
            try:
                self.after_cancel(self.preview_loop_after_id)
            except Exception:
                pass
            self.preview_loop_after_id = None

    def _preview_status_ms(self, field: str) -> int:
        value = self._mci_send_command(f"status {PREVIEW_MCI_ALIAS} {field}")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Preview playback failed: could not read MCI {field} status.") from exc

    def _schedule_preview_loop_restart(self) -> None:
        if os.name != "nt" or self.preview_playback_state != "playing":
            return
        self._cancel_preview_loop_restart()
        try:
            length_ms = self._preview_status_ms("length")
            position_ms = self._preview_status_ms("position")
            remaining_ms = max(120, length_ms - position_ms + 40)
        except RuntimeError:
            remaining_ms = 250
        self.preview_loop_after_id = self.after(remaining_ms, self._handle_preview_loop_restart)

    def _handle_preview_loop_restart(self) -> None:
        self.preview_loop_after_id = None
        if os.name != "nt" or self.preview_playback_state != "playing" or self.preview_active_variant is None:
            return
        try:
            self._mci_send_command(f"seek {PREVIEW_MCI_ALIAS} to start")
            self._mci_send_command(f"play {PREVIEW_MCI_ALIAS}")
            self._schedule_preview_loop_restart()
        except RuntimeError:
            self._close_preview_transport()

    def _mci_send_command(self, command: str, *, allow_error: bool = False) -> str:
        if os.name != "nt":
            return ""
        response = ctypes.create_unicode_buffer(255)
        error_code = ctypes.windll.winmm.mciSendStringW(command, response, len(response), 0)
        if error_code != 0 and not allow_error:
            error_text = ctypes.create_unicode_buffer(255)
            ctypes.windll.winmm.mciGetErrorStringW(error_code, error_text, len(error_text))
            detail = error_text.value.strip() or f"MCI error {error_code}"
            raise RuntimeError(f"Preview playback failed: {detail}")
        return response.value.strip()

    def _on_preview_slider_changed(self, value: float) -> None:
        self.preview_time_label.configure(text=format_seconds(value))

    def _on_preview_length_changed(self) -> None:
        if self.media_info is None:
            self._persist_app_settings()
            return
        preview_length = min(parse_preview_length(self.preview_length_var.get()), self.media_info.duration)
        max_start = max(0.0, self.media_info.duration - preview_length)
        current = clamp(self.preview_start_var.get(), 0.0, max_start)
        self.preview_start_var.set(current)
        self.preview_slider.configure(from_=0.0, to=max(max_start, 1e-3), number_of_steps=max(1, int(max(max_start, 0.0) * 4) + 1))
        self.preview_time_label.configure(text=format_seconds(current))
        self.preview_is_stale = True
        self._persist_app_settings()
        if self.mode == "idle" and self.media_info is not None:
            self.after(40, self._start_preview_generation)

    def _on_slider_changed(self, key: str) -> None:
        value = self.slider_vars[key].get()
        self.slider_value_labels[key].configure(text=f"{int(round(value * 100))}%")
        self.preset_var.set("Custom")
        self.preview_is_stale = True
        if self.media_info is not None and self.mode == "idle":
            self._set_preview_feedback("Settings changed. Update the preview loop to hear the new cleanup.", "Needs Refresh")
            self._set_next_step("Update the preview, then compare Original and Cleaned again before exporting.")
            self._refresh_action_states()

    def _apply_preset(self, preset_name: str) -> None:
        preset = PRESET_VALUES.get(preset_name)
        if preset is None:
            return
        for key, _label in SLIDER_KEYS:
            self.slider_vars[key].set(preset[key])
            self.slider_value_labels[key].configure(text=f"{int(round(preset[key] * 100))}%")
        self.preset_var.set(preset_name)
        self.preview_is_stale = True
        self._persist_app_settings()
        if self.media_info is not None and self.mode == "idle":
            self._set_preview_feedback(
                f"Preset changed to {preset_name}. GlideAudio is rebuilding the preview loop.",
                "Generating",
            )
            self._set_next_step("GlideAudio is rebuilding the compare loop with the updated preset.")
            self.after(40, self._start_preview_generation)

    def _on_export_mode_changed(self) -> None:
        mode = self.export_mode_var.get()
        format_values = EXPORT_FORMATS[mode]
        self.export_format_menu.configure(values=format_values)
        if self.export_format_var.get() not in format_values:
            self.export_format_var.set(format_values[0])
        self.output_path = None
        self.output_label.configure(text=str(self.output_dir))
        self._update_export_guidance()
        self._persist_app_settings()

    def _on_export_format_changed(self) -> None:
        self.output_path = None
        self.output_label.configure(text=str(self.output_dir))
        self._persist_app_settings()

    def _on_loudness_target_changed(self) -> None:
        self._persist_app_settings()
        if self.media_info is not None and self.mode == "idle":
            self.preview_is_stale = True
            self._set_preview_feedback(
                f"Loudness target changed to {self.loudness_target_var.get()}. Rebuilding the preview loop.",
                "Generating",
            )
            self._set_next_step("GlideAudio is rebuilding the compare loop with the updated loudness target.")
            self.after(40, self._start_preview_generation)

    def _choose_output_path(self) -> None:
        if self.media_path is None:
            messagebox.showinfo(APP_NAME, "Load a source file first.")
            return

        mode = self.export_mode_var.get()
        format_name = self.export_format_var.get().lower()
        suggested_name = suggested_output_filename(
            self.media_path,
            mode=mode,
            format_name=self.export_format_var.get(),
        )
        filetypes = [("All Files", "*.*")]
        if mode == EXPORT_MODE_AUDIO:
            filetypes = [(f"{self.export_format_var.get()} File", f"*.{format_name}")]
        else:
            filetypes = [("MP4 Video", "*.mp4")]

        chosen = filedialog.asksaveasfilename(
            title="Choose Export Destination",
            initialdir=str(self.output_dir),
            initialfile=suggested_name,
            defaultextension=f".{format_name if mode == EXPORT_MODE_AUDIO else 'mp4'}",
            filetypes=filetypes,
        )
        if chosen:
            self.output_path = Path(chosen)
            self.output_dir = self.output_path.parent
            self.output_label.configure(text=str(self.output_path))
            self._set_next_step("Save location is ready. Export the final file when the preview sounds right.")
            self._persist_app_settings()

    def _render_output_to_path(
        self,
        *,
        media_path: Path,
        media_info: MediaInfo,
        output_path: Path,
        mode: str,
        format_name: str,
        filter_chain: str,
        ffmpeg_path: str,
        ffprobe_path: str,
    ) -> MediaInfo:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_output_path = output_path.with_name(f"{output_path.stem}.glideaudio-render{output_path.suffix}")
        if temp_output_path.exists():
            temp_output_path.unlink(missing_ok=True)

        command = (
            build_video_export_command(media_path, temp_output_path, ffmpeg_path, filter_chain=filter_chain)
            if mode == EXPORT_MODE_VIDEO
            else build_audio_export_command(
                media_path,
                temp_output_path,
                ffmpeg_path,
                filter_chain=filter_chain,
                format_name=format_name,
            )
        )
        self._queue_log(" ".join(command))

        try:
            run_ffmpeg_with_progress(
                command,
                duration=media_info.duration,
                cancel_event=self.cancel_event,
                log_callback=self._queue_log,
                progress_callback=self._queue_progress,
                process_callback=self._set_active_process,
            )
            verified_info = verify_rendered_output(
                temp_output_path,
                ffprobe_path=ffprobe_path,
                expected_video=mode == EXPORT_MODE_VIDEO,
                expected_audio=True,
                source_duration=media_info.duration,
            )
            if output_path.exists():
                output_path.unlink()
            temp_output_path.replace(output_path)
            return verified_info
        except Exception:
            temp_output_path.unlink(missing_ok=True)
            raise

    def _set_batch_item_state(
        self,
        item_id: str,
        *,
        status: str,
        detail: str,
        output_path: Optional[Path] = None,
    ) -> None:
        item = next((queued for queued in self.batch_queue if queued.item_id == item_id), None)
        if item is None:
            return
        item.status = status
        item.detail = detail
        item.output_path = output_path
        self._upsert_batch_item(item)
        self._refresh_action_states()

    def _complete_batch_queue(self, *, cancelled: bool, successes: int, failures: int, total: int) -> None:
        self.progress.set(0.0 if cancelled else 1.0)
        self._set_mode("idle")
        self.active_process = None
        if cancelled:
            self._set_status("Batch queue stopped.")
            self._set_next_step("Review the queue state, then rerun it or go back to single-file export.")
            self._update_batch_status(f"Queue stopped after {successes + failures}/{total} file(s).")
            self.export_status_var.set("Batch queue stopped before finishing every file.")
            self._log("Batch queue stopped.")
            return

        self._set_status("Batch queue complete.")
        self._set_next_step("Review any failed queue items, or load another source for single-file cleanup.")
        self.export_status_var.set(f"Batch queue finished. {successes} succeeded, {failures} failed.")
        self._update_batch_status(f"Queue finished. {successes} succeeded, {failures} failed.")
        self._log(f"Batch queue finished. {successes} succeeded, {failures} failed.")

    def _stop_batch_queue(self) -> None:
        if self.mode != "batch":
            return
        self.cancel_event.set()
        process = self.active_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass
        self._update_batch_status("Stopping the active batch queue...")
        self.export_status_var.set("Stopping batch queue...")
        self._log("Stop requested for the active batch queue.")

    def _start_batch_queue(self) -> None:
        if self.mode != "idle" or not self.batch_queue:
            return

        requested_mode = self.export_mode_var.get()
        format_name = self.export_format_var.get()
        filter_chain = self._current_filter_chain()
        ffmpeg_path = self._get_ffmpeg_path()
        ffprobe_path = self._get_ffprobe_path()
        queue_items = [item for item in self.batch_queue]

        self.cancel_event.clear()
        self.progress.set(0.0)
        self._set_mode("batch")
        self._set_status("Running batch queue...")
        self._set_next_step("GlideAudio is batch rendering with the current cleanup and export settings.")
        self.export_status_var.set(f"Batch rendering {len(queue_items)} queued file(s) with the current cleanup settings.")
        self._update_batch_status(f"Running queue 0/{len(queue_items)}...")
        self._persist_app_settings()

        for item in queue_items:
            self._set_batch_item_state(item.item_id, status="Queued", detail="Waiting to export.", output_path=None)

        def worker() -> None:
            successes = 0
            failures = 0
            total = len(queue_items)
            try:
                for index, item in enumerate(queue_items, start=1):
                    if self.cancel_event.is_set():
                        break

                    self._post_ui(
                        lambda item_id=item.item_id, index=index, total=total: self._update_batch_status(
                            f"Running queue {index}/{total}..."
                        )
                    )
                    self._post_ui(
                        lambda item_id=item.item_id: self._set_batch_item_state(
                            item_id,
                            status="Running",
                            detail="Rendering with the current export settings.",
                            output_path=None,
                        )
                    )
                    try:
                        info = probe_media(item.path, ffprobe_path)
                        if not info.has_audio:
                            raise RuntimeError("The queued file has no audio stream to clean.")

                        actual_mode = requested_mode
                        detail_prefix = "Using requested export mode."
                        if requested_mode == EXPORT_MODE_VIDEO and not info.has_video:
                            actual_mode = EXPORT_MODE_AUDIO
                            detail_prefix = "Audio-only fallback from repaired video mode."

                        output_path = self._default_output_path(
                            item.path,
                            mode=actual_mode,
                            format_name=format_name,
                            allow_existing=False,
                        )
                        verified_info = self._render_output_to_path(
                            media_path=item.path,
                            media_info=info,
                            output_path=output_path,
                            mode=actual_mode,
                            format_name=format_name,
                            filter_chain=filter_chain,
                            ffmpeg_path=ffmpeg_path,
                            ffprobe_path=ffprobe_path,
                        )
                        summary = (
                            f"{detail_prefix} Saved {output_path.name}"
                            if actual_mode == EXPORT_MODE_AUDIO
                            else f"Saved repaired video {output_path.name}"
                        )
                        self._post_ui(
                            lambda item_id=item.item_id, detail=summary, output_path=output_path: self._set_batch_item_state(
                                item_id,
                                status="Done",
                                detail=detail,
                                output_path=output_path,
                            )
                        )
                        self._queue_log(f"Batch export complete: {output_path} ({verified_info.audio_codec})")
                        successes += 1
                    except Exception as exc:
                        if str(exc) == "cancelled":
                            break
                        friendly = friendly_export_error(
                            str(exc),
                            output_path=self._default_output_path(
                                item.path,
                                mode=EXPORT_MODE_AUDIO if requested_mode == EXPORT_MODE_VIDEO else requested_mode,
                                format_name=format_name,
                                allow_existing=True,
                            ),
                            format_name=format_name,
                        )
                        self._post_ui(
                            lambda item_id=item.item_id, detail=friendly: self._set_batch_item_state(
                                item_id,
                                status="Failed",
                                detail=shorten_middle(detail, 72),
                                output_path=None,
                            )
                        )
                        self._queue_log(f"Batch export failed for {item.path}: {friendly}")
                        failures += 1
                self._post_ui(
                    lambda successes=successes, failures=failures, total=total: self._complete_batch_queue(
                        cancelled=self.cancel_event.is_set(),
                        successes=successes,
                        failures=failures,
                        total=total,
                    )
                )
            except Exception as exc:
                self._post_ui(lambda error_text=str(exc), trace_text=traceback.format_exc(): self._fail_task(error_text, trace_text))

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def _start_export(self) -> None:
        if self.media_info is None or self.media_path is None or self.mode != "idle":
            return

        mode = self.export_mode_var.get()
        if mode == EXPORT_MODE_VIDEO and not self.media_info.has_video:
            messagebox.showinfo(APP_NAME, "Repaired video export is only available for video sources.")
            return

        if self.output_path is None:
            self._choose_output_path()
            if self.output_path is None:
                return

        output_path = self.output_path
        if output_path.resolve().samefile(self.media_path) if output_path.exists() else output_path.resolve(strict=False) == self.media_path.resolve():
            messagebox.showerror(APP_NAME, "Choose a different export path than the source file.")
            return

        if output_path.exists():
            overwrite = messagebox.askyesno(
                APP_NAME,
                f"Replace the existing export?\n\n{output_path}",
                icon="warning",
            )
            if not overwrite:
                self.export_status_var.set("Export cancelled before render. Choose a different file name or folder.")
                self._set_status("Export cancelled.")
                self._set_next_step("Choose another save location, then export the final file when you are ready.")
                return

        filter_chain = self._current_filter_chain()
        ffmpeg_path = self._get_ffmpeg_path()
        ffprobe_path = self._get_ffprobe_path()

        self.cancel_event.clear()
        self.progress.set(0.0)
        self._set_mode("export")
        self._set_status("Exporting cleaned output...")
        self._set_next_step("GlideAudio is rendering the final file. Wait for verification before closing the app.")
        self.export_status_var.set(f"Rendering {output_path.name} ...")
        self._log(f"Starting export -> {output_path}")

        def worker() -> None:
            try:
                verified_info = self._render_output_to_path(
                    media_path=self.media_path,
                    media_info=self.media_info,
                    output_path=output_path,
                    mode=mode,
                    format_name=self.export_format_var.get(),
                    filter_chain=filter_chain,
                    ffmpeg_path=ffmpeg_path,
                    ffprobe_path=ffprobe_path,
                )
                self._post_ui(lambda info=verified_info: self._complete_export(output_path, info))
            except Exception as exc:
                if str(exc) == "cancelled":
                    self._post_ui(self._complete_cancelled_export)
                else:
                    self._post_ui(
                        lambda error_text=str(exc), trace_text=traceback.format_exc(): self._fail_export(
                            error_text,
                            trace_text,
                            output_path=output_path,
                            format_name=self.export_format_var.get(),
                        )
                    )

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def _stop_export(self) -> None:
        if self.mode != "export":
            return
        self.cancel_event.set()
        process = self.active_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass
        self.export_status_var.set("Stopping export...")
        self._log("Stop requested for the active export.")

    def _set_active_process(self, process: Optional[subprocess.Popen]) -> None:
        self.active_process = process

    def _complete_export(self, output_path: Path, info: MediaInfo) -> None:
        self.progress.set(1.0)
        if info.has_video:
            summary = f"Verified repaired MP4 | {format_seconds(info.duration)} | {info.width}x{info.height}"
        else:
            summary = f"Verified cleaned audio | {format_seconds(info.duration)} | {info.audio_codec}"
        self.export_status_var.set(f"Export complete: {output_path.name}")
        self._set_mode("idle")
        self._set_status("Export complete.")
        self._set_next_step("Export another format, queue more files, or load a new source.")
        self._log(f"Export complete: {output_path}")
        self._log(summary)
        messagebox.showinfo(APP_NAME, f"Saved cleaned output to:\n{output_path}\n\n{summary}")

    def _complete_cancelled_export(self) -> None:
        self.progress.set(0.0)
        self.export_status_var.set("Export cancelled.")
        self._set_mode("idle")
        self._set_status("Export cancelled.")
        self._set_next_step("Choose another save location or export format when you are ready to try again.")
        self._log("Export cancelled.")

    def _fail_export(self, error_text: str, trace_text: str, *, output_path: Path, format_name: str) -> None:
        self.cancel_event.clear()
        self.active_process = None
        self.progress.set(0.0)
        self._set_mode("idle")
        friendly = friendly_export_error(error_text, output_path=output_path, format_name=format_name)
        self.export_status_var.set("Export failed. Review the message and try again.")
        self._set_status("Export failed.")
        self._set_next_step("Review the error, then try a simpler format like WAV or choose a different save location.")
        self._log(trace_text)
        self._log(f"Export failed: {friendly}")
        messagebox.showerror(APP_NAME, friendly)

    def _queue_progress(self, value: float) -> None:
        self._post_ui(lambda: self.progress.set(clamp(value, 0.0, 1.0)))

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        self._refresh_action_states()

    def _refresh_action_states(self) -> None:
        busy = self.mode != "idle"
        has_source = self.media_info is not None
        has_preview = self.preview_original_wav is not None and self.preview_cleaned_wav is not None
        can_video = bool(self.media_info and self.media_info.has_video)
        has_batch_items = bool(self.batch_queue)
        has_batch_selection = bool(self._selected_batch_item_ids()) if hasattr(self, "batch_tree") else False

        self.browse_button.configure(state="normal" if not busy else "disabled")
        self.analyze_button.configure(state="normal" if has_source and not busy else "disabled")
        self.refresh_preview_button.configure(state="normal" if has_source and not busy else "disabled")
        self.stop_preview_button.configure(
            state="normal" if self.preview_playback_state in {"playing", "paused"} and not busy else "disabled"
        )
        self.reset_preview_button.configure(
            state="normal"
            if has_preview and self.preview_last_variant is not None and not busy
            else "disabled"
        )
        self.output_button.configure(state="normal" if has_source and not busy else "disabled")
        self.export_button.configure(state="normal" if has_source and not busy else "disabled")
        self.stop_export_button.configure(state="normal" if self.mode == "export" else "disabled")
        self.preview_slider.configure(state="normal" if has_source and not busy else "disabled")
        self.preview_length_menu.configure(state="normal" if has_source and not busy else "disabled")
        self.preset_menu.configure(state="normal" if not busy else "disabled")
        self.reapply_suggested_button.configure(
            state="normal" if self.suggested_preset_name is not None and has_source and not busy else "disabled"
        )
        self.export_mode_menu.configure(state="normal" if has_source and not busy else "disabled")
        self.export_format_menu.configure(state="normal" if has_source and not busy else "disabled")
        self.loudness_target_menu.configure(state="normal" if has_source and not busy else "disabled")
        self.batch_add_button.configure(state="normal" if not busy else "disabled")
        self.batch_queue_current_button.configure(state="normal" if has_source and not busy else "disabled")
        self.batch_load_button.configure(state="normal" if has_batch_selection and not busy else "disabled")
        self.batch_remove_button.configure(state="normal" if has_batch_selection and not busy else "disabled")
        self.batch_clear_button.configure(state="normal" if has_batch_items and not busy else "disabled")
        self.batch_run_button.configure(state="normal" if has_batch_items and not busy else "disabled")
        self.batch_stop_button.configure(state="normal" if self.mode == "batch" else "disabled")
        self._update_preview_refresh_button(has_preview=has_preview)
        self._update_preview_transport_buttons(has_preview=has_preview, busy=busy)
        if not can_video and self.export_mode_var.get() == EXPORT_MODE_VIDEO:
            self.export_mode_var.set(EXPORT_MODE_AUDIO)
            self._on_export_mode_changed()

    def _update_preview_refresh_button(self, *, has_preview: Optional[bool] = None) -> None:
        if not hasattr(self, "refresh_preview_button"):
            return
        if has_preview is None:
            has_preview = self.preview_original_wav is not None and self.preview_cleaned_wav is not None
        if not has_preview:
            label = "Build Preview"
        elif self.preview_is_stale:
            label = "Update Preview"
        else:
            label = "Rebuild Preview"
        self.refresh_preview_button.configure(text=label)

    def _update_preview_transport_buttons(self, has_preview: Optional[bool] = None, busy: Optional[bool] = None) -> None:
        if not hasattr(self, "preview_original_toggle_button") or not hasattr(self, "preview_cleaned_toggle_button"):
            return

        if has_preview is None:
            has_preview = self.preview_original_wav is not None and self.preview_cleaned_wav is not None
        if busy is None:
            busy = self.mode != "idle"

        original_text = "Play"
        cleaned_text = "Play"
        if self.preview_active_variant == "original":
            original_text = "Pause" if self.preview_playback_state == "playing" else "Resume"
        elif self.preview_active_variant == "cleaned":
            cleaned_text = "Pause" if self.preview_playback_state == "playing" else "Resume"

        button_state = "normal" if has_preview and not busy else "disabled"
        original_active = self.preview_active_variant == "original" and self.preview_playback_state in {"playing", "paused"}
        cleaned_active = self.preview_active_variant == "cleaned" and self.preview_playback_state in {"playing", "paused"}

        self.preview_original_toggle_button.configure(
            text=original_text,
            state=button_state,
            fg_color=COLORS["primary"] if original_active else "transparent",
            hover_color=COLORS["primary_hover"] if original_active else COLORS["surface_alt"],
            text_color=COLORS["bg_primary"] if original_active else COLORS["text_primary"],
            border_color=COLORS["primary"] if original_active else COLORS["border"],
        )
        self.preview_cleaned_toggle_button.configure(
            text=cleaned_text,
            state=button_state,
            fg_color=COLORS["primary"] if cleaned_active else "transparent",
            hover_color=COLORS["primary_hover"] if cleaned_active else COLORS["surface_alt"],
            text_color=COLORS["bg_primary"] if cleaned_active else COLORS["text_primary"],
            border_color=COLORS["primary"] if cleaned_active else COLORS["border"],
        )
        self.preview_original_frame.configure(border_color=COLORS["primary"] if original_active else COLORS["border"])
        self.preview_cleaned_frame.configure(border_color=COLORS["primary"] if cleaned_active else COLORS["border"])

    def _set_preview_feedback(self, message: str, state_label: str) -> None:
        self.preview_status_var.set(message)
        self.preview_transport_var.set(state_label)

    def _apply_suggested_preset(self) -> None:
        if self.suggested_preset_name is None:
            return
        self._apply_preset(self.suggested_preset_name)

    def _update_export_guidance(self) -> None:
        mode = self.export_mode_var.get()
        if self.media_info is None:
            self.export_status_var.set("Step 3: once the preview sounds right, choose where to save the final cleaned file.")
            return
        if mode == EXPORT_MODE_VIDEO and self.media_info.has_video:
            self.export_status_var.set("Export a repaired MP4. GlideAudio keeps the original video and swaps in the cleaned audio.")
            return
        self.export_status_var.set("Export a cleaned audio file. WAV is the safest choice if you want the most reliable output.")

    def _apply_scaled_image(
        self,
        *,
        label: ctk.CTkLabel,
        pil_image: Optional[Image.Image],
        aspect_ratio: float,
        fallback_size: tuple[int, int],
        max_height: Optional[int] = None,
        target_attr: str,
        forced_size: Optional[tuple[int, int]] = None,
    ) -> None:
        if pil_image is None:
            return

        if forced_size is not None:
            target_size = forced_size
        else:
            label.update_idletasks()
            width = label.winfo_width()
            if width <= 1 and label.master is not None:
                label.master.update_idletasks()
                width = label.master.winfo_width()

            if width <= 1:
                target_size = fallback_size
            else:
                horizontal_padding = 12
                target_size = fit_aspect_size(
                    aspect_ratio,
                    max(140, width - horizontal_padding),
                    max_height=max_height,
                )

        resized = pil_image.resize(target_size, Image.Resampling.LANCZOS)
        ctk_image = ctk.CTkImage(light_image=resized, dark_image=resized, size=target_size)
        setattr(self, target_attr, ctk_image)
        label.configure(image=ctk_image, text="", width=target_size[0], height=target_size[1])

    def _refresh_source_image(self) -> None:
        self.source_preview_frame.update_idletasks()
        available_width = self.source_preview_frame.winfo_width() - 32
        self._apply_scaled_image(
            label=self.source_preview_label,
            pil_image=self.source_pil_image,
            aspect_ratio=SOURCE_PREVIEW_ASPECT,
            fallback_size=fit_aspect_size(SOURCE_PREVIEW_ASPECT, max(140, available_width), max_height=240)
            if available_width > 1
            else SOURCE_PREVIEW_SIZE,
            max_height=240,
            target_attr="source_image",
            forced_size=fit_aspect_size(SOURCE_PREVIEW_ASPECT, max(140, available_width), max_height=240)
            if available_width > 1
            else None,
        )

    def _refresh_preview_images(self) -> None:
        self.preview_images_frame.update_idletasks()
        available_width = self.preview_images_frame.winfo_width()
        gutter = 20
        per_card_width = max(160, (available_width - gutter) // 2) if available_width > 1 else AB_PREVIEW_SIZE[0]
        shared_height = max(140, min(176, int(round(per_card_width * 0.38))))
        shared_size = (per_card_width, shared_height)

        if self.preview_original_payload is not None:
            self.preview_original_pil_image = build_preview_image(
                self.preview_original_payload[0],
                label=self.preview_original_payload[1],
                subtitle=self.preview_original_payload[2],
                size=shared_size,
            )
        if self.preview_cleaned_payload is not None:
            self.preview_cleaned_pil_image = build_preview_image(
                self.preview_cleaned_payload[0],
                label=self.preview_cleaned_payload[1],
                subtitle=self.preview_cleaned_payload[2],
                size=shared_size,
            )

        self._apply_scaled_image(
            label=self.preview_original_label,
            pil_image=self.preview_original_pil_image,
            aspect_ratio=AB_PREVIEW_ASPECT,
            fallback_size=shared_size,
            max_height=shared_height,
            target_attr="preview_original_image",
            forced_size=shared_size,
        )
        self._apply_scaled_image(
            label=self.preview_cleaned_label,
            pil_image=self.preview_cleaned_pil_image,
            aspect_ratio=AB_PREVIEW_ASPECT,
            fallback_size=shared_size,
            max_height=shared_height,
            target_attr="preview_cleaned_image",
            forced_size=shared_size,
        )

    def _set_source_placeholder(self) -> None:
        self.source_pil_image = waveform_card_image(
            np.asarray([], dtype=np.float32),
            SOURCE_PREVIEW_SIZE,
            title="Source Preview",
            subtitle="Load media to inspect waveform or poster frame.",
        )
        self.suggested_preset_name = None
        self.suggested_preset_var.set("Waiting for analysis.")
        self.source_preview_caption_var.set("Load media to inspect waveform or poster frame.")
        self._refresh_source_image()

    def _set_preview_placeholders(self) -> None:
        self.preview_active_variant = None
        self.preview_last_variant = None
        self.preview_playback_state = "stopped"
        self.preview_is_stale = True
        self.preview_original_payload = (
            np.asarray([], dtype=np.float32),
            "Original",
            "Original reference loop appears here after analysis.",
        )
        self.preview_cleaned_payload = (
            np.asarray([], dtype=np.float32),
            "Cleaned",
            "Cleaned loop appears here after preview render.",
        )
        self.preview_original_caption_var.set(self.preview_original_payload[2])
        self.preview_cleaned_caption_var.set(self.preview_cleaned_payload[2])
        self._set_preview_feedback("GlideAudio will build a short original-vs-cleaned preview after analysis.", "Idle")
        self._refresh_preview_images()

    def _cleanup_preview_files(self) -> None:
        if self.preview_dir is not None and self.preview_dir.exists():
            shutil.rmtree(self.preview_dir, ignore_errors=True)
        self.preview_dir = None
        self.preview_original_wav = None
        self.preview_cleaned_wav = None
        self.preview_original_payload = None
        self.preview_cleaned_payload = None
        self.preview_active_variant = None
        self.preview_last_variant = None
        self.preview_playback_state = "stopped"
        self.preview_is_stale = True

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _persist_app_settings(self) -> None:
        settings = {
            "preset": self.preset_var.get(),
            "preview_length": self.preview_length_var.get(),
            "loudness_target": self.loudness_target_var.get(),
            "output_dir": str(self.output_dir),
            "export_mode": self.export_mode_var.get(),
            "export_format": self.export_format_var.get(),
        }
        try:
            save_app_settings(settings)
        except Exception as exc:
            self._log(f"Could not save settings: {exc}")

    def _set_next_step(self, message: str) -> None:
        self.next_step_var.set(message)

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message.rstrip() + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _queue_log(self, message: str) -> None:
        self._post_ui(lambda: self._log(message))

    def _post_ui(self, callback) -> None:
        self.ui_queue.put(callback)

    def _drain_ui_events(self) -> None:
        while True:
            try:
                callback = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception:
                self._log(traceback.format_exc())
        self.after(40, self._drain_ui_events)

    def _fail_task(self, error_text: str, trace_text: str) -> None:
        self.cancel_event.clear()
        self.active_process = None
        self.progress.set(0.0)
        self._set_mode("idle")
        self._set_status("Task failed.")
        self._set_next_step("Review the error, then retry the last step or load a different source file.")
        self._log(trace_text)
        messagebox.showerror(APP_NAME, error_text)

    def _on_close(self) -> None:
        self.cancel_event.set()
        process = self.active_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass
        self._persist_app_settings()
        self._stop_preview_audio()
        self._cleanup_preview_files()
        self.destroy()


def main() -> None:
    app = GlideAudioApp()
    app.mainloop()


if __name__ == "__main__":
    main()
