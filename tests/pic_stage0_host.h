/*
 * DreyzeOS — host-only PIC stage-0 contract model
 *
 * This interface is intentionally test-only. It models the checks a future
 * position-independent bootstrap would need before entering a larger image;
 * it never relocates, jumps, touches MMIO, or executes an image.
 */
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#include "../include/loader_handoff.h"

typedef enum {
    PIC_STAGE0_HOST_READY = 0,
    PIC_STAGE0_HOST_REJECT_NULL = 1,
    PIC_STAGE0_HOST_REJECT_DESCRIPTOR_BOUNDS = 2,
    PIC_STAGE0_HOST_REJECT_DESCRIPTOR = 3,
    PIC_STAGE0_HOST_REJECT_HANDOFF_FACTS = 4,
    PIC_STAGE0_HOST_REJECT_CPU_CONTRACT = 5,
    PIC_STAGE0_HOST_REJECT_EXECUTABLE_MAPPING = 6,
    PIC_STAGE0_HOST_REJECT_RUNTIME_PC = 7,
    PIC_STAGE0_HOST_REJECT_PAYLOAD_RANGE = 8
} pic_stage0_host_status_t;

typedef struct {
    /*
     * descriptor_readable is an assertion supplied by the pre-existing
     * loader contract. The model does not try to probe an arbitrary pointer.
     */
    const void *descriptor_address;
    size_t descriptor_readable;

    uintptr_t runtime_pc;
    uintptr_t stage0_link_base;
    uintptr_t target_entry_offset;

    uintptr_t executable_mapping_base;
    size_t executable_mapping_size;
    bool executable_mapping_proven;

    /*
     * V1 does not encode these CPU facts. They remain independent inputs and
     * must be proven by a future loader/shim before a real transition.
     */
    bool initial_stack_proven;
    bool daif_state_proven;
    bool translation_state_proven;
    bool cache_state_proven;
} pic_stage0_host_input_t;

typedef struct {
    loader_handoff_descriptor_t descriptor_copy;
    int64_t runtime_delta;
    uintptr_t target_entry_va;
} pic_stage0_host_output_t;

pic_stage0_host_status_t pic_stage0_host_prepare(
    const pic_stage0_host_input_t *input,
    pic_stage0_host_output_t *output);

void pic_stage0_host_run_self_tests(void);
