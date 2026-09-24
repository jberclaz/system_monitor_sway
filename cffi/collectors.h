// /proc-based cpu / memory / net samplers.
// Deliberately libgtop-free: the build then needs only gtk3 (which Waybar
// already links), and there is no extra runtime dependency.
// Semantics mirror collectors.py: cpu/memory/net value layout and the
// "prime on first call, no data yet" behaviour of differential samplers.
#pragma once

#ifdef __cplusplus
extern "C" {
#endif

// out: [user%, system%, nice%, iowait%, other%]. Returns 1 with data,
// 0 when priming (first call) or on read error.
typedef struct {
  unsigned long long last[5];
  int have_last;
} CpuState;
int cpu_sample(CpuState *s, double out[5]);

// out: [program, buffer, cache] fractions of total. Stateless.
int mem_sample(double out[3]);

// out: [down_Bps, downerrors_ps, up_Bps, uperrors_ps, collisions_ps].
// Returns 1 with data, 0 when priming or on read error.
typedef struct {
  unsigned long long last[5];
  double last_time;
  int have_last;
} NetState;
int net_sample(NetState *s, double out[5]);

double sm_mono_seconds(void);

#ifdef __cplusplus
}
#endif
