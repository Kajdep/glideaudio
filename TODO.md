# GlideAudio TODO

## Current

- [ ] Finish packaging and release assets
  Linear: `ALL-48`
  Add branded icon assets, privacy policy, store collateral, and a final Windows release build pass.

## Done

- [x] Stabilize source and A/B preview rendering
  Linear: `ALL-43`
  Flattened the rendered preview surfaces, fixed the nested-card look, and improved readability across common window widths.

- [x] Add better preview transport
  Linear: `ALL-44`
  Added per-card play/pause controls, stop/reset transport actions, clearer preview-state feedback, and more obvious A/B listening flow.

- [x] Tune cleanup presets against real voice samples
  Linear: `ALL-45`
  Retuned the cleanup presets and FFmpeg chain against clean speech, noisy-room speech, and audio-only samples so the defaults stay creator-friendly instead of DAW-heavy.

- [x] Harden export validation and failure handling
  Linear: `ALL-46`
  Added explicit overwrite confirmation, verified temp renders before success, clearer FFmpeg/path failures, and safer repaired-video export checks.

- [x] Improve diagnostics and preset suggestions
  Linear: `ALL-49`
  Strengthened the analysis heuristics, added a safer starting-preset recommendation, and reduced misleading speech/noise guesses.

- [x] Persist session settings
  Linear: `ALL-47`
  GlideAudio now remembers the key session choices between launches so creator workflows resume where they left off.

- [x] Add batch queue support
  Linear: `ALL-50`
  Added a simple batch queue with per-item state, current-file queuing, selection/loading, and safe export-path reuse for repeated runs.

## Queue
