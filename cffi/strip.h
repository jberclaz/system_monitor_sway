// Strip layout + label drawing shared by the module and test harnesses.
// Labels mirror the old overlay (#bbbbbb monospace) but render rotated 90
// degrees counter-clockwise (read bottom-to-top) in a narrow slot, so the
// strip stays compact.
#pragma once

#include <cairo.h>

#include "chart.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SM_LABEL_PX 14
#define SM_LABEL_FONT_SIZE 10.0

// Label slot color (#bbbbbb).
extern const SmColor SM_LABEL_RGBA;

// Width of one element: label slot (if shown) + chart.
int sm_element_width(int show_label, int graph_width);

// Draws `text` rotated 90 deg CCW, centered in a SM_LABEL_PX-wide slot at
// the current origin, for a strip of `height` px. Text longer than the
// strip height is truncated. No-op on NULL/empty text.
void sm_draw_label(cairo_t *cr, const char *text, double height, SmColor color,
                   double font_size);

#ifdef __cplusplus
}
#endif
