from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import glideaudio


def main() -> None:
    ffmpeg = glideaudio.resolve_binary("ffmpeg")
    ffprobe = glideaudio.resolve_binary("ffprobe")

    with tempfile.TemporaryDirectory(prefix="glideaudio-smoke-") as temp_dir:
        root = Path(temp_dir)
        sample_mp4 = root / "sample.mp4"
        preview_wav = root / "preview.wav"
        export_wav = root / "cleaned.wav"
        export_mp4 = root / "cleaned.mp4"

        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=640x360:rate=30",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=220:sample_rate=48000:duration=8",
                "-f",
                "lavfi",
                "-i",
                "anoisesrc=color=white:amplitude=0.03:sample_rate=48000:duration=8",
                "-filter_complex",
                "[1:a][2:a]amix=inputs=2:weights=1 0.35[a]",
                "-map",
                "0:v:0",
                "-map",
                "[a]",
                "-t",
                "8",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(sample_mp4),
            ],
            check=True,
        )

        info = glideaudio.probe_media(sample_mp4, ffprobe)
        samples = glideaudio.decode_audio_samples(
            sample_mp4,
            ffmpeg,
            duration=6,
            sample_rate=glideaudio.ANALYSIS_SAMPLE_RATE,
        )
        diagnostics = glideaudio.analyze_audio_samples(
            samples,
            glideaudio.ANALYSIS_SAMPLE_RATE,
            average_lufs=glideaudio.loudnorm_probe(sample_mp4, ffmpeg, 6),
            peak_dbfs=glideaudio.peak_volume_probe(sample_mp4, ffmpeg, 6),
        )
        filter_chain = glideaudio.build_audio_filter_chain(
            0.5,
            0.5,
            0.2,
            0.2,
            0.5,
            0.5,
            loudness_target=-14.0,
        )

        glideaudio.create_preview_wav(
            sample_mp4,
            preview_wav,
            ffmpeg,
            start=1.0,
            duration=6.0,
            filter_chain=filter_chain,
        )
        subprocess.run(
            glideaudio.build_audio_export_command(
                sample_mp4,
                export_wav,
                ffmpeg,
                filter_chain=filter_chain,
                format_name="WAV",
            ),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            glideaudio.build_video_export_command(
                sample_mp4,
                export_mp4,
                ffmpeg,
                filter_chain=filter_chain,
            ),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        audio_info = glideaudio.verify_rendered_output(
            export_wav,
            ffprobe_path=ffprobe,
            expected_video=False,
            expected_audio=True,
            source_duration=info.duration,
        )
        repaired_info = glideaudio.verify_rendered_output(
            export_mp4,
            ffprobe_path=ffprobe,
            expected_video=True,
            expected_audio=True,
            source_duration=info.duration,
        )

        print("source:", info)
        print("diagnostics:", diagnostics)
        print("preview bytes:", preview_wav.stat().st_size)
        print("audio export:", audio_info)
        print("video export:", repaired_info)


if __name__ == "__main__":
    main()
