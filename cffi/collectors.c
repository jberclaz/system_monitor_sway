// /proc-based cpu / memory / net samplers (see collectors.h).
#include "collectors.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

double sm_mono_seconds(void) {
  struct timespec ts;
  if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return -1.0;
  return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

// --- cpu -----------------------------------------------------------------

static int read_cpu_fields(unsigned long long f[5]) {
  FILE *fp = fopen("/proc/stat", "r");
  if (!fp) return -1;
  char line[512];
  int rc = -1;
  if (fgets(line, sizeof(line), fp) && strncmp(line, "cpu ", 4) == 0) {
    // fields: user nice system idle iowait (rest ignored)
    unsigned long long u = 0, n = 0, s = 0, id = 0, io = 0;
    if (sscanf(line + 4, "%llu %llu %llu %llu %llu", &u, &n, &s, &id, &io) == 5) {
      f[0] = u;
      f[1] = s;
      f[2] = n;
      f[3] = id;
      f[4] = io;
      rc = 0;
    }
  }
  fclose(fp);
  return rc;
}

int cpu_sample(CpuState *s, double out[5]) {
  if (!s || !out) return 0;
  unsigned long long cur[5];
  if (read_cpu_fields(cur) != 0) return 0;
  if (!s->have_last) {
    memcpy(s->last, cur, sizeof(cur));
    s->have_last = 1;
    return 0;
  }
  unsigned long long delta = 0;
  double usage[5];
  for (int i = 0; i < 5; i++) delta += cur[i] - s->last[i];
  if (delta == 0) return 0;
  for (int i = 0; i < 5; i++) {
    usage[i] = 100.0 * (double)(cur[i] - s->last[i]) / (double)delta;
  }
  memcpy(s->last, cur, sizeof(cur));
  double other = 100.0 - (usage[0] + usage[1] + usage[2] + usage[3] + usage[4]);
  if (other < 0) other = 0;
  out[0] = usage[0];  // user
  out[1] = usage[1];  // system
  out[2] = usage[2];  // nice
  out[3] = usage[4];  // iowait
  out[4] = other;
  return 1;
}

// --- memory ---------------------------------------------------------------

int mem_sample(double out[3]) {
  if (!out) return 0;
  FILE *fp = fopen("/proc/meminfo", "r");
  if (!fp) return 0;
  unsigned long long total = 0, avail_free = 0, buffers = 0, cached = 0;
  char line[256];
  while (fgets(line, sizeof(line), fp)) {
    unsigned long long v = 0;
    if (sscanf(line, "MemTotal: %llu", &v) == 1) {
      total = v;
    } else if (sscanf(line, "MemFree: %llu", &v) == 1) {
      avail_free = v;
    } else if (sscanf(line, "Buffers: %llu", &v) == 1) {
      buffers = v;
    } else if (sscanf(line, "Cached: %llu", &v) == 1) {
      // First "Cached:" line only (Meminfo has exactly one).
      if (cached == 0) cached = v;
    }
  }
  fclose(fp);
  if (total == 0) return 0;
  double user = (double)total - (double)avail_free - (double)buffers - (double)cached;
  if (user < 0) user = 0;
  out[0] = user / (double)total;
  out[1] = (double)buffers / (double)total;
  out[2] = (double)cached / (double)total;
  return 1;
}

// --- net -------------------------------------------------------------------

static int iface_up(const char *name) {
  char path[128];
  snprintf(path, sizeof(path), "/sys/class/net/%s/operstate", name);
  FILE *fp = fopen(path, "r");
  if (!fp) return 1;  // collectors.py includes ifaces without operstate file
  char state[16];
  int up = 1;
  if (fgets(state, sizeof(state), fp) && strncmp(state, "up", 2) != 0) up = 0;
  fclose(fp);
  return up;
}

static int use_iface(const char *name) {
  if (strncmp(name, "lo", 2) == 0) return 0;
  if (strncmp(name, "br", 2) == 0) return 0;
  return iface_up(name);
}

static int read_net_totals(unsigned long long acc[5]) {
  FILE *fp = fopen("/proc/net/dev", "r");
  if (!fp) return -1;
  char line[512];
  // Skip the two header lines.
  if (!fgets(line, sizeof(line), fp) || !fgets(line, sizeof(line), fp)) {
    fclose(fp);
    return -1;
  }
  for (int i = 0; i < 5; i++) acc[i] = 0;
  while (fgets(line, sizeof(line), fp)) {
    char *colon = strchr(line, ':');
    if (!colon) continue;
    *colon = '\0';
    char *name = line;
    while (*name && isspace((unsigned char)*name)) name++;
    // Trim trailing spaces from the name.
    char *end = name + strlen(name);
    while (end > name && isspace((unsigned char)end[-1])) *--end = '\0';
    if (!use_iface(name)) continue;
    unsigned long long f[16] = {0};
    // All 16 counters are 64-bit; parse them all (no %* suppression, which
    // gcc's -Wformat rejects in combination with length modifiers).
    int n = sscanf(colon + 1,
                   "%llu %llu %llu %llu %llu %llu %llu %llu"
                   " %llu %llu %llu %llu %llu %llu %llu %llu",
                   &f[0], &f[1], &f[2], &f[3], &f[4], &f[5], &f[6], &f[7],
                   &f[8], &f[9], &f[10], &f[11], &f[12], &f[13], &f[14], &f[15]);
    if (n != 16) continue;
    acc[0] += f[0];   // rx bytes
    acc[1] += f[2];   // rx errs
    acc[2] += f[8];   // tx bytes
    acc[3] += f[10];  // tx errs
    acc[4] += f[13];  // collisions
  }
  fclose(fp);
  return 0;
}

int net_sample(NetState *s, double out[5]) {
  if (!s || !out) return 0;
  unsigned long long cur[5];
  if (read_net_totals(cur) != 0) return 0;
  double t = sm_mono_seconds();
  if (t < 0) return 0;
  if (!s->have_last) {
    memcpy(s->last, cur, sizeof(cur));
    s->last_time = t;
    s->have_last = 1;
    return 0;
  }
  double dt = t - s->last_time;
  if (dt <= 0) return 0;
  for (int i = 0; i < 5; i++) {
    out[i] = (double)(cur[i] - s->last[i]) / dt;
    s->last[i] = cur[i];
  }
  s->last_time = t;
  return 1;
}
