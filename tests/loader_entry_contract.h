/*
 * DreyzeOS — host-only Loader Entry Contract model
 *
 * This is an internal/native proof model for static analysis and host tests.
 * It is deliberately not a wire ABI, not a loader, and not linked into the
 * production image. Numeric addresses are facts only; range permissions and
 * ownership are separate proof inputs.
 */
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#include "../include/loader_handoff.h"

#define LOADER_ENTRY_CONTRACT_MAX_RESERVED_RANGES 16U

typedef enum {
    LOADER_CONTRACT_ADDRESS_PHYSICAL = 0,
    LOADER_CONTRACT_ADDRESS_VIRTUAL = 1
} loader_contract_address_space_t;

typedef enum {
    LOADER_CONTRACT_PERMISSION_READ = 0,
    LOADER_CONTRACT_PERMISSION_WRITE = 1,
    LOADER_CONTRACT_PERMISSION_EXECUTE = 2
} loader_contract_permission_t;

typedef struct {
    uintptr_t base;
    size_t length;
    loader_contract_address_space_t address_space;

    /*
     * PRESENT/BOUNDS_PROVEN describe facts. Permissions and ownership are
     * independent authority inputs; a non-zero base never grants access.
     */
    bool present;
    bool bounds_proven;
    bool readable;
    bool writable;
    bool executable;
    bool ownership_proven;
} loader_contract_range_t;

bool loader_contract_range_is_valid(const loader_contract_range_t *range);
bool loader_contract_range_contains(const loader_contract_range_t *container,
                                    uintptr_t base, size_t length);
bool loader_contract_range_overlaps(const loader_contract_range_t *left,
                                    const loader_contract_range_t *right);
bool loader_contract_range_has_authority(
    const loader_contract_range_t *range,
    loader_contract_permission_t permission);

typedef enum {
    LOADER_CONTRACT_MEMORY_UNKNOWN = 0,
    LOADER_CONTRACT_MEMORY_STATIC_FALLBACK = 1,
    LOADER_CONTRACT_MEMORY_RUNTIME_VERIFIED = 2
} loader_contract_memory_provenance_t;

typedef enum {
    LOADER_ENTRY_CONTRACT_READY = 0,
    LOADER_ENTRY_REJECT_NULL = 1,
    LOADER_ENTRY_REJECT_DESCRIPTOR_UNREADABLE = 2,
    LOADER_ENTRY_REJECT_DESCRIPTOR_NOT_COPIED = 3,
    LOADER_ENTRY_REJECT_DESCRIPTOR_NOT_TRUSTED = 4,
    LOADER_ENTRY_REJECT_DESCRIPTOR_INVALID = 5,
    LOADER_ENTRY_REJECT_ENTRY_EL = 6,
    LOADER_ENTRY_REJECT_STACK = 7,
    LOADER_ENTRY_REJECT_SP_ALIGNMENT = 8,
    LOADER_ENTRY_REJECT_DAIF = 9,
    LOADER_ENTRY_REJECT_TRANSLATION = 10,
    LOADER_ENTRY_REJECT_CACHE = 11,
    LOADER_ENTRY_REJECT_EXEC_MAPPING = 12,
    LOADER_ENTRY_REJECT_READ_MAPPING = 13,
    LOADER_ENTRY_REJECT_WRITE_MAPPING = 14,
    LOADER_ENTRY_REJECT_PAYLOAD_RANGE = 15,
    LOADER_ENTRY_REJECT_ENTRY_OUTSIDE_PAYLOAD = 16,
    LOADER_ENTRY_REJECT_BOOT_ARGS_RANGE = 17,
    LOADER_ENTRY_REJECT_DEVICE_TREE_RANGE = 18,
    LOADER_ENTRY_REJECT_COLLISION = 19,
    LOADER_ENTRY_REJECT_RUNTIME_MEMORY_MAP = 20,
    LOADER_ENTRY_REJECT_PERSISTENT_WRITE = 21,
    LOADER_ENTRY_REJECT_CONTROL_TRANSFER = 22,
    LOADER_ENTRY_REJECT_RESERVED_RANGES = 23
} loader_entry_contract_status_t;

/*
 * This is native state, not a serialized extension of Loader Handoff ABI V1.
 * The descriptor is already copied into this object by the caller; the
 * validator never probes or copies from an untrusted pointer.
 */
typedef struct {
    loader_handoff_descriptor_t descriptor_copy;

    bool descriptor_prefix_readable;
    bool descriptor_copied;
    bool descriptor_structurally_valid;

    bool entry_el_proven;
    bool initial_sp_proven;
    uintptr_t initial_sp;
    bool sp_alignment_proven;
    bool daif_state_normalized;

    bool translation_regime_known;
    bool mmu_state_known;
    bool mmu_state_normalized;
    bool sctlr_policy_proven;
    bool ttbr_policy_proven;
    bool tcr_policy_proven;
    bool mair_policy_proven;

    bool icache_state_known;
    bool icache_state_normalized;
    bool dcache_state_known;
    bool dcache_state_normalized;
    bool vbar_handoff_proven;
    bool fp_simd_policy_proven;

    bool stage0_executable_mapping_proven;
    bool kernel_executable_mapping_proven;
    bool kernel_readable_mapping_proven;
    bool kernel_writable_mapping_proven;

    loader_contract_range_t stage0_executable_range;
    loader_contract_range_t kernel_executable_range;
    loader_contract_range_t kernel_readable_range;
    loader_contract_range_t kernel_writable_range;
    loader_contract_range_t kernel_bss_range;
    loader_contract_range_t kernel_stack_range;

    bool payload_pa_fact_present;
    bool payload_va_fact_present;
    bool payload_size_fact_present;
    loader_contract_range_t payload_pa_range;
    loader_contract_range_t payload_va_range;
    bool entry_pc_proven;
    uintptr_t entry_pc;

    loader_contract_range_t loader_code_range;
    loader_contract_range_t loader_stack_range;
    loader_contract_range_t loader_heap_range;
    loader_contract_range_t descriptor_source_range;
    loader_contract_range_t descriptor_copy_range;

    bool boot_args_required;
    loader_contract_range_t boot_args_range;
    bool device_tree_required;
    loader_contract_range_t device_tree_range;

    bool framebuffer_reservation_known;
    bool framebuffer_present;
    loader_contract_range_t framebuffer_range;

    bool reserved_ranges_complete;
    size_t reserved_range_count;
    loader_contract_range_t reserved_ranges[
        LOADER_ENTRY_CONTRACT_MAX_RESERVED_RANGES];

    loader_contract_memory_provenance_t memory_provenance;
    uint64_t dram_phys_base;
    uint64_t dram_size;

    bool payload_collision_audit_complete;
    bool no_persistent_write_required;
    bool control_transfer_proven;
} loader_entry_contract_t;

loader_entry_contract_status_t loader_entry_contract_validate(
    const loader_entry_contract_t *contract);
const char *loader_entry_contract_status_string(
    loader_entry_contract_status_t status);

/* Invoked by the real C host harness; never linked into production. */
void loader_entry_contract_run_self_tests(void);
