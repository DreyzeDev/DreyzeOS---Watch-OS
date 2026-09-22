/*
 * DreyzeOS — host-only Loader Entry Contract validator
 *
 * DESIGN/HOST ONLY. This code performs arithmetic and proof-state checks.
 * It never dereferences a loader address, touches MMIO, copies untrusted
 * memory, invokes a function pointer, or transfers control.
 */

#include "loader_entry_contract.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static bool range_end(const loader_contract_range_t *range,
                      uintptr_t *out_end)
{
    if (!range || range->length == 0 ||
        range->length > (uintptr_t)-1 - range->base) {
        return false;
    }

    if (out_end) {
        *out_end = range->base + range->length;
    }
    return true;
}

bool loader_contract_range_is_valid(const loader_contract_range_t *range)
{
    return range != NULL &&
           range->present &&
           range->bounds_proven &&
           range->base != 0 &&
           (range->address_space == LOADER_CONTRACT_ADDRESS_PHYSICAL ||
            range->address_space == LOADER_CONTRACT_ADDRESS_VIRTUAL) &&
           range_end(range, NULL);
}

bool loader_contract_range_contains(const loader_contract_range_t *container,
                                    uintptr_t base, size_t length)
{
    uintptr_t container_end;

    if (!loader_contract_range_is_valid(container) ||
        length == 0 ||
        length > (uintptr_t)-1 - base ||
        !range_end(container, &container_end) ||
        base < container->base ||
        base > container_end) {
        return false;
    }

    return length <= container_end - base;
}

bool loader_contract_range_overlaps(const loader_contract_range_t *left,
                                    const loader_contract_range_t *right)
{
    uintptr_t left_end;
    uintptr_t right_end;

    if (!loader_contract_range_is_valid(left) ||
        !loader_contract_range_is_valid(right) ||
        left->address_space != right->address_space ||
        !range_end(left, &left_end) ||
        !range_end(right, &right_end)) {
        return false;
    }

    return left->base < right_end && right->base < left_end;
}

bool loader_contract_range_has_authority(
    const loader_contract_range_t *range,
    loader_contract_permission_t permission)
{
    if (!loader_contract_range_is_valid(range) ||
        !range->ownership_proven) {
        return false;
    }

    switch (permission) {
    case LOADER_CONTRACT_PERMISSION_READ:
        return range->readable;
    case LOADER_CONTRACT_PERMISSION_WRITE:
        return range->writable;
    case LOADER_CONTRACT_PERMISSION_EXECUTE:
        return range->executable;
    default:
        return false;
    }
}

static bool range_matches(const loader_contract_range_t *left,
                          const loader_contract_range_t *right)
{
    return loader_contract_range_is_valid(left) &&
           loader_contract_range_is_valid(right) &&
           left->address_space == right->address_space &&
           left->base == right->base &&
           left->length == right->length;
}

static bool stack_pointer_is_in_range(
    const loader_contract_range_t *range, uintptr_t sp)
{
    uintptr_t end;

    if (!loader_contract_range_is_valid(range) ||
        !range_end(range, &end)) {
        return false;
    }

    /*
     * SP == end is allowed: the AArch64 stack grows down from the top of the
     * proven writable interval. SP below base or above end is rejected.
     */
    return sp >= range->base && sp <= end;
}

static bool descriptor_wire_matches(
    const loader_handoff_range_v1_t *wire,
    const loader_contract_range_t *range)
{
    verified_range_t native_range;

    if (!wire || !range ||
        !loader_handoff_range_to_native(wire, &native_range) ||
        !loader_contract_range_is_valid(range)) {
        return false;
    }

    /*
     * V1 carries no PA/VA tag. The native contract must carry that explicit
     * address-space fact; the wire range only has to match base and length.
     */
    return range->base == native_range.base &&
           range->length == native_range.length;
}

static bool payload_fields_are_structurally_nonwrapping(
    const loader_handoff_descriptor_t *descriptor)
{
    return descriptor != NULL &&
           descriptor->payload_pa != 0 &&
           descriptor->payload_va != 0 &&
           descriptor->payload_size != 0 &&
           descriptor->payload_size <=
               (uint64_t)-1 - descriptor->payload_pa &&
           descriptor->payload_size <=
               (uint64_t)-1 - descriptor->payload_va;
}

static bool runtime_memory_metadata_is_valid(
    const loader_entry_contract_t *contract)
{
    loader_contract_range_t dram;
    uintptr_t dram_base;
    size_t dram_size;

    if (!contract ||
        contract->memory_provenance !=
            LOADER_CONTRACT_MEMORY_RUNTIME_VERIFIED ||
        contract->dram_phys_base == 0 ||
        contract->dram_size == 0 ||
        !loader_handoff_u64_to_uintptr(contract->dram_phys_base,
                                       &dram_base) ||
        !loader_handoff_u64_to_size(contract->dram_size, &dram_size)) {
        return false;
    }

    memset(&dram, 0, sizeof(dram));
    dram.base = dram_base;
    dram.length = dram_size;
    dram.address_space = LOADER_CONTRACT_ADDRESS_PHYSICAL;
    dram.present = true;
    dram.bounds_proven = true;
    dram.ownership_proven = true;
    return loader_contract_range_is_valid(&dram);
}

static bool payload_in_runtime_dram(
    const loader_entry_contract_t *contract,
    const loader_contract_range_t *payload_pa)
{
    loader_contract_range_t dram;
    uintptr_t dram_base;
    size_t dram_size;

    if (!runtime_memory_metadata_is_valid(contract) ||
        !loader_handoff_u64_to_uintptr(contract->dram_phys_base,
                                       &dram_base) ||
        !loader_handoff_u64_to_size(contract->dram_size, &dram_size)) {
        return false;
    }

    memset(&dram, 0, sizeof(dram));
    dram.base = dram_base;
    dram.length = dram_size;
    dram.address_space = LOADER_CONTRACT_ADDRESS_PHYSICAL;
    dram.present = true;
    dram.bounds_proven = true;
    dram.ownership_proven = true;
    return loader_contract_range_contains(&dram, payload_pa->base,
                                          payload_pa->length);
}

static loader_entry_contract_status_t collision_status_for_range(
    const loader_contract_range_t *payload_pa,
    const loader_contract_range_t *payload_va,
    const loader_contract_range_t *protected_range)
{
    if (!protected_range->present) {
        return LOADER_ENTRY_CONTRACT_READY;
    }

    if (!loader_contract_range_is_valid(protected_range) ||
        !protected_range->ownership_proven) {
        return LOADER_ENTRY_REJECT_COLLISION;
    }

    if ((protected_range->address_space ==
         LOADER_CONTRACT_ADDRESS_PHYSICAL &&
         loader_contract_range_overlaps(payload_pa, protected_range)) ||
        (protected_range->address_space ==
         LOADER_CONTRACT_ADDRESS_VIRTUAL &&
         loader_contract_range_overlaps(payload_va, protected_range))) {
        return LOADER_ENTRY_REJECT_COLLISION;
    }

    return LOADER_ENTRY_CONTRACT_READY;
}

static loader_entry_contract_status_t validate_collisions(
    const loader_entry_contract_t *contract,
    const loader_contract_range_t *payload_pa,
    const loader_contract_range_t *payload_va)
{
    const loader_contract_range_t *protected_ranges[] = {
        &contract->stage0_executable_range,
        &contract->loader_code_range,
        &contract->loader_stack_range,
        &contract->loader_heap_range,
        &contract->descriptor_source_range,
        &contract->descriptor_copy_range,
        &contract->kernel_stack_range
    };
    size_t protected_count = sizeof(protected_ranges) /
                            sizeof(protected_ranges[0]);

    if (!contract->payload_collision_audit_complete) {
        return LOADER_ENTRY_REJECT_COLLISION;
    }

    for (size_t i = 0; i < protected_count; i++) {
        loader_entry_contract_status_t status =
            collision_status_for_range(payload_pa, payload_va,
                                       protected_ranges[i]);
        if (status != LOADER_ENTRY_CONTRACT_READY) {
            return status;
        }
    }

    if (contract->boot_args_required &&
        collision_status_for_range(payload_pa, payload_va,
                                   &contract->boot_args_range) !=
            LOADER_ENTRY_CONTRACT_READY) {
        return LOADER_ENTRY_REJECT_COLLISION;
    }
    if (contract->device_tree_required &&
        collision_status_for_range(payload_pa, payload_va,
                                   &contract->device_tree_range) !=
            LOADER_ENTRY_CONTRACT_READY) {
        return LOADER_ENTRY_REJECT_COLLISION;
    }
    if (contract->framebuffer_present &&
        collision_status_for_range(payload_pa, payload_va,
                                   &contract->framebuffer_range) !=
            LOADER_ENTRY_CONTRACT_READY) {
        return LOADER_ENTRY_REJECT_COLLISION;
    }

    for (size_t i = 0; i < contract->reserved_range_count; i++) {
        if (collision_status_for_range(payload_pa, payload_va,
                                       &contract->reserved_ranges[i]) !=
            LOADER_ENTRY_CONTRACT_READY) {
            return LOADER_ENTRY_REJECT_COLLISION;
        }
    }

    return LOADER_ENTRY_CONTRACT_READY;
}

loader_entry_contract_status_t loader_entry_contract_validate(
    const loader_entry_contract_t *contract)
{
    const uint64_t required_flags =
        DREYZE_HANDOFF_FLAG_VERIFIED |
        DREYZE_HANDOFF_FLAG_ENTRY_EL_KNOWN |
        DREYZE_HANDOFF_FLAG_PAYLOAD_LOCATION_KNOWN |
        DREYZE_HANDOFF_FLAG_MMU_STATE_KNOWN;
    uintptr_t payload_pa_base;
    uintptr_t payload_va_base;
    size_t payload_size;
    loader_contract_range_t payload_pa;
    loader_contract_range_t payload_va;

    if (!contract) {
        return LOADER_ENTRY_REJECT_NULL;
    }

    /*
     * Root-of-trust order: these facts precede any descriptor interpretation.
     * The validator receives a caller-owned copy, never the source pointer.
     */
    if (!contract->descriptor_prefix_readable) {
        return LOADER_ENTRY_REJECT_DESCRIPTOR_UNREADABLE;
    }
    if (!contract->descriptor_copied) {
        return LOADER_ENTRY_REJECT_DESCRIPTOR_NOT_COPIED;
    }
    if (!contract->descriptor_structurally_valid) {
        return LOADER_ENTRY_REJECT_DESCRIPTOR_INVALID;
    }

    if (!payload_fields_are_structurally_nonwrapping(
            &contract->descriptor_copy)) {
        return LOADER_ENTRY_REJECT_PAYLOAD_RANGE;
    }
    if (!loader_handoff_descriptor_validate(&contract->descriptor_copy)) {
        return LOADER_ENTRY_REJECT_DESCRIPTOR_INVALID;
    }
    if ((contract->descriptor_copy.flags & required_flags) != required_flags ||
        contract->descriptor_copy.entry_el != 1U ||
        !contract->entry_el_proven) {
        return LOADER_ENTRY_REJECT_ENTRY_EL;
    }

    if (!contract->initial_sp_proven ||
        !loader_contract_range_has_authority(
            &contract->kernel_stack_range,
            LOADER_CONTRACT_PERMISSION_WRITE)) {
        return LOADER_ENTRY_REJECT_STACK;
    }
    if (!contract->sp_alignment_proven ||
        (contract->initial_sp & 0xFU) != 0) {
        return LOADER_ENTRY_REJECT_SP_ALIGNMENT;
    }
    if (!stack_pointer_is_in_range(&contract->kernel_stack_range,
                                   contract->initial_sp)) {
        return LOADER_ENTRY_REJECT_STACK;
    }

    if (!contract->daif_state_normalized) {
        return LOADER_ENTRY_REJECT_DAIF;
    }

    if (!contract->translation_regime_known ||
        !contract->mmu_state_known ||
        !contract->mmu_state_normalized ||
        !contract->sctlr_policy_proven ||
        !contract->ttbr_policy_proven ||
        !contract->tcr_policy_proven ||
        !contract->mair_policy_proven ||
        (contract->descriptor_copy.flags &
         DREYZE_HANDOFF_FLAG_MMU_STATE_KNOWN) == 0) {
        return LOADER_ENTRY_REJECT_TRANSLATION;
    }

    if (!contract->icache_state_known ||
        !contract->icache_state_normalized ||
        !contract->dcache_state_known ||
        !contract->dcache_state_normalized ||
        !contract->vbar_handoff_proven ||
        !contract->fp_simd_policy_proven) {
        return LOADER_ENTRY_REJECT_CACHE;
    }

    if (!contract->stage0_executable_mapping_proven ||
        !loader_contract_range_has_authority(
            &contract->stage0_executable_range,
            LOADER_CONTRACT_PERMISSION_EXECUTE)) {
        return LOADER_ENTRY_REJECT_EXEC_MAPPING;
    }
    if (!contract->kernel_executable_mapping_proven ||
        !loader_contract_range_has_authority(
            &contract->kernel_executable_range,
            LOADER_CONTRACT_PERMISSION_EXECUTE)) {
        return LOADER_ENTRY_REJECT_EXEC_MAPPING;
    }
    if (!contract->kernel_readable_mapping_proven ||
        !loader_contract_range_has_authority(
            &contract->kernel_readable_range,
            LOADER_CONTRACT_PERMISSION_READ)) {
        return LOADER_ENTRY_REJECT_READ_MAPPING;
    }
    if (!contract->kernel_writable_mapping_proven ||
        !loader_contract_range_has_authority(
            &contract->kernel_writable_range,
            LOADER_CONTRACT_PERMISSION_WRITE) ||
        !loader_contract_range_has_authority(
            &contract->kernel_bss_range,
            LOADER_CONTRACT_PERMISSION_WRITE) ||
        !loader_contract_range_has_authority(
            &contract->kernel_stack_range,
            LOADER_CONTRACT_PERMISSION_WRITE) ||
        !loader_contract_range_contains(
            &contract->kernel_writable_range,
            contract->kernel_bss_range.base,
            contract->kernel_bss_range.length) ||
        !loader_contract_range_contains(
            &contract->kernel_writable_range,
            contract->kernel_stack_range.base,
            contract->kernel_stack_range.length)) {
        return LOADER_ENTRY_REJECT_WRITE_MAPPING;
    }

    if (!contract->payload_pa_fact_present ||
        !contract->payload_va_fact_present ||
        !contract->payload_size_fact_present ||
        !loader_handoff_u64_to_uintptr(
            contract->descriptor_copy.payload_pa, &payload_pa_base) ||
        !loader_handoff_u64_to_uintptr(
            contract->descriptor_copy.payload_va, &payload_va_base) ||
        !loader_handoff_u64_to_size(
            contract->descriptor_copy.payload_size, &payload_size)) {
        return LOADER_ENTRY_REJECT_PAYLOAD_RANGE;
    }

    if (!runtime_memory_metadata_is_valid(contract)) {
        return LOADER_ENTRY_REJECT_RUNTIME_MEMORY_MAP;
    }

    memset(&payload_pa, 0, sizeof(payload_pa));
    payload_pa.base = payload_pa_base;
    payload_pa.length = payload_size;
    payload_pa.address_space = LOADER_CONTRACT_ADDRESS_PHYSICAL;
    payload_pa.present = true;
    payload_pa.bounds_proven = true;
    payload_pa.ownership_proven = contract->payload_pa_range.ownership_proven;

    memset(&payload_va, 0, sizeof(payload_va));
    payload_va.base = payload_va_base;
    payload_va.length = payload_size;
    payload_va.address_space = LOADER_CONTRACT_ADDRESS_VIRTUAL;
    payload_va.present = true;
    payload_va.bounds_proven = true;
    payload_va.ownership_proven = contract->payload_va_range.ownership_proven;

    if (!range_matches(&contract->payload_pa_range, &payload_pa) ||
        !range_matches(&contract->payload_va_range, &payload_va) ||
        !contract->payload_pa_range.ownership_proven ||
        !contract->payload_va_range.ownership_proven ||
        !payload_in_runtime_dram(contract, &payload_pa)) {
        return LOADER_ENTRY_REJECT_PAYLOAD_RANGE;
    }
    if (!loader_contract_range_contains(
            &contract->kernel_executable_range,
            payload_va.base, payload_va.length) ||
        !loader_contract_range_contains(
            &contract->kernel_readable_range,
            payload_va.base, payload_va.length)) {
        return LOADER_ENTRY_REJECT_EXEC_MAPPING;
    }

    if (!contract->entry_pc_proven ||
        !loader_contract_range_contains(&payload_va,
                                        contract->entry_pc, 1) ||
        !loader_contract_range_contains(
            &contract->kernel_executable_range,
            contract->entry_pc, 1)) {
        return LOADER_ENTRY_REJECT_ENTRY_OUTSIDE_PAYLOAD;
    }

    if (contract->boot_args_required &&
        (!loader_contract_range_has_authority(
             &contract->boot_args_range,
             LOADER_CONTRACT_PERMISSION_READ) ||
         !descriptor_wire_matches(
             &contract->descriptor_copy.boot_args_range,
             &contract->boot_args_range))) {
        return LOADER_ENTRY_REJECT_BOOT_ARGS_RANGE;
    }
    if (contract->device_tree_required &&
        (!loader_contract_range_has_authority(
             &contract->device_tree_range,
             LOADER_CONTRACT_PERMISSION_READ) ||
         !descriptor_wire_matches(
             &contract->descriptor_copy.device_tree_range,
             &contract->device_tree_range))) {
        return LOADER_ENTRY_REJECT_DEVICE_TREE_RANGE;
    }

    if (!contract->framebuffer_reservation_known ||
        (contract->framebuffer_present &&
         (!loader_contract_range_is_valid(&contract->framebuffer_range) ||
          !contract->framebuffer_range.ownership_proven))) {
        return LOADER_ENTRY_REJECT_COLLISION;
    }

    if (!loader_contract_range_has_authority(
            &contract->loader_code_range,
            LOADER_CONTRACT_PERMISSION_EXECUTE) ||
        !loader_contract_range_has_authority(
            &contract->loader_stack_range,
            LOADER_CONTRACT_PERMISSION_WRITE) ||
        !loader_contract_range_has_authority(
            &contract->descriptor_source_range,
            LOADER_CONTRACT_PERMISSION_READ) ||
        !loader_contract_range_contains(
            &contract->descriptor_source_range,
            contract->descriptor_source_range.base,
            DREYZE_HANDOFF_V1_SIZE) ||
        !loader_contract_range_has_authority(
            &contract->descriptor_copy_range,
            LOADER_CONTRACT_PERMISSION_WRITE) ||
        !loader_contract_range_contains(
            &contract->descriptor_copy_range,
            contract->descriptor_copy_range.base,
            DREYZE_HANDOFF_V1_SIZE)) {
        return LOADER_ENTRY_REJECT_DESCRIPTOR_NOT_TRUSTED;
    }

    if (contract->loader_heap_range.present &&
        (!loader_contract_range_is_valid(&contract->loader_heap_range) ||
         !loader_contract_range_has_authority(
             &contract->loader_heap_range,
             LOADER_CONTRACT_PERMISSION_WRITE))) {
        return LOADER_ENTRY_REJECT_COLLISION;
    }

    if (!contract->reserved_ranges_complete ||
        contract->reserved_range_count >
            LOADER_ENTRY_CONTRACT_MAX_RESERVED_RANGES) {
        return LOADER_ENTRY_REJECT_RESERVED_RANGES;
    }
    for (size_t i = 0; i < contract->reserved_range_count; i++) {
        if (!loader_contract_range_is_valid(&contract->reserved_ranges[i]) ||
            !contract->reserved_ranges[i].ownership_proven) {
            return LOADER_ENTRY_REJECT_RESERVED_RANGES;
        }
    }

    loader_entry_contract_status_t collision_status =
        validate_collisions(contract, &payload_pa, &payload_va);
    if (collision_status != LOADER_ENTRY_CONTRACT_READY) {
        return collision_status;
    }

    if (!contract->no_persistent_write_required) {
        return LOADER_ENTRY_REJECT_PERSISTENT_WRITE;
    }
    if (!contract->control_transfer_proven) {
        return LOADER_ENTRY_REJECT_CONTROL_TRANSFER;
    }

    return LOADER_ENTRY_CONTRACT_READY;
}

const char *loader_entry_contract_status_string(
    loader_entry_contract_status_t status)
{
    switch (status) {
    case LOADER_ENTRY_CONTRACT_READY:
        return "READY";
    case LOADER_ENTRY_REJECT_NULL:
        return "REJECT_NULL";
    case LOADER_ENTRY_REJECT_DESCRIPTOR_UNREADABLE:
        return "REJECT_DESCRIPTOR_UNREADABLE";
    case LOADER_ENTRY_REJECT_DESCRIPTOR_NOT_COPIED:
        return "REJECT_DESCRIPTOR_NOT_COPIED";
    case LOADER_ENTRY_REJECT_DESCRIPTOR_NOT_TRUSTED:
        return "REJECT_DESCRIPTOR_NOT_TRUSTED";
    case LOADER_ENTRY_REJECT_DESCRIPTOR_INVALID:
        return "REJECT_DESCRIPTOR_INVALID";
    case LOADER_ENTRY_REJECT_ENTRY_EL:
        return "REJECT_ENTRY_EL";
    case LOADER_ENTRY_REJECT_STACK:
        return "REJECT_STACK";
    case LOADER_ENTRY_REJECT_SP_ALIGNMENT:
        return "REJECT_SP_ALIGNMENT";
    case LOADER_ENTRY_REJECT_DAIF:
        return "REJECT_DAIF";
    case LOADER_ENTRY_REJECT_TRANSLATION:
        return "REJECT_TRANSLATION";
    case LOADER_ENTRY_REJECT_CACHE:
        return "REJECT_CACHE";
    case LOADER_ENTRY_REJECT_EXEC_MAPPING:
        return "REJECT_EXEC_MAPPING";
    case LOADER_ENTRY_REJECT_READ_MAPPING:
        return "REJECT_READ_MAPPING";
    case LOADER_ENTRY_REJECT_WRITE_MAPPING:
        return "REJECT_WRITE_MAPPING";
    case LOADER_ENTRY_REJECT_PAYLOAD_RANGE:
        return "REJECT_PAYLOAD_RANGE";
    case LOADER_ENTRY_REJECT_ENTRY_OUTSIDE_PAYLOAD:
        return "REJECT_ENTRY_OUTSIDE_PAYLOAD";
    case LOADER_ENTRY_REJECT_BOOT_ARGS_RANGE:
        return "REJECT_BOOT_ARGS_RANGE";
    case LOADER_ENTRY_REJECT_DEVICE_TREE_RANGE:
        return "REJECT_DEVICE_TREE_RANGE";
    case LOADER_ENTRY_REJECT_COLLISION:
        return "REJECT_COLLISION";
    case LOADER_ENTRY_REJECT_RUNTIME_MEMORY_MAP:
        return "REJECT_RUNTIME_MEMORY_MAP";
    case LOADER_ENTRY_REJECT_PERSISTENT_WRITE:
        return "REJECT_PERSISTENT_WRITE";
    case LOADER_ENTRY_REJECT_CONTROL_TRANSFER:
        return "REJECT_CONTROL_TRANSFER";
    case LOADER_ENTRY_REJECT_RESERVED_RANGES:
        return "REJECT_RESERVED_RANGES";
    default:
        return "REJECT_UNKNOWN";
    }
}

static void set_range(loader_contract_range_t *range,
                      uintptr_t base, size_t length,
                      loader_contract_address_space_t address_space,
                      bool readable, bool writable, bool executable)
{
    memset(range, 0, sizeof(*range));
    range->base = base;
    range->length = length;
    range->address_space = address_space;
    range->present = true;
    range->bounds_proven = true;
    range->readable = readable;
    range->writable = writable;
    range->executable = executable;
    range->ownership_proven = true;
}

static void set_wire_range(loader_handoff_range_v1_t *range,
                           uintptr_t base, size_t length)
{
    range->base = (uint64_t)base;
    range->length = (uint64_t)length;
    range->flags = DREYZE_HANDOFF_RANGE_FLAG_READABLE;
    range->reserved = 0;
}

static void make_valid_contract(loader_entry_contract_t *contract)
{
    const uintptr_t payload_pa = (uintptr_t)0x91000000U;
    const uintptr_t payload_va = (uintptr_t)0x50000000U;
    const size_t payload_size = 0x4000U;

    memset(contract, 0, sizeof(*contract));
    contract->descriptor_copy.magic = DREYZE_HANDOFF_MAGIC;
    contract->descriptor_copy.version = DREYZE_HANDOFF_VERSION;
    contract->descriptor_copy.size = DREYZE_HANDOFF_V1_SIZE;
    contract->descriptor_copy.flags =
        DREYZE_HANDOFF_FLAG_VERIFIED |
        DREYZE_HANDOFF_FLAG_ENTRY_EL_KNOWN |
        DREYZE_HANDOFF_FLAG_PAYLOAD_LOCATION_KNOWN |
        DREYZE_HANDOFF_FLAG_MMU_STATE_KNOWN;
    contract->descriptor_copy.entry_el = 1;
    contract->descriptor_copy.payload_pa = payload_pa;
    contract->descriptor_copy.payload_va = payload_va;
    contract->descriptor_copy.payload_size = payload_size;
    contract->descriptor_copy.mmu_enabled = 1;

    set_wire_range(&contract->descriptor_copy.boot_args_range,
                   (uintptr_t)0x90040000U, 0x200U);
    set_wire_range(&contract->descriptor_copy.device_tree_range,
                   (uintptr_t)0x90050000U, 0x1000U);

    contract->descriptor_prefix_readable = true;
    contract->descriptor_copied = true;
    contract->descriptor_structurally_valid = true;
    contract->entry_el_proven = true;
    contract->initial_sp_proven = true;
    contract->initial_sp = (uintptr_t)0x50012000U;
    contract->sp_alignment_proven = true;
    contract->daif_state_normalized = true;

    contract->translation_regime_known = true;
    contract->mmu_state_known = true;
    contract->mmu_state_normalized = true;
    contract->sctlr_policy_proven = true;
    contract->ttbr_policy_proven = true;
    contract->tcr_policy_proven = true;
    contract->mair_policy_proven = true;
    contract->icache_state_known = true;
    contract->icache_state_normalized = true;
    contract->dcache_state_known = true;
    contract->dcache_state_normalized = true;
    contract->vbar_handoff_proven = true;
    contract->fp_simd_policy_proven = true;
    contract->stage0_executable_mapping_proven = true;
    contract->kernel_executable_mapping_proven = true;
    contract->kernel_readable_mapping_proven = true;
    contract->kernel_writable_mapping_proven = true;

    set_range(&contract->stage0_executable_range,
              (uintptr_t)0x40000000U, 0x10000U,
              LOADER_CONTRACT_ADDRESS_VIRTUAL, true, false, true);
    set_range(&contract->kernel_executable_range,
              payload_va, 0x10000U,
              LOADER_CONTRACT_ADDRESS_VIRTUAL, true, false, true);
    set_range(&contract->kernel_readable_range,
              payload_va, 0x10000U,
              LOADER_CONTRACT_ADDRESS_VIRTUAL, true, false, false);
    set_range(&contract->kernel_writable_range,
              (uintptr_t)0x50010000U, 0x20000U,
              LOADER_CONTRACT_ADDRESS_VIRTUAL, true, true, false);
    set_range(&contract->kernel_bss_range,
              (uintptr_t)0x50010000U, 0x1000U,
              LOADER_CONTRACT_ADDRESS_VIRTUAL, true, true, false);
    set_range(&contract->kernel_stack_range,
              (uintptr_t)0x50011000U, 0x1000U,
              LOADER_CONTRACT_ADDRESS_VIRTUAL, true, true, false);

    set_range(&contract->payload_pa_range, payload_pa, payload_size,
              LOADER_CONTRACT_ADDRESS_PHYSICAL, true, false, false);
    set_range(&contract->payload_va_range, payload_va, payload_size,
              LOADER_CONTRACT_ADDRESS_VIRTUAL, true, false, true);
    contract->payload_pa_fact_present = true;
    contract->payload_va_fact_present = true;
    contract->payload_size_fact_present = true;
    contract->entry_pc_proven = true;
    contract->entry_pc = payload_va + 0x100U;

    set_range(&contract->loader_code_range,
              (uintptr_t)0x90010000U, 0x10000U,
              LOADER_CONTRACT_ADDRESS_PHYSICAL, true, false, true);
    set_range(&contract->loader_stack_range,
              (uintptr_t)0x90020000U, 0x10000U,
              LOADER_CONTRACT_ADDRESS_PHYSICAL, false, true, false);
    set_range(&contract->descriptor_source_range,
              (uintptr_t)0x90030000U, DREYZE_HANDOFF_V1_SIZE,
              LOADER_CONTRACT_ADDRESS_PHYSICAL, true, false, false);
    set_range(&contract->descriptor_copy_range,
              (uintptr_t)0x90031000U, DREYZE_HANDOFF_V1_SIZE,
              LOADER_CONTRACT_ADDRESS_PHYSICAL, false, true, false);

    contract->boot_args_required = true;
    set_range(&contract->boot_args_range,
              (uintptr_t)0x90040000U, 0x200U,
              LOADER_CONTRACT_ADDRESS_PHYSICAL, true, false, false);
    contract->device_tree_required = true;
    set_range(&contract->device_tree_range,
              (uintptr_t)0x90050000U, 0x1000U,
              LOADER_CONTRACT_ADDRESS_PHYSICAL, true, false, false);

    contract->framebuffer_reservation_known = true;
    contract->framebuffer_present = true;
    set_range(&contract->framebuffer_range,
              (uintptr_t)0x90060000U, 0x1000U,
              LOADER_CONTRACT_ADDRESS_PHYSICAL, false, false, false);

    contract->reserved_ranges_complete = true;
    contract->reserved_range_count = 1;
    set_range(&contract->reserved_ranges[0],
              (uintptr_t)0x90070000U, 0x1000U,
              LOADER_CONTRACT_ADDRESS_PHYSICAL, false, false, false);

    contract->memory_provenance =
        LOADER_CONTRACT_MEMORY_RUNTIME_VERIFIED;
    contract->dram_phys_base = 0x90000000ULL;
    contract->dram_size = 0x20000000ULL;
    contract->payload_collision_audit_complete = true;
    contract->no_persistent_write_required = true;
    contract->control_transfer_proven = true;
}

void loader_entry_contract_run_self_tests(void)
{
    loader_entry_contract_t contract;

    printf("[C-TEST] Running: loader_entry_contract_validator... ");

    make_valid_contract(&contract);
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_CONTRACT_READY);
    assert(strcmp(loader_entry_contract_status_string(
                      LOADER_ENTRY_CONTRACT_READY), "READY") == 0);

    /* Generic [base,end) range model. */
    assert(loader_contract_range_overlaps(
               &contract.payload_pa_range, &contract.payload_pa_range));
    {
        loader_contract_range_t adjacent = contract.loader_code_range;
        adjacent.base = contract.payload_pa_range.base -
                        adjacent.length;
        assert(!loader_contract_range_overlaps(
                   &adjacent, &contract.payload_pa_range));
        adjacent.base = contract.payload_pa_range.base +
                        contract.payload_pa_range.length - 1U;
        adjacent.length = 1U;
        assert(loader_contract_range_overlaps(
                   &adjacent, &contract.payload_pa_range));
        assert(loader_contract_range_contains(
                   &contract.payload_pa_range,
                   contract.payload_pa_range.base + 0x100U, 0x100U));
        assert(!loader_contract_range_contains(
                   &contract.payload_pa_range,
                   contract.payload_pa_range.base - 1U, 1U));
        assert(!loader_contract_range_contains(
                   &contract.payload_pa_range,
                   contract.payload_pa_range.base +
                       contract.payload_pa_range.length, 1U));
    }
    {
        loader_contract_range_t invalid = contract.payload_pa_range;
        invalid.length = 0;
        assert(!loader_contract_range_is_valid(&invalid));
        invalid = contract.payload_pa_range;
        invalid.base = (uintptr_t)-2;
        invalid.length = 3;
        assert(!loader_contract_range_is_valid(&invalid));
    }

    contract.descriptor_prefix_readable = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_DESCRIPTOR_UNREADABLE);
    make_valid_contract(&contract);
    contract.descriptor_copied = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_DESCRIPTOR_NOT_COPIED);
    make_valid_contract(&contract);
    contract.descriptor_structurally_valid = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_DESCRIPTOR_INVALID);
    make_valid_contract(&contract);
    contract.descriptor_copy.magic ^= 1U;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_DESCRIPTOR_INVALID);
    make_valid_contract(&contract);
    contract.descriptor_source_range.length = DREYZE_HANDOFF_V1_SIZE - 1U;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_DESCRIPTOR_NOT_TRUSTED);
    make_valid_contract(&contract);
    contract.descriptor_copy_range.length = DREYZE_HANDOFF_V1_SIZE - 1U;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_DESCRIPTOR_NOT_TRUSTED);

    make_valid_contract(&contract);
    contract.entry_el_proven = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_ENTRY_EL);
    make_valid_contract(&contract);
    contract.initial_sp_proven = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_STACK);
    make_valid_contract(&contract);
    contract.sp_alignment_proven = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_SP_ALIGNMENT);
    make_valid_contract(&contract);
    contract.initial_sp |= 1U;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_SP_ALIGNMENT);
    make_valid_contract(&contract);
    contract.initial_sp = contract.kernel_stack_range.base - 0x10U;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_STACK);

    make_valid_contract(&contract);
    contract.daif_state_normalized = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_DAIF);
    make_valid_contract(&contract);
    contract.translation_regime_known = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_TRANSLATION);
    make_valid_contract(&contract);
    contract.sctlr_policy_proven = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_TRANSLATION);
    make_valid_contract(&contract);
    contract.icache_state_known = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_CACHE);
    make_valid_contract(&contract);
    contract.dcache_state_normalized = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_CACHE);

    make_valid_contract(&contract);
    contract.stage0_executable_mapping_proven = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_EXEC_MAPPING);
    make_valid_contract(&contract);
    contract.kernel_readable_mapping_proven = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_READ_MAPPING);
    make_valid_contract(&contract);
    contract.kernel_writable_mapping_proven = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_WRITE_MAPPING);

    make_valid_contract(&contract);
    contract.descriptor_copy.payload_size = 0;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_PAYLOAD_RANGE);
    make_valid_contract(&contract);
    contract.descriptor_copy.payload_pa = UINT64_MAX - 1ULL;
    contract.descriptor_copy.payload_size = 2;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_PAYLOAD_RANGE);
    make_valid_contract(&contract);
    contract.descriptor_copy.payload_va = UINT64_MAX - 1ULL;
    contract.descriptor_copy.payload_size = 2;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_PAYLOAD_RANGE);
    make_valid_contract(&contract);
#if UINTPTR_MAX < UINT64_MAX
    contract.descriptor_copy.payload_pa = (uint64_t)UINTPTR_MAX + 1ULL;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_PAYLOAD_RANGE);
#endif

    make_valid_contract(&contract);
    contract.memory_provenance = LOADER_CONTRACT_MEMORY_STATIC_FALLBACK;
    contract.dram_phys_base = 0;
    contract.dram_size = 0;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_RUNTIME_MEMORY_MAP);
    make_valid_contract(&contract);
    contract.memory_provenance = LOADER_CONTRACT_MEMORY_UNKNOWN;
    contract.dram_phys_base = 0x90000000ULL;
    contract.dram_size = 0x20000000ULL;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_RUNTIME_MEMORY_MAP);

    make_valid_contract(&contract);
    contract.dram_size = 0x1000;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_PAYLOAD_RANGE);

    make_valid_contract(&contract);
    contract.entry_pc = contract.payload_va_range.base +
                        contract.payload_va_range.length;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_ENTRY_OUTSIDE_PAYLOAD);
    make_valid_contract(&contract);
    contract.entry_pc = contract.payload_va_range.base - 1U;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_ENTRY_OUTSIDE_PAYLOAD);

    make_valid_contract(&contract);
    contract.descriptor_source_range.base =
        contract.payload_pa_range.base;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_COLLISION);
    make_valid_contract(&contract);
    contract.descriptor_copy_range.base =
        contract.payload_pa_range.base;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_COLLISION);
    make_valid_contract(&contract);
    contract.boot_args_range.base = contract.payload_pa_range.base;
    contract.descriptor_copy.boot_args_range.base =
        (uint64_t)contract.payload_pa_range.base;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_COLLISION);
    make_valid_contract(&contract);
    contract.device_tree_range.base = contract.payload_pa_range.base;
    contract.descriptor_copy.device_tree_range.base =
        (uint64_t)contract.payload_pa_range.base;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_COLLISION);
    make_valid_contract(&contract);
    contract.loader_stack_range.base = contract.payload_pa_range.base;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_COLLISION);
    make_valid_contract(&contract);
    contract.framebuffer_range.base = contract.payload_pa_range.base;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_COLLISION);
    make_valid_contract(&contract);
    contract.reserved_ranges[0].base = contract.payload_pa_range.base;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_COLLISION);
    make_valid_contract(&contract);
    contract.stage0_executable_range.base =
        contract.payload_va_range.base;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_COLLISION);
    make_valid_contract(&contract);
    contract.kernel_writable_range.base =
        contract.payload_va_range.base;
    contract.kernel_writable_range.length = 0x30000U;
    contract.kernel_stack_range.base =
        contract.payload_va_range.base;
    contract.initial_sp = contract.kernel_stack_range.base;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_COLLISION);

    make_valid_contract(&contract);
    contract.loader_code_range.base =
        contract.payload_pa_range.base - contract.loader_code_range.length;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_CONTRACT_READY);

    make_valid_contract(&contract);
    contract.boot_args_required = false;
    contract.device_tree_required = false;
    memset(&contract.descriptor_copy.boot_args_range, 0,
           sizeof(contract.descriptor_copy.boot_args_range));
    memset(&contract.descriptor_copy.device_tree_range, 0,
           sizeof(contract.descriptor_copy.device_tree_range));
    contract.boot_args_range.present = false;
    contract.device_tree_range.present = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_CONTRACT_READY);

    make_valid_contract(&contract);
    contract.payload_collision_audit_complete = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_COLLISION);
    make_valid_contract(&contract);
    contract.no_persistent_write_required = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_PERSISTENT_WRITE);
    make_valid_contract(&contract);
    contract.control_transfer_proven = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_CONTROL_TRANSFER);
    make_valid_contract(&contract);
    contract.reserved_ranges_complete = false;
    assert(loader_entry_contract_validate(&contract) ==
           LOADER_ENTRY_REJECT_RESERVED_RANGES);

    printf("PASS\n");
}
