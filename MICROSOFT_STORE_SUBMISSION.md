# GlideAudio Microsoft Store Submission

## Identity

- Partner Center identity / package name: `NatflaLtd.GlideAudio`
- Publisher: `CN=5A609937-1921-4929-89C2-766139363CA0`
- Publisher display name: `Natfla Ltd`
- Package family name: `NatflaLtd.GlideAudio_pa3aqdh53p230`
- Package SID: `S-1-15-2-2161190272-2418176117-478214088-3628919072-1152830748-3081032745-1746997563`
- Store ID / product ID: `9P1F9CXS8KPF`
- Store deep link: `Available after the product is live`
- Web Store URL: `Available after the product is live`

## Package

- Architecture: `x64`
- Packaging format: `PyInstaller single-file executable delivered in a win64 zip bundle`
- Version: `0.1.0`
- Signed by: `_TBD_`
- Release artifact path: `D:\glide-apps\glideaudio\release\GlideAudio-0.1.0-win64.zip`
- EXE path inside release folder: `D:\glide-apps\glideaudio\release\win64\GlideAudio.exe`

## Listing Fields

- App name: `GlideAudio`
- Short description (max 200 chars):

```text
Local-first spoken-audio cleanup for videos and audio files, with noise reduction, voice clarity, loudness leveling, and repaired-video export.
```

- Long description:

```markdown
# GlideAudio

GlideAudio is a desktop app for cleaning spoken audio in videos and audio files without the overhead of a full DAW. Analyze the source, tune the cleanup, preview the before-and-after result, and export either a cleaned audio file or a repaired video.

## Why People Use GlideAudio

- Reduce background noise and hiss
- Improve voice clarity for tutorials, talking-head videos, and podcast-style audio
- Keep the workflow local instead of uploading source media to a cloud editor

## Key Features

- Noise reduction
- Voice clarity enhancement
- De-echo and de-hum controls
- Loudness leveling and limiter
- Export cleaned audio or repaired video

## Great For

- Tutorials and screen recordings
- Talking-head videos
- Creator and client-service workflows

## Privacy

Hosted policy URL still needs to be published.

Current release package includes:

- `PRIVACY_POLICY.md`
- local-first processing only
- no telemetry or account requirement

## System Requirements

- Windows 10 version 1809 or later, or Windows 11
- 64-bit processor
- 4 GB RAM recommended pending final QA confirmation
- 250 MB free disk space recommended for the app bundle and temp/export work
```

- Keywords:

```text
audio cleanup, voice enhancement, noise reduction, video audio repair, podcast audio, creator tool
```

- Category / subcategory: `_TBD_`
- Website URL: `https://kajdep.itch.io/glideaudio`
- Privacy policy URL: `Hosted URL still TBD. Local package includes PRIVACY_POLICY.md.`
- Support URL or support email: `https://kajdep.itch.io/glideaudio`

## Store Assets

- Store logo set ready: `yes`
- Icon file: `D:\glide-apps\glideaudio\glideaudio.ico`
- Cover image: `D:\glide-apps\glideaudio\assets\store\glideaudio-cover.png`
- Hero art: `D:\glide-apps\glideaudio\assets\store\glideaudio-store-hero.png`
- Square art: `D:\glide-apps\glideaudio\assets\store\glideaudio-store-square.png`
- Screenshot set:
  - `_TBD_`
  - `_TBD_`
  - `_TBD_`
- Trailer: `_TBD_`

## Technical Requirements

- Minimum OS: `Windows 10 version 1809 or later, or Windows 11`
- RAM requirement: `4 GB recommended pending final QA confirmation`
- Disk requirement: `250 MB recommended`
- Internet required for core workflow: `no`
- Capabilities used by the app: `local file selection, local file I/O, local media processing`

## Certification Notes

- known external dependencies: `FFmpeg and FFprobe can be bundled in ffmpeg\bin or resolved from PATH`
- offline behavior: `the core workflow is intended to work fully offline`
- first-run behavior: `launches directly to the local desktop UI with no sign-in and waits for a local media file`
- anything likely to confuse certification: `if FFmpeg binaries are not bundled, the user must already have ffmpeg and ffprobe available on PATH`

## Final Check

- [x] identity values copied from Partner Center
- [ ] category chosen
- [ ] hosted privacy URL is live
- [ ] screenshots match the current UI
- [ ] branded tile assets exist
- [ ] no placeholder branding remains
