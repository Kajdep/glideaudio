# GlideAudio

## Product Summary

GlideAudio is a Windows desktop app for cleaning, leveling, and improving spoken audio in video or audio files.

It should help users:

- reduce background noise and hiss
- tame room echo and harshness
- normalize loudness for platform delivery
- improve vocal clarity for tutorials, talking-head videos, podcasts, and social clips
- export either cleaned audio-only files or cleaned video files with the repaired audio muxed back in

The product should feel like part of the same Glide family as GlideConvert, GlideLooper, GlideBlend, GlidePrep, GlideShorts, and GlideCaps.

## Positioning

Core promise:

`Clean spoken audio fast, keep the workflow local, and avoid dragging a simple fix through a full editor.`

This is not a DAW. It is a focused repair and polish tool.

## Best Use Cases

- cleaning voice audio in screen recordings
- repairing talking-head or webcam videos
- improving tutorial narration
- leveling creator voice tracks before captioning or clipping
- batch-fixing rough client deliverables

## Product Shape

The workflow should be:

`Load -> Analyze -> Tune Cleanup -> A/B Preview -> Export`

For video files, GlideAudio should preserve the picture and replace the source audio with the cleaned result during export.

## MVP Scope

### 1. Source Intake

- drag/drop or file picker
- accept common video and audio formats
- show duration, resolution, audio presence, sample rate, and channel count
- support a batch queue, but keep editing single-source first

### 2. Audio Analysis

Show a concise diagnostics pass:

- estimated noise floor
- peak level
- average loudness
- clipping risk
- speech presence

The UI should not pretend to be a mastering suite. Keep the readout simple and actionable.

### 3. Cleanup Modules

Expose a small, understandable chain:

- `Noise Reduction`
- `Voice Clarity`
- `De-Echo`
- `De-Hum`
- `Leveling`
- `Limiter`

Each module should have a simple intensity control rather than a dense engineer panel.

### 4. Presets

Built-in presets:

- Clean Voice
- Noisy Room
- Screen Recording Voiceover
- Podcast Speech
- Social Clip Speech
- Loudness Match Only

### 5. Preview

- short before/after playback loop
- waveform or loudness strip view
- toggle original vs cleaned signal
- no full timeline editor

### 6. Export

- export cleaned WAV, MP3, or AAC
- export repaired MP4 with cleaned audio
- loudness targets for creator workflows such as YouTube, podcast, and social delivery

## Recommended Tech Direction

- Python 3 desktop app
- `customtkinter` for the Glide UI family
- `ffmpeg` / `ffprobe` for decode, encode, mux, and filter chains
- Python-side analysis for loudness/noise estimation
- optional FFmpeg `arnndn`, `afftdn`, `loudnorm`, `dynaudnorm`, EQ, and limiter filters

Keep the first version practical and reliable. Do not require cloud processing for the core workflow.

## UX Direction

Use the same Glide family direction:

- dark, focused desktop UI
- large source panel
- concise copy
- one clear primary action per stage
- preview-first rather than settings-heavy

Avoid:

- giant mixer-style panels
- multitrack metaphors
- plugin-like complexity
- hidden auto-processing that cannot be reviewed

## Likely MVP Layout

### Source Section

- source metadata
- input/output path controls
- source preview transport

### Cleanup Section

- preset selector
- module intensity sliders
- concise diagnostics

### Preview Section

- before/after toggle
- short loop playback
- loudness and clipping summary

### Export Section

- export mode: audio-only or repaired video
- format target
- loudness target
- output path

## Non-Goals

- no multitrack editing
- no music production workflow
- no full podcast editor
- no transcription-driven cutting in v1

That last item belongs in GlidePace.

## Stronger Future Versions

- auto voice isolate
- background music ducking
- speech-only enhancement mode
- batch preset runs across large folders
- voice repair profiles by microphone type
- optional AI cleanup pack for higher-end machines

## Build Guidance For Another LLM

Implement in this order:

1. app shell and source loader
2. metadata and diagnostics panel
3. practical cleanup preset system
4. short A/B preview loop
5. export cleaned audio and repaired video
6. batch queue after single-file flow feels solid

Important constraints:

- keep controls minimal
- prefer understandable presets over raw DSP jargon
- preserve the Glide family feel
- do not let the tool drift into DAW territory
