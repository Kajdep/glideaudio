# GlideAudio TODO

## Current

- [ ] Harden export validation and failure handling
  Linear: `ALL-46`
  Improve overwrite behavior, surface codec and path errors clearly, and verify produced files before reporting success.

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

## Queue

- [ ] Persist session settings
  Linear: `ALL-47`
  Save last-used preset, preview length, loudness target, output folder, and export mode between launches.

- [ ] Finish packaging and release assets
  Linear: `ALL-48`
  Add branded icon assets, privacy policy, store collateral, and a final Windows release build pass.

- [ ] Improve diagnostics and preset suggestions
  Linear: `ALL-49`
  Make the speech/noise analysis more trustworthy and use it to suggest a starting preset automatically.

- [ ] Add batch queue support
  Linear: `ALL-50`
  Support multiple source files with a simple queue so repeated cleanup/export runs do not require one-file-at-a-time setup.
