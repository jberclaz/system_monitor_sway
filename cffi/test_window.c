// Visual test harness: same charts + collectors + draw code as sysmon.c,
// but in a plain GtkWindow (which grim CAN capture; grim cannot see
// layer-shell surfaces on this setup). Not shipped; `make visualtest`.
#include <gtk/gtk.h>

#include "chart.h"
#include "collectors.h"

static const char *CPU_COLORS[] = {"#0072b3", "#0092e6", "#00a3ff", "#002f3d",
                                   "#001d26"};
static const char *MEM_COLORS[] = {"#00b35b", "#00ff82", "#aaf5d0"};
static const char *NET_COLORS[] = {"#fce94f", "#ff6e00", "#fb74fb", "#e0006e",
                                   "#ff0000"};

typedef struct {
  GtkWidget *area;
  SmChart charts[3];
  SmColor bg;
  CpuState cpu;
  NetState net;
  int ticks;
} App;

static gboolean on_draw(GtkWidget *w, cairo_t *cr, gpointer data) {
  (void)w;
  App *app = data;
  int widths[3] = {100, 100, 100};
  double x = 0;
  for (int i = 0; i < 3; i++) {
    if (i) x += 4;
    cairo_save(cr);
    cairo_translate(cr, x, 0);
    sm_chart_draw(&app->charts[i], cr, app->bg);
    cairo_restore(cr);
    x += widths[i];
  }
  return FALSE;
}

static void snapshot(App *app, const char *path) {
  cairo_surface_t *s = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 308, 30);
  cairo_t *cr = cairo_create(s);
  // Transparent base like a bar; charts paint their own bg.
  cairo_set_source_rgba(cr, 0.21, 0.21, 0.21, 1.0);
  cairo_paint(cr);
  int widths[3] = {100, 100, 100};
  double x = 0;
  for (int i = 0; i < 3; i++) {
    if (i) x += 4;
    cairo_save(cr);
    cairo_translate(cr, x, 0);
    sm_chart_draw(&app->charts[i], cr, app->bg);
    cairo_restore(cr);
    x += widths[i];
  }
  cairo_surface_write_to_png(s, path);
  cairo_destroy(cr);
  cairo_surface_destroy(s);
}

static gboolean on_tick(gpointer data) {
  App *app = data;
  double v5[5], v3[3];
  if (cpu_sample(&app->cpu, v5)) sm_chart_push(&app->charts[0], v5);
  if (mem_sample(v3)) sm_chart_push(&app->charts[1], v3);
  if (net_sample(&app->net, v5)) sm_chart_push(&app->charts[2], v5);
  gtk_widget_queue_draw(app->area);
  // Snapshot the exact composite to PNG every 10s for headless verification.
  if (++app->ticks % 100 == 0) {
    char path[64];
    snprintf(path, sizeof(path), "/tmp/wbtest/harness-%d.png", app->ticks);
    snapshot(app, path);
  }
  return G_SOURCE_CONTINUE;
}

int main(int argc, char **argv) {
  gtk_init(&argc, &argv);
  App app;
  memset(&app, 0, sizeof(app));
  sm_parse_color("#ffffff16", &app.bg);
  sm_chart_init(&app.charts[0], 100, 30, CPU_COLORS, 5, 100.0);
  sm_chart_init(&app.charts[1], 100, 30, MEM_COLORS, 3, -1.0);
  sm_chart_init(&app.charts[2], 100, 30, NET_COLORS, 5, -1.0);
  GtkWidget *win = gtk_window_new(GTK_WINDOW_TOPLEVEL);
  gtk_window_set_title(GTK_WINDOW(win), "sysmon-visualtest");
  gtk_window_set_default_size(GTK_WINDOW(win), 308, 30);
  gtk_window_set_decorated(GTK_WINDOW(win), FALSE);
  gtk_window_stick(GTK_WINDOW(win));
  gtk_window_set_keep_above(GTK_WINDOW(win), TRUE);
  app.area = gtk_drawing_area_new();
  gtk_widget_set_size_request(app.area, 308, 30);
  g_signal_connect(app.area, "draw", G_CALLBACK(on_draw), &app);
  gtk_container_add(GTK_CONTAINER(win), app.area);
  g_signal_connect(win, "destroy", G_CALLBACK(gtk_main_quit), NULL);
  gtk_widget_show_all(win);
  g_timeout_add(100, on_tick, &app);
  gtk_main();
  return 0;
}
