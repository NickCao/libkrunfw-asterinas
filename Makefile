VERSION := 0.1.0
BOOT_MODE ?= initramfs
ifeq ($(BOOT_MODE),rootfs)
BUILD ?= build/rootfs
else ifeq ($(BOOT_MODE),initramfs)
BUILD ?= build
INIT_PREREQUISITE = $(BUILD)/init
PACK_INIT = --init $(BUILD)/init
else
$(error BOOT_MODE must be initramfs or rootfs)
endif
KERNEL ?= build/asterinas.elf
CC ?= gcc
CFLAGS ?= -O2 -g -Wall -Wextra

.PHONY: all kernel check clean
all: $(BUILD)/libkrunfw.so.5 $(BUILD)/run

kernel:
	bash tools/build-kernel.sh

$(KERNEL): upstream.json tools/build-kernel.sh tools/fetch-sources.py $(wildcard patches/*)
	bash tools/build-kernel.sh

$(BUILD)/init: src/init.c
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS) -o $@ $<

$(BUILD)/run: src/run.c
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS) -o $@ $< -lkrun -ljson-c

$(BUILD)/payload/layout.h: $(KERNEL) $(INIT_PREREQUISITE) tools/pack.py src/entry.S src/boot.c src/boot.ld
	python3 tools/pack.py $(KERNEL) $(BUILD)/payload $(PACK_INIT)

$(BUILD)/libkrunfw.so.5: src/firmware.c $(BUILD)/payload/layout.h
	$(CC) $(CFLAGS) -fPIC -fvisibility=hidden -shared -nostdlib -Wl,-soname,libkrunfw.so.5 -Wl,-z,noexecstack -I$(BUILD)/payload -o $@ src/firmware.c $(BUILD)/payload/image.S

check: all
	FIRMWARE_BUILD=$(BUILD) FIRMWARE_KERNEL=$(KERNEL) python3 -m unittest discover -s tests -v

clean:
	rm -rf $(BUILD)
