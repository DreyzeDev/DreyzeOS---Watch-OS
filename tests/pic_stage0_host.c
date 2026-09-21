/*
 * DreyzeOS — host-only PIC stage-0 contract model
 *
 * DESIGN only: this is a bounded decision model for tests and documentation.
 * It has no production linkage and contains no hardware access or branch to a
 * loader-provided address.
 */

#include "pic_stage0_host.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static bool host_range_contains(uintptr_t container_base,
                                size_t container_size,
                                uintptr_t object_base,
                                size_t object_size)
{
    uintptr_t container_end;

    if (container_size == 0 || object_size == 0 ||
        container_size > (uintptr_t)-1 - container_base ||
        object_size > (uintptr_t)-1 - object_base) {
        return false;
    }

    container_end = container_base + container_size;
    return object_base >= container_base &&
           object_base <= container_end &&
           object_size <= container_end - object_base;
}

static bool signed_delta(uintptr_t runtime_pc,
                         uintptr_t stage0_link_base,
                         int64_t *out)
{
    uintptr_t difference;

    if (!out) {
        return false;
    }

    if (runtime_pc >= stage0_link_base) {
        difference = runtime_pc - stage0_link_base;
        if ((uint64_t)difference > (uint64_t)INT64_MAX) {
            return false;
        }
        *out = (int64_t)difference;
        return true;
    }

    difference = stage0_link_base - runtime_pc;
    if ((uint64_t)difference > (uint64_t)INT64_MAX) {
        return false;
    }
    *out = -(int64_t)difference;
    return true;
}

pic_stage0_host_status_t pic_stage0_host_prepare(
    const pic_stage0_host_input_t *input,
    pic_stage0_host_output_t *output)
{
    const uint64_t required_flags =
        DREYZE_HANDOFF_FLAG_VERIFIED |
        DREYZE_HANDOFF_FLAG_ENTRY_EL_KNOWN |
        DREYZE_HANDOFF_FLAG_PAYLOAD_LOCATION_KNOWN |
        DREYZE_HANDOFF_FLAG_MMU_STATE_KNOWN;
    uintptr_t target_entry;

    if (!input || !output) {
        return PIC_STAGE0_HOST_REJECT_NULL;
    }

    memset(output, 0, sizeof(*output));

    if (!input->descriptor_address ||
        input->descriptor_readable < DREYZE_HANDOFF_V1_SIZE) {
        return PIC_STAGE0_HOST_REJECT_DESCRIPTOR_BOUNDS;
    }

    /*
     * Copy only the fixed prefix. In a real bootstrap this copy would happen
     * after the loader proved the source range readable.
     */
    memcpy(&output->descriptor_copy, input->descriptor_address,
           DREYZE_HANDOFF_V1_SIZE);
    if (!loader_handoff_descriptor_validate(&output->descriptor_copy)) {
        return PIC_STAGE0_HOST_REJECT_DESCRIPTOR;
    }

    if ((output->descriptor_copy.flags & required_flags) != required_flags ||
        output->descriptor_copy.entry_el != 1U) {
        return PIC_STAGE0_HOST_REJECT_HANDOFF_FACTS;
    }

    if (!input->initial_stack_proven || !input->daif_state_proven ||
        !input->translation_state_proven || !input->cache_state_proven) {
        return PIC_STAGE0_HOST_REJECT_CPU_CONTRACT;
    }

    if (!input->executable_mapping_proven ||
        !host_range_contains(input->executable_mapping_base,
                             input->executable_mapping_size,
                             input->runtime_pc, 1)) {
        return PIC_STAGE0_HOST_REJECT_EXECUTABLE_MAPPING;
    }

    if (!input->runtime_pc || !input->stage0_link_base ||
        !signed_delta(input->runtime_pc, input->stage0_link_base,
                      &output->runtime_delta)) {
        return PIC_STAGE0_HOST_REJECT_RUNTIME_PC;
    }

    if (input->target_entry_offset >= output->descriptor_copy.payload_size ||
        output->descriptor_copy.payload_va >
            (uintptr_t)-1 - input->target_entry_offset) {
        return PIC_STAGE0_HOST_REJECT_PAYLOAD_RANGE;
    }

    target_entry = (uintptr_t)output->descriptor_copy.payload_va +
                   input->target_entry_offset;
    if (!host_range_contains(input->executable_mapping_base,
                             input->executable_mapping_size,
                             target_entry, 4)) {
        return PIC_STAGE0_HOST_REJECT_EXECUTABLE_MAPPING;
    }

    output->target_entry_va = target_entry;
    return PIC_STAGE0_HOST_READY;
}

void pic_stage0_host_run_self_tests(void)
{
    loader_handoff_descriptor_t descriptor;
    pic_stage0_host_input_t input;
    pic_stage0_host_output_t output;

    printf("[C-TEST] Running: pic_stage0_host_contract... ");
    memset(&descriptor, 0, sizeof(descriptor));
    descriptor.magic = DREYZE_HANDOFF_MAGIC;
    descriptor.version = DREYZE_HANDOFF_VERSION;
    descriptor.size = DREYZE_HANDOFF_V1_SIZE;
    descriptor.flags = DREYZE_HANDOFF_FLAG_VERIFIED |
                       DREYZE_HANDOFF_FLAG_ENTRY_EL_KNOWN |
                       DREYZE_HANDOFF_FLAG_PAYLOAD_LOCATION_KNOWN |
                       DREYZE_HANDOFF_FLAG_MMU_STATE_KNOWN;
    descriptor.entry_el = 1;
    descriptor.payload_pa = 0x800000000ULL;
    descriptor.payload_va = 0x200000000ULL;
    descriptor.payload_size = 0x4000;
    descriptor.mmu_enabled = 1;

    memset(&input, 0, sizeof(input));
    input.descriptor_address = &descriptor;
    input.descriptor_readable = sizeof(descriptor);
    input.runtime_pc = 0x100000100ULL;
    input.stage0_link_base = 0x100000000ULL;
    input.target_entry_offset = 0x100;
    input.executable_mapping_base = 0x100000000ULL;
    input.executable_mapping_size = 0x110000000ULL;
    input.executable_mapping_proven = true;
    input.initial_stack_proven = true;
    input.daif_state_proven = true;
    input.translation_state_proven = true;
    input.cache_state_proven = true;

    assert(pic_stage0_host_prepare(&input, &output) ==
           PIC_STAGE0_HOST_READY);
    assert(output.runtime_delta == 0x100);
    assert(output.target_entry_va == 0x200000100ULL);

    input.descriptor_readable = DREYZE_HANDOFF_V1_SIZE - 1;
    assert(pic_stage0_host_prepare(&input, &output) ==
           PIC_STAGE0_HOST_REJECT_DESCRIPTOR_BOUNDS);

    input.descriptor_readable = sizeof(descriptor);
    input.initial_stack_proven = false;
    assert(pic_stage0_host_prepare(&input, &output) ==
           PIC_STAGE0_HOST_REJECT_CPU_CONTRACT);

    printf("PASS\n");
}
