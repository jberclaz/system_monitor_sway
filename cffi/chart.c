// Stacked area charts ported from chart.py.
#include "chart.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int sm_parse_color(const char *spec, SmColor *out) {
  if (!spec || !out) return -1;
  const char *s = spec;
  if (*s == '#') s++;
  size_t len = strlen(s);
  unsigned r = 0, g = 0, b = 0, a = 255;
  if (len == 8) {
    if (sscanf(s, "%2x%2x%2x%2x", &r, &g, &b, &a) != 4) return -1;
  } else if (len == 6) {
    if (sscanf(s, "%2x%2x%2x", &r, &g, &b) != 3) return -1;
  } else {
    return -1;
  }
  out->r = r / 255.0;
  out->g = g / 255.0;
  out->b = b / 255.0;
  out->a = a / 255.0;
  return 0;
}

int sm_chart_init(SmChart *c, int width, int height, const char **colors, int n,
                  double fixed_max) {
  if (!c || width <= 0 || height <= 0 || n <= 0) return -1;
  memset(c, 0, sizeof(*c));
  c->colors = calloc((size_t)n, sizeof(SmColor));
  c->data = calloc((size_t)n * (size_t)width, sizeof(double));
  if (!c->colors || !c->data) {
    sm_chart_free(c);
    return -1;
  }
  for (int i = 0; i < n; i++) {
    if (!colors || !colors[i] || sm_parse_color(colors[i], &c->colors[i]) != 0) {
      // Unknown colors degrade to mid grey rather than failing the module.
      c->colors[i] = (SmColor){0.53, 0.53, 0.53, 1.0};
    }
  }
  c->width = width;
  c->height = height;
  c->n_layers = n;
  c->fixed_max = fixed_max;
  c->count = 0;
  return 0;
}

void sm_chart_push(SmChart *c, const double *vals) {
  if (!c || !vals) return;
  double acc = 0.0;
  for (int layer = 0; layer < c->n_layers; layer++) {
    double v = vals[layer];
    if (layer == 0) {
      acc = v;
    } else if (v > 0) {
      acc += v;
    }
    double *row = c->data + (size_t)layer * (size_t)c->width;
    if (c->count < c->width) {
      row[c->count] = acc;
    } else {
      memmove(row, row + 1, (size_t)(c->width - 1) * sizeof(double));
      row[c->width - 1] = acc;
    }
  }
  if (c->count < c->width) c->count++;
}

double sm_chart_ymax(const SmChart *c) {
  if (!c) return 1.0;
  if (c->fixed_max >= 0) return c->fixed_max;
  if (c->count == 0) return 1.0;
  const double *row = c->data + (size_t)(c->n_layers - 1) * (size_t)c->width;
  double mx = row[0];
  for (int i = 1; i < c->count; i++) {
    if (row[i] > mx) mx = row[i];
  }
  // chart.py: max(1.0, 2**ceil(log(max(ymax,1e-9))/log(2))); max <= 0 -> 1.0.
  if (!(mx > 0)) return 1.0;
  return fmax(1.0, pow(2.0, ceil(log(mx) / log(2.0))));
}

void sm_chart_draw(const SmChart *c, cairo_t *cr, SmColor bg) {
  if (!c || !cr) return;
  double w = (double)c->width, h = (double)c->height;
  double ymax = sm_chart_ymax(c);

  cairo_save(cr);
  cairo_set_source_rgba(cr, bg.r, bg.g, bg.b, bg.a);
  cairo_rectangle(cr, 0, 0, w, h);
  cairo_fill(cr);

  // GNOME Chart._draw device-pixel path at scale 1.
  for (int i = c->n_layers - 1; i >= 0; i--) {
    const double *row = c->data + (size_t)i * (size_t)c->width;
    int samples = c->count - 1;
    if (samples <= 0) continue;
    double x = w - 0.25;
    cairo_move_to(cr, w, h);
    cairo_line_to(cr, x, (1 - row[samples] / ymax) * h);
    x -= 0.5;
    for (int j = samples; j >= 0; j--) {
      double y = (1 - row[j] / ymax) * h;
      cairo_line_to(cr, x, y);
      x -= 0.5;
      cairo_line_to(cr, x, y);
      x -= 0.5;
    }
    x += 0.25;
    cairo_line_to(cr, x, (1 - row[0] / ymax) * h);
    cairo_line_to(cr, x, h);
    cairo_close_path(cr);
    cairo_set_source_rgba(cr, c->colors[i].r, c->colors[i].g, c->colors[i].b,
                          c->colors[i].a);
    cairo_fill(cr);
  }
  cairo_restore(cr);
}

void sm_chart_free(SmChart *c) {
  if (!c) return;
  free(c->colors);
  free(c->data);
  memset(c, 0, sizeof(*c));
}
