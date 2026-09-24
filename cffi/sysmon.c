// system-monitor-sway as a native Waybar module (CFFI ABI v2).
//
// Waybar loads this .so in-process and hands us a GtkContainer to populate.
// We draw the same stacked area charts as chart.py into a GtkDrawingArea
// with cairo, on Waybar's own GTK thread. No overlay window, no PNG file,
// no Python at runtime, no fullscreen workaround: Sway covers Waybar (and
// with it our graphs) automatically.
//
// First cut: cpu / memory / net graphs only, no labels, no tooltips.
// All state lives in Sysmon (no globals) so multi-output bars work.
#include "waybar_cffi_module.h"

#include <glib.h>
#include <stdlib.h>
#include <string.h>

#include "chart.h"
#include "collectors.h"
#include "strip.h"

#ifndef SYSMON_VERSION
#define SYSMON_VERSION "unknown"
#endif

const size_t wbcffi_version __attribute__((visibility("default"))) = 2;

// Waybar <= some version only knows ABI v1; the loader checks this symbol
// and refuses unknown versions with a clear error. Fail closed, never draw
// garbage against a mismatched ABI.

// --- defaults (GNOME applet palette; see README) -------------------------------
static const char *CPU_COLORS[] = {"#0072b3", "#0092e6", "#00a3ff", "#002f3d",
                                   "#001d26"};
static const char *MEM_COLORS[] = {"#00b35b", "#00ff82", "#aaf5d0"};
static const char *NET_COLORS[] = {"#fce94f", "#ff6e00", "#fb74fb", "#e0006e",
                                   "#ff0000"};
static const char *DISK_COLORS[] = {"#c65000", "#ff6700"};

typedef struct {
  const char *name;
  const char **colors;
  int n_colors;
  double fixed_max;  // <0 = auto
  int refresh_ms;
} GraphSpec;

static const GraphSpec GRAPH_SPECS[] = {
    {"cpu", CPU_COLORS, 5, 100.0, 1500},
    {"memory", MEM_COLORS, 3, -1.0, 5000},
    {"net", NET_COLORS, 5, -1.0, 1000},
    {"disk", DISK_COLORS, 2, -1.0, 2000},
};
#define N_SPECS (int)(sizeof(GRAPH_SPECS) / sizeof(GRAPH_SPECS[0]))

typedef struct {
  const GraphSpec *spec;
  SmChart chart;
  int width;
  int refresh_ms;
  gint64 last_sample_us;  // 0 = never
  int pushed;             // set when the latest sample produced data
  int show_label;
  char label[32];
} Graph;

typedef struct {
  wbcffi_module *mod;
  void (*queue_update)(wbcffi_module *);
  GtkWidget *area;
  Graph graphs[N_SPECS];
  int n_graphs;
  int spacing;
  int height;
  SmColor bg;
  double font_size;
  guint timer_id;
  int interval_ms;
  int warmup_left;  // fast-tick burst filling history right after startup
  CpuState cpu;
  NetState net;
  DiskState disk;
} Sysmon;

// --- minimal JSON helpers (ABI v2 values are JSON-encoded) -------------------
// Only what our config needs: strings, numbers, arrays of strings.

static const char *cfg_raw(const wbcffi_config_entry *entries, size_t n,
                           const char *key) {
  for (size_t i = 0; i < n; i++) {
    if (entries[i].key && strcmp(entries[i].key, key) == 0) return entries[i].value;
  }
  return NULL;
}

// Unquote a JSON string in place into buf. Returns 0 on success.
// Accepts bare (unquoted) strings for tolerance.
static int json_unquote(const char *in, char *buf, size_t cap) {
  if (!in || !buf || cap == 0) return -1;
  size_t len = strlen(in);
  const char *p = in;
  size_t plen = len;
  if (len >= 2 && in[0] == '"' && in[len - 1] == '"') {
    p++;
    plen -= 2;
  }
  size_t o = 0;
  for (size_t i = 0; i < plen && o + 1 < cap; i++) {
    char ch = p[i];
    if (ch == '\\' && i + 1 < plen) {
      char e = p[++i];
      switch (e) {
        case 'n': ch = '\n'; break;
        case 't': ch = '\t'; break;
        case 'r': ch = '\r'; break;
        case 'b': ch = '\b'; break;
        case 'f': ch = '\f'; break;
        case 'u':
          // \uXXXX: ASCII fast path, anything else becomes '?'.
          if (i + 4 < plen + 1) {
            char hex[5] = {p[i + 1], p[i + 2], p[i + 3], p[i + 4], 0};
            unsigned code = 0;
            if (sscanf(hex, "%x", &code) == 1 && code < 0x80 && code >= 0x20) {
              ch = (char)code;
              i += 4;
              break;
            }
          }
          ch = '?';
          break;
        default: ch = e; break;
      }
    }
    buf[o++] = ch;
  }
  buf[o] = 0;
  return 0;
}

static int cfg_int(const wbcffi_config_entry *entries, size_t n, const char *key,
                   int fallback) {
  const char *raw = cfg_raw(entries, n, key);
  if (!raw) return fallback;
  char *end = NULL;
  long v = strtol(raw, &end, 10);
  if (end == raw) return fallback;
  return (int)v;
}

static int cfg_bool(const wbcffi_config_entry *entries, size_t n, const char *key,
                    int fallback) {
  const char *raw = cfg_raw(entries, n, key);
  if (!raw) return fallback;
  if (strcmp(raw, "true") == 0 || strcmp(raw, "1") == 0) return 1;
  if (strcmp(raw, "false") == 0 || strcmp(raw, "0") == 0) return 0;
  return fallback;
}

// Collects quoted strings from a JSON array value into out[].
// Returns the count (<= cap). Non-array or empty -> -1 (caller keeps default).
static int cfg_str_array(const wbcffi_config_entry *entries, size_t n,
                         const char *key, char out[][32], int cap) {
  const char *raw = cfg_raw(entries, n, key);
  if (!raw || raw[0] != '[') return -1;
  int count = 0;
  const char *p = raw;
  while (count < cap && (p = strchr(p, '"')) != NULL) {
    p++;
    const char *q = p;
    while (*q && (*q != '"' || *(q - 1) == '\\')) q++;
    if (!*q) break;
    size_t len = (size_t)(q - p);
    if (len > 0 && len < 32) {
      char tmp[64];
      if (len >= sizeof(tmp)) len = sizeof(tmp) - 1;
      memcpy(tmp, p, len);
      tmp[len] = 0;
      char unq[32];
      if (json_unquote(tmp, unq, sizeof(unq)) == 0) {
        strncpy(out[count], unq, 32);
        out[count][31] = 0;
        count++;
      }
    }
    p = q + 1;
  }
  return count == 0 ? -1 : count;
}

static int sm_debug(void) {
  static int cached = -1;
  if (cached < 0) cached = getenv("WAYBAR_SYSMON_DEBUG") ? 1 : 0;
  return cached;
}

// --- sampling ----------------------------------------------------------------

// refresh gating is bypassed while warming so every graph fills quickly;
// deltas over 100ms are noisier but valid, and steady-state rates apply after.
#define WARMUP_TICKS 60
#define WARMUP_MS 100

static void sample_one(Sysmon *sm, Graph *g) {
  if (strcmp(g->spec->name, "cpu") == 0) {
    double vals[5];
    if (cpu_sample(&sm->cpu, vals)) {
      sm_chart_push(&g->chart, vals);
      g->pushed = 1;
    }
  } else if (strcmp(g->spec->name, "memory") == 0) {
    double vals[3];
    if (mem_sample(vals)) {
      sm_chart_push(&g->chart, vals);
      g->pushed = 1;
    }
    } else if (strcmp(g->spec->name, "net") == 0) {
      double vals[5];
      if (net_sample(&sm->net, vals)) {
        sm_chart_push(&g->chart, vals);
        g->pushed = 1;
      }
    } else if (strcmp(g->spec->name, "disk") == 0) {
      double vals[2];
      if (disk_sample(&sm->disk, vals)) {
        sm_chart_push(&g->chart, vals);
        g->pushed = 1;
      }
    }
}

static void sample_graphs(Sysmon *sm) {
  gint64 now = g_get_monotonic_time();
  int warming = sm->warmup_left > 0;
  for (int i = 0; i < sm->n_graphs; i++) {
    Graph *g = &sm->graphs[i];
    g->pushed = 0;
    if (!warming && g->last_sample_us != 0 &&
        now - g->last_sample_us < (gint64)g->refresh_ms * 1000)
      continue;
    g->last_sample_us = now;
    sample_one(sm, g);
    if (sm_debug()) {
      fprintf(stderr, "sysmon: sample %-6s pushed=%d count=%d ymax=%.3g\n",
              g->spec->name, g->pushed, g->chart.count,
              sm_chart_ymax(&g->chart));
    }
  }
  if (warming) sm->warmup_left--;
}

static gboolean on_tick(gpointer data) {
  Sysmon *sm = data;
  sample_graphs(sm);
  if (sm->warmup_left == 0 && sm->timer_id) {
    // Warmup done: settle into the configured steady-state interval.
    g_source_remove(sm->timer_id);
    sm->timer_id = g_timeout_add((guint)sm->interval_ms, on_tick, sm);
    // Keep timer_id valid; mark settled with warmup_left = -1.
    sm->warmup_left = -1;
    if (sm_debug()) fprintf(stderr, "sysmon: warmup done\n");
  }
  // NOTE: gtk_widget_queue_draw() alone never produces a repaint inside
  // Waybar's bar window (its frame clock doesn't schedule our paints), so
  // invalidate the widget's window directly and process the update
  // synchronously. queue_draw_area (not manual gdk rect math: this area is
  // windowless and draws on an ancestor's window) gets the clip right; the
  // strip is ~300x30px so the forced paint is trivially cheap.
  // gdk_window_process_updates is deprecated (upstream prefers frame-clock
  // scheduling) but remains the only mechanism that paints here.
  GtkAllocation alloc;
  gtk_widget_get_allocation(sm->area, &alloc);
  gtk_widget_queue_draw_area(sm->area, 0, 0, alloc.width, alloc.height);
  GdkWindow *win = gtk_widget_get_window(sm->area);
  if (win) {
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
    gdk_window_process_updates(win, TRUE);
#pragma GCC diagnostic pop
  }
  return G_SOURCE_CONTINUE;
}

static gboolean on_draw(GtkWidget *widget, cairo_t *cr, gpointer data) {
  Sysmon *sm = data;
  if (sm_debug()) {
    GtkAllocation alloc;
    gtk_widget_get_allocation(widget, &alloc);
    fprintf(stderr, "sysmon: draw alloc=%dx%d graphs=%d\n",
            alloc.width, alloc.height, sm->n_graphs);
  }
  double x = 0;
  for (int i = 0; i < sm->n_graphs; i++) {
    if (i > 0) x += sm->spacing;
    if (sm->graphs[i].show_label) {
      cairo_save(cr);
      cairo_translate(cr, x, 0);
      sm_draw_label(cr, sm->graphs[i].label, (double)sm->height, SM_LABEL_RGBA,
                    sm->font_size);
      cairo_restore(cr);
      x += SM_LABEL_PX;
    }
    cairo_save(cr);
    cairo_translate(cr, x, 0);
    sm_chart_draw(&sm->graphs[i].chart, cr, sm->bg);
    cairo_restore(cr);
    x += sm->graphs[i].width;
  }
  return FALSE;
}

// --- CFFI entry points --------------------------------------------------------
#define WBCFFI_EXPORT __attribute__((visibility("default")))

WBCFFI_EXPORT void *wbcffi_init(const wbcffi_init_info *init_info,
                  const wbcffi_config_entry *config_entries,
                  size_t config_entries_len) {
  if (!init_info || !init_info->get_root_widget || !init_info->queue_update)
    return NULL;

  Sysmon *sm = calloc(1, sizeof(*sm));
  if (!sm) return NULL;
  sm->mod = init_info->obj;
  sm->queue_update = init_info->queue_update;

  int graph_width = cfg_int(config_entries, config_entries_len, "graph_width", 100);
  if (graph_width < 10) graph_width = 10;
  if (graph_width > 2000) graph_width = 2000;
  sm->spacing = cfg_int(config_entries, config_entries_len, "spacing", 4);
  if (sm->spacing < 0) sm->spacing = 0;
  if (sm->spacing > 64) sm->spacing = 64;
  sm->height = cfg_int(config_entries, config_entries_len, "height", 30);
  if (sm->height < 8) sm->height = 8;
  if (sm->height > 256) sm->height = 256;
  int interval_ms =
      cfg_int(config_entries, config_entries_len, "interval_ms", 1000);
  if (interval_ms < 250) interval_ms = 250;

  char bg_raw[32] = "#ffffff16";
  const char *bg_cfg = cfg_raw(config_entries, config_entries_len, "background");
  if (bg_cfg) {
    char unq[32];
    if (json_unquote(bg_cfg, unq, sizeof(unq)) == 0 && unq[0]) {
      strncpy(bg_raw, unq, sizeof(bg_raw));
      bg_raw[sizeof(bg_raw) - 1] = 0;
    }
  }
  if (sm_parse_color(bg_raw, &sm->bg) != 0)
    sm_parse_color("#ffffff16", &sm->bg);

  // Label defaults mirror the old overlay (memory shortens to "mem").
  static const char *default_labels[N_SPECS] = {"cpu", "mem", "net", "disk"};
  int show_label = cfg_bool(config_entries, config_entries_len, "show_label", 1);
  // Enabled graphs, in canonical order.
  char wanted[N_SPECS][32];
  memset(wanted, 0, sizeof(wanted));
  int n_wanted =
      cfg_str_array(config_entries, config_entries_len, "graphs", wanted, N_SPECS);
  for (int i = 0; i < N_SPECS && sm->n_graphs < N_SPECS; i++) {
    if (n_wanted > 0) {
      int found = 0;
      for (int k = 0; k < n_wanted; k++) {
        if (strcmp(wanted[k], GRAPH_SPECS[i].name) == 0) {
          found = 1;
          break;
        }
      }
      if (!found) continue;
    }
    Graph *g = &sm->graphs[sm->n_graphs++];
    g->spec = &GRAPH_SPECS[i];
    g->width = graph_width;
    g->show_label = show_label;
    char lkey[48];
    snprintf(lkey, sizeof(lkey), "label_%s", GRAPH_SPECS[i].name);
    const char *lraw = cfg_raw(config_entries, config_entries_len, lkey);
    char lunq[32] = {0};
    if (lraw && json_unquote(lraw, lunq, sizeof(lunq)) == 0 && lunq[0]) {
      strncpy(g->label, lunq, sizeof(g->label));
    } else {
      strncpy(g->label, default_labels[i], sizeof(g->label));
    }
    g->label[sizeof(g->label) - 1] = 0;
    char rkey[48];
    snprintf(rkey, sizeof(rkey), "refresh_%s_ms", GRAPH_SPECS[i].name);
    g->refresh_ms = cfg_int(config_entries, config_entries_len, rkey,
                            GRAPH_SPECS[i].refresh_ms);
    if (g->refresh_ms < 250) g->refresh_ms = 250;
    // Per-graph colors key, e.g. "colors_cpu": ["#...", ...].
    char ckey[48];
    snprintf(ckey, sizeof(ckey), "colors_%s", GRAPH_SPECS[i].name);
    char cbufs[8][32];
    const char **colors = GRAPH_SPECS[i].colors;
    int n_colors = GRAPH_SPECS[i].n_colors;
    char *cptrs[8];
    int n_got = cfg_str_array(config_entries, config_entries_len, ckey, cbufs, 8);
    if (n_got == GRAPH_SPECS[i].n_colors) {
      for (int k = 0; k < n_got; k++) cptrs[k] = cbufs[k];
      colors = (const char **)cptrs;
      n_colors = n_got;
    }
    if (sm_chart_init(&g->chart, g->width, sm->height, colors, n_colors,
                      GRAPH_SPECS[i].fixed_max) != 0) {
      sm->n_graphs--;
      continue;
    }
  }
  if (sm->n_graphs == 0) {
    free(sm);
    return NULL;
  }

  GtkContainer *root = init_info->get_root_widget(init_info->obj);
  if (!root) {
    for (int i = 0; i < sm->n_graphs; i++) sm_chart_free(&sm->graphs[i].chart);
    free(sm);
    return NULL;
  }
  GtkWidget *box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
  sm->area = gtk_drawing_area_new();
  sm->font_size =
      sm->height < 14 ? (double)sm->height * 0.7 : SM_LABEL_FONT_SIZE;
  int total_w = 0;
  for (int i = 0; i < sm->n_graphs; i++) {
    if (i > 0) total_w += sm->spacing;
    total_w += sm_element_width(sm->graphs[i].show_label, sm->graphs[i].width);
  }
  gtk_widget_set_size_request(sm->area, total_w, sm->height);
  g_signal_connect(sm->area, "draw", G_CALLBACK(on_draw), sm);
  gtk_container_add(GTK_CONTAINER(box), sm->area);
  gtk_container_add(root, box);
  gtk_widget_show_all(box);

  // Prime differential samplers, then burst-fill history at 100ms so the
  // charts arrive populated instead of growing from an empty sliver.
  sm->interval_ms = interval_ms;
  sm->warmup_left = WARMUP_TICKS;
  sample_graphs(sm);
  sm->timer_id = g_timeout_add(WARMUP_MS, on_tick, sm);
  if (sm_debug()) {
    fprintf(stderr, "sysmon: init v%s graphs=%d size=%dx%d inst=%p\n",
            SYSMON_VERSION, sm->n_graphs, total_w, sm->height, (void *)sm);
  }
  return sm;
}

WBCFFI_EXPORT void wbcffi_deinit(void *instance) {
  Sysmon *sm = instance;
  if (sm_debug()) fprintf(stderr, "sysmon: deinit inst=%p\n", (void *)sm);
  if (!sm) return;
  if (sm->timer_id) g_source_remove(sm->timer_id);
  for (int i = 0; i < sm->n_graphs; i++) sm_chart_free(&sm->graphs[i].chart);
  free(sm);
}

WBCFFI_EXPORT void wbcffi_update(void *instance) {
  Sysmon *sm = instance;
  if (sm && sm->area) gtk_widget_queue_draw(sm->area);
}

WBCFFI_EXPORT void wbcffi_refresh(void *instance, int signal) {
  (void)signal;
  wbcffi_update(instance);
}

WBCFFI_EXPORT void wbcffi_doaction(void *instance, const char *action_name) {
  (void)instance;
  (void)action_name;
}
