VERSION := 0.1.0
BUILD ?= build
CC ?= gcc
CFLAGS ?= -O2 -g -Wall -Wextra

.PHONY: all check clean
all: $(BUILD)/libkrunfw.so.5 $(BUILD)/run

$(BUILD)/asterinas.elf: upstream.json tools/fetch-kernel.py
	python3 tools/fetch-kernel.py --output $@

$(BUILD)/init: src/init.c
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS) -o $@ $< -ljson-c

$(BUILD)/run: src/run.c
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS) -o $@ $< -lkrun -ljson-c

$(BUILD)/payload/layout.h: $(BUILD)/asterinas.elf $(BUILD)/init tools/pack.py src/entry.S
	python3 tools/pack.py $(BUILD)/asterinas.elf $(BUILD)/init $(BUILD)/payload

$(BUILD)/libkrunfw.so.5: src/firmware.c $(BUILD)/payload/layout.h
	$(CC) $(CFLAGS) -fPIC -fvisibility=hidden -shared -nostdlib -Wl,-soname,libkrunfw.so.5 -Wl,-z,noexecstack -I$(BUILD)/payload -o $@ src/firmware.c $(BUILD)/payload/image.S

check: all
	python3 -m unittest discover -s tests -v

clean:
	rm -rf $(BUILD)
