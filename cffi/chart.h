// Stacked area charts ported from chart.py (StackedChart).
// Matches gnome-shell-system-monitor-applet Chart._draw semantics:
// layer 0 accumulates its raw value, deeper layers stack only positive
// values; auto ymax snaps to the next power of two (>= 1.0).
#pragma once

#include <cairo.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  double r, g, b, a;
} SmColor;

// Use fixed_max < 0 for auto-scaling.
typedef struct {
  int width;
  int height;
  int n_layers;
  SmColor *colors;  // n_layers
  double fixed_max;
  double *data;  // n_layers * width, valid prefix length = count
  int count;
} SmChart;

// colors: n "#rrggbb" or "#rrggbbaa" strings. Returns 0 on success.
int sm_chart_init(SmChart *c, int width, int height, const char **colors, int n,
                  double fixed_max);
void sm_chart_push(SmChart *c, const double *vals);
double sm_chart_ymax(const SmChart *c);
// Draws into the current cairo transform at logical size width x height.
void sm_chart_draw(const SmChart *c, cairo_t *cr, SmColor bg);
void sm_chart_free(SmChart *c);

// Parses "#rrggbb" / "#rrggbbaa" (with or without '#'). Returns 0 on success.
int sm_parse_color(const char *spec, SmColor *out);

#ifdef __cplusplus
}
#endif
