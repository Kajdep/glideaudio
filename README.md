# GlideAudio

GlideAudio is a Windows desktop app for cleaning spoken audio in videos and audio files without requiring a full DAW or cloud workflow.

See `PRODUCT-BRIEF.md` for the build-oriented product spec.

## Current Build

The first desktop shell is now in `glideaudio.py`. It currently includes:

- drag and drop or file-picker source loading
- FFprobe-based media metadata
- diagnostics for peak, loudness, noise floor, clipping risk, and speech presence
- cleanup presets plus six module sliders
- short A/B loop preview generation
- cleaned audio export and repaired MP4 export

## Run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python glideaudio.py
```

FFmpeg and FFprobe must be available on `PATH`, in a nearby `ffmpeg\bin` folder, or via `FFMPEG_PATH` / `FFPROBE_PATH`.

## Smoke Test

```powershell
python scripts\smoke_test.py
```

This creates a temporary synthetic sample, runs analysis, generates a cleaned preview WAV, and verifies both audio-only and repaired-video exports.

## Build EXE

```powershell
python -m pip install pyinstaller
.\build_release.ps1
```

The release script builds `GlideAudio.exe` from [glideaudio.spec](/D:/glide-apps/glideaudio/glideaudio.spec) and creates a zip in `release\`.
