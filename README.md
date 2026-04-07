# GlideAudio

GlideAudio is a Windows desktop app for cleaning spoken audio in videos and audio files without requiring a full DAW or cloud workflow.

See `PRODUCT-BRIEF.md` for the build-oriented product spec.

## Current Build

The first desktop shell is now in `glideaudio.py`. It currently includes:

- drag and drop or file-picker source loading
- FFprobe-based media metadata
- diagnostics for peak, loudness, noise floor, clipping risk, and speech presence
- suggested starting presets from source analysis
- cleanup presets plus six module sliders
- short A/B loop preview generation
- per-card preview play, pause, stop, and reset controls
- session settings persistence for the common export and preview choices
- simple batch queueing for repeated exports
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

## Brand Assets

```powershell
python scripts\generate_brand_assets.py
```

This regenerates the app icon, logo, and store collateral in `assets\store\`.

## Build EXE

```powershell
python -m pip install pyinstaller
.\build_release.ps1
```

The release script builds `GlideAudio.exe` from [glideaudio.spec](/D:/glide-apps/glideaudio/glideaudio.spec), copies the bundled docs, and creates:

- `release\win64\GlideAudio.exe`
- `release\GlideAudio-0.1.0-win64.zip`

The release package also includes [PRIVACY_POLICY.md](/D:/glide-apps/glideaudio/PRIVACY_POLICY.md) for local distribution.
