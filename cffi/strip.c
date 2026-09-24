// Strip layout + label drawing (see strip.h).
#include "strip.h"

#include <math.h>
#include <string.h>

const SmColor SM_LABEL_RGBA = {0xBB / 255.0, 0xBB / 255.0, 0xBB / 255.0, 1.0};

int sm_element_width(int show_label, int graph_width) {
  return (show_label ? SM_LABEL_PX : 0) + graph_width;
}

void sm_draw_label(cairo_t *cr, const char *text, double height, SmColor color,
                   double font_size) {
  if (!cr || !text || !*text || font_size <= 0 || height <= 0) return;
  cairo_save(cr);
  cairo_select_font_face(cr, "monospace", CAIRO_FONT_SLANT_NORMAL,
                         CAIRO_FONT_WEIGHT_NORMAL);
  cairo_set_font_size(cr, font_size);
  // Truncate to what fits the strip height (monospace: even share each).
  char buf[32];
  size_t len = strlen(text);
  if (len >= sizeof(buf)) len = sizeof(buf) - 1;
  memcpy(buf, text, len);
  buf[len] = 0;
  cairo_text_extents_t ext;
  cairo_text_extents(cr, buf, &ext);
  while (len > 1 && ext.width > height) {
    buf[--len] = 0;
    cairo_text_extents(cr, buf, &ext);
  }
  // Center of the slot, then rotate so text reads bottom-to-top.
  cairo_translate(cr, SM_LABEL_PX / 2.0, height / 2.0);
  cairo_rotate(cr, -M_PI_2);
  cairo_text_extents(cr, buf, &ext);
  cairo_move_to(cr, -ext.width / 2.0 - ext.x_bearing, ext.height / 2.0);
  cairo_set_source_rgba(cr, color.r, color.g, color.b, color.a);
  cairo_show_text(cr, buf);
  cairo_restore(cr);
}
