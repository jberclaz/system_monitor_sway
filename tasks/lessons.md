# Lessons (project: system_monitor_sway)

## Shell safety
- NEVER put `pkill -f <pattern>` and the literal target path in the SAME
  shell invocation: pkill matches the invoking shell's own cmdline and kills
  it (looks like a tool timeout). Use bracket patterns (`pkill -f "[w]btest"`)
  AND keep pkill in a separate tool call from any literal target path.

## Waybar CFFI module (cffi/)
- `wbcffi_deinit` is MANDATORY: if the `.so` doesn't export it (e.g. eaten by
  `-fvisibility=hidden`), Waybar logs `Disabling module ... Missing
  wbcffi_deinit` and silently continues without the module. Always `nm -D`
  the final binary for all 5 functions + `wbcffi_version`.
- Keep `-fvisibility=hidden` + explicit default-visibility on the ABI symbols
  so the plugin exports only its contract.
- `gtk_widget_queue_draw()` alone never repaints inside Waybar's bar window
  (frame clock doesn't schedule it). Working mechanism: `gtk_widget_queue_draw_area`
  on the widget + `gdk_window_process_updates` on its window (deprecated but
  the only thing that paints; pragma-suppress the warning with a comment).
  Do NOT hand-roll clip rects with translate_coordinates for windowless
  widgets (ancestor-window coordinate mismatch) — use queue_draw_area.
- Charts fill right-to-left with history; a fresh start shows slivers for
  minutes (mem: 100 x 5s). Ship a warmup burst (fast ticks bypassing refresh
  gating, then re-arm steady interval) so first paint is useful.
- Differential samplers must prime (first call: store + return no-data).

## Testing GUI-on-compositor code here
- grim CANNOT capture layer-shell surfaces on this setup (even the real
  Waybar is invisible to it). Verify via: Waybar stderr (module load, sample
  counts, draw counts), in-process offscreen snapshots, standalone GtkWindow
  harness (grim CAN see normal windows), and `swaymsg -t get_tree`.
- wlsunset (3500K here) shifts screenshot colors; never assert absolute RGB
  from screenshots without accounting for it.
- Only ONE test bar instance at a time: stacked exclusive-zone bars
  contaminate every pixel assertion. Always `ps -C waybar` before shooting.
- Live collectors vary (idle CPU renders ~empty, net is bursty): prove fills
  with synthetic load (`sha1sum /dev/zero`, traffic) or synthetic values, and
  cross-check C history against chart.py reference values in unit tests.
