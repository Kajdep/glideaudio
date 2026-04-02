# GlideAudio TODO

## Current

- [ ] Add better preview transport
  Linear: `ALL-44`
  Add play/pause controls directly to the preview cards, improve playback-state feedback, and keep the A/B listening flow obvious.

## Done

- [x] Stabilize source and A/B preview rendering
  Linear: `ALL-43`
  Flattened the rendered preview surfaces, fixed the nested-card look, and improved readability across common window widths.

## Queue

- [ ] Tune cleanup presets against real voice samples
  Linear: `ALL-45`
  Validate the FFmpeg cleanup chain on clean speech, noisy-room speech, and audio-only sources, then retune preset defaults from actual results.

- [ ] Harden export validation and failure handling
  Linear: `ALL-46`
  Improve overwrite behavior, surface codec and path errors clearly, and verify produced files before reporting success.

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
