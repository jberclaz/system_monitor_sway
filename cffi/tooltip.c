// Tooltip text formatters ported from system_monitor_sway.py (TIP_FORMATTERS).
// Only the four graphs the native module implements: cpu / memory / net /
// disk. Units follow collectors.h; net needs care: the old Python overlay
// formatted ~KiB/s while net_sample() reports B/s, so divide by 1024 first.
#include "tooltip.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

// Appends `src` (+ optional newline separator) to the cursor. Returns 0,
// -1 when the tail does not fit (out stays NUL-terminated).
static int emit(char *out, size_t cap, size_t *pos, int first, const char *src) {
  size_t need = strlen(src) + (first ? 0 : 1);
  if (*pos + need + 1 > cap) return -1;
  if (!first) out[(*pos)++] = '\n';
  memcpy(out + *pos, src, strlen(src));
  *pos += strlen(src);
  out[*pos] = 0;
  return 0;
}

// Old _net_rate() over KiB/s: <1024 -> int KiB/s; <1048576 -> %.3g MiB/s;
// else %.3g GiB/s.
static void fmt_rate(double kib_s, char *buf, size_t cap) {
  if (kib_s < 1024.0) {
    snprintf(buf, cap, "%lld KiB/s", llround(kib_s));
  } else if (kib_s < 1048576.0) {
    snprintf(buf, cap, "%.3g MiB/s", kib_s / 1024.0);
  } else {
    snprintf(buf, cap, "%.3g GiB/s", kib_s / 1048576.0);
  }
}

// Old _disk_mib(): <10 -> one decimal, else int.
static void fmt_mib(double v, char *buf, size_t cap) {
  if (v < 10.0) {
    snprintf(buf, cap, "%.1f", round(v * 10.0) / 10.0);
  } else {
    snprintf(buf, cap, "%lld", llround(v));
  }
}

int sm_tooltip_text(const char *name, const double *vals, char *out,
                    size_t cap) {
  if (!name || !vals || !out || cap == 0) return -1;
  out[0] = 0;
  size_t pos = 0;

  if (strcmp(name, "cpu") == 0) {
    static const char *names[5] = {"user", "system", "nice", "iowait", "other"};
    for (int i = 0; i < 5; i++) {
      char line[64];
      snprintf(line, sizeof(line), "%s  %lld %%", names[i], llround(vals[i]));
      if (emit(out, cap, &pos, i == 0, line) != 0) return -1;
    }
    return 0;
  }
  if (strcmp(name, "memory") == 0) {
    static const char *names[3] = {"program", "buffer", "cache"};
    for (int i = 0; i < 3; i++) {
      char line[64];
      snprintf(line, sizeof(line), "%s  %lld %%", names[i],
               llround(vals[i] * 100.0));
      if (emit(out, cap, &pos, i == 0, line) != 0) return -1;
    }
    return 0;
  }
  if (strcmp(name, "net") == 0) {
    char down[32], up[32];
    fmt_rate(vals[0] / 1024.0, down, sizeof(down));
    fmt_rate(vals[2] / 1024.0, up, sizeof(up));
    char line[4][64];
    snprintf(line[0], sizeof(line[0]), "down  %s", down);
    snprintf(line[1], sizeof(line[1]), "downerrors  %lld /s",
             (long long)vals[1]);
    snprintf(line[2], sizeof(line[2]), "up  %s", up);
    snprintf(line[3], sizeof(line[3]), "uperrors  %lld /s",
             (long long)vals[3]);
    char last[64];
    snprintf(last, sizeof(last), "collisions  %lld /s", (long long)vals[4]);
    for (int i = 0; i < 4; i++) {
      if (emit(out, cap, &pos, i == 0, line[i]) != 0) return -1;
    }
    if (emit(out, cap, &pos, 0, last) != 0) return -1;
    return 0;
  }
  if (strcmp(name, "disk") == 0) {
    char r[32], w[32];
    fmt_mib(vals[0], r, sizeof(r));
    fmt_mib(vals[1], w, sizeof(w));
    char line[2][64];
    snprintf(line[0], sizeof(line[0]), "read  %s MiB/s", r);
    snprintf(line[1], sizeof(line[1]), "write  %s MiB/s", w);
    if (emit(out, cap, &pos, 1, line[0]) != 0) return -1;
    if (emit(out, cap, &pos, 0, line[1]) != 0) return -1;
    return 0;
  }
  return -1;
}
