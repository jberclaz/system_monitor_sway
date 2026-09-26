// Per-graph hover tooltip text (see tooltip.c).
// Pure string formatting, no GTK dependency, so unit tests cover it.
// Value layouts mirror collectors.h: cpu = 5 percentages, memory =
// 3 fractions, net = 5 B/s counters, disk = 2 MiB/s rates.
#pragma once

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// Formats the tooltip for graph `name` ("cpu", "memory", "net", "disk")
// from its latest sample `vals` into `out` (always NUL-terminated).
// Returns 0 on success, -1 on NULL/bad-name/truncation.
int sm_tooltip_text(const char *name, const double *vals, char *out,
                    size_t cap);

#ifdef __cplusplus
}
#endif
