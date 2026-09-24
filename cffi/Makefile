# Build for the native Waybar CFFI module.
#   make            -> build/waybar_sysmon.so
#   make test       -> build/run_tests (chart + collector unit tests)
#   make clean
# Requires: gcc, pkg-config, gtk+-3.0 dev headers. No libgtop needed
# (collectors read /proc directly).
CC ?= gcc
CFLAGS ?= -O2
VERSION := $(shell cat ../VERSION 2>/dev/null || echo 0.0.0-dev)
CFLAGS += -DSYSMON_VERSION='"$(VERSION)"'
WARN = -Wall -Wextra -Wpedantic -Wno-unused-parameter
GTK_CFLAGS := $(shell pkg-config --cflags gtk+-3.0)
GTK_LIBS := $(shell pkg-config --libs gtk+-3.0)

BUILD = build
SO = $(BUILD)/waybar_sysmon.so

SRCS = sysmon.c chart.c collectors.c strip.c
OBJS = $(SRCS:%.c=$(BUILD)/%.o)

.PHONY: all test clean

all: $(SO)

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/%.o: %.c | $(BUILD)
	$(CC) $(CFLAGS) $(WARN) $(GTK_CFLAGS) -fPIC -fvisibility=hidden -c $< -o $@

$(SO): $(OBJS)
	$(CC) -shared -o $@ $(OBJS) $(GTK_LIBS) -lm

test: $(BUILD)/run_tests
	./$(BUILD)/run_tests

visualtest: $(BUILD)/visualtest
	@echo "Run: ./build/visualtest & sleep 9; grim shot; pkill visualtest"

$(BUILD)/run_tests: test_logic.c chart.c collectors.c strip.c | $(BUILD)
	$(CC) $(CFLAGS) $(WARN) $(shell pkg-config --cflags cairo) $^ -o $@ \
		$(shell pkg-config --libs cairo) -lm

$(BUILD)/visualtest: test_window.c chart.c collectors.c strip.c | $(BUILD)
	$(CC) $(CFLAGS) $(WARN) $(GTK_CFLAGS) $^ -o $@ $(GTK_LIBS) -lm

clean:
	rm -rf $(BUILD)
