/*
 * DreyzeOS Stage-0 reference record contract.
 *
 * HOST-ONLY: this API is deliberately excluded from the AArch64 production
 * ELF and cannot perform device I/O or a control transfer.
 */
#pragma once

#if !defined(STAGE0_HOST_REFERENCE)
#error "Stage-0 reference must be built only as a host reference model"
#endif

#if defined(__aarch64__) || defined(__arm__)
#error "This reference artifact is not target-executable ARM stage-0 code"
#endif

#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "Stage-0 host reference records require a little-endian host"
#endif

#include <stdint.h>
#include "loader_handoff.h"

#define STAGE0_REFERENCE_SCHEMA_VERSION 1U
#define STAGE0_CAPTURE_ID_SIZE 36U
#define STAGE0_UTC_TEXT_SIZE 32U
#define STAGE0_PRODUCER_TEXT_SIZE 32U
#define STAGE0_SOURCE_TEXT_SIZE 32U
#define STAGE0_SHA256_SIZE 32U
#define STAGE0_MAX_RESERVED_RANGES 16U

#define STAGE0_SESSION_MAGIC "D0SES001"
#define STAGE0_RAW_CPU_MAGIC "D0CPU001"
#define STAGE0_POST_CPU_MAGIC "D0CPU002"
#define STAGE0_MMU_MAGIC "D0MMU001"
#define STAGE0_MEMORY_MAGIC "D0MEM001"
#define STAGE0_RESULT_MAGIC "D0RES001"
#define STAGE0_RESULT_MAGIC_BYTES {'D', '0', 'R', 'E', 'S', '0', '0', '1'}

enum {
    STAGE0_SESSION_CAPTURE_ID_PRESENT = 1U << 0,
    STAGE0_SESSION_CAPTURE_ID_PROVEN = 1U << 1,
    STAGE0_SESSION_START_PRESENT = 1U << 2,
    STAGE0_SESSION_START_PROVEN = 1U << 3,
    STAGE0_SESSION_END_PRESENT = 1U << 4,
    STAGE0_SESSION_END_PROVEN = 1U << 5,
    STAGE0_SESSION_PRODUCER_PRESENT = 1U << 6,
    STAGE0_SESSION_PRODUCER_PROVEN = 1U << 7,
    STAGE0_SESSION_SOURCE_PRESENT = 1U << 8,
    STAGE0_SESSION_SOURCE_PROVEN = 1U << 9,
    STAGE0_SESSION_DREYZEOS_HASH_PRESENT = 1U << 10,
    STAGE0_SESSION_DREYZEOS_HASH_PROVEN = 1U << 11,
    STAGE0_SESSION_STAGE0_HASH_PRESENT = 1U << 12,
    STAGE0_SESSION_STAGE0_HASH_PROVEN = 1U << 13
};

enum {
    STAGE0_CPU_FACT_CURRENT_EL = UINT64_C(1) << 0,
    STAGE0_CPU_FACT_PC = UINT64_C(1) << 1,
    STAGE0_CPU_FACT_SP = UINT64_C(1) << 2,
    STAGE0_CPU_FACT_DAIF = UINT64_C(1) << 3,
    STAGE0_CPU_FACT_SCTLR_EL1 = UINT64_C(1) << 4,
    STAGE0_CPU_FACT_TCR_EL1 = UINT64_C(1) << 5,
    STAGE0_CPU_FACT_TTBR0_EL1 = UINT64_C(1) << 6,
    STAGE0_CPU_FACT_TTBR1_EL1 = UINT64_C(1) << 7,
    STAGE0_CPU_FACT_MAIR_EL1 = UINT64_C(1) << 8,
    STAGE0_CPU_FACT_VBAR_EL1 = UINT64_C(1) << 9,
    STAGE0_CPU_FACT_CPACR_EL1 = UINT64_C(1) << 10
};

enum {
    STAGE0_MMU_FACT_SCTLR_EL1 = UINT64_C(1) << 0,
    STAGE0_MMU_FACT_TCR_EL1 = UINT64_C(1) << 1,
    STAGE0_MMU_FACT_TTBR0_EL1 = UINT64_C(1) << 2,
    STAGE0_MMU_FACT_TTBR1_EL1 = UINT64_C(1) << 3,
    STAGE0_MMU_FACT_MAIR_EL1 = UINT64_C(1) << 4,
    STAGE0_MMU_FACT_GRANULE = UINT64_C(1) << 5,
    STAGE0_MMU_FACT_VA_BITS = UINT64_C(1) << 6,
    STAGE0_MMU_FACT_PA_BITS = UINT64_C(1) << 7,
    STAGE0_MMU_FACT_TABLE_PAGES_REQUIRED = UINT64_C(1) << 8,
    STAGE0_MMU_FACT_TABLE_PAGES_PRESENT = UINT64_C(1) << 9,
    STAGE0_MMU_FACT_REGION_COUNT = UINT64_C(1) << 10,
    STAGE0_MMU_FACT_TABLE_BYTES_HASH = UINT64_C(1) << 11
};

enum {
    STAGE0_MEMORY_FACT_RUNTIME_DRAM = UINT64_C(1) << 0,
    STAGE0_MEMORY_FACT_STAGE0_CODE = UINT64_C(1) << 1,
    STAGE0_MEMORY_FACT_STAGE0_STACK = UINT64_C(1) << 2,
    STAGE0_MEMORY_FACT_SCRATCH_OUTPUT = UINT64_C(1) << 3,
    STAGE0_MEMORY_FACT_KERNEL_PAYLOAD = UINT64_C(1) << 4,
    STAGE0_MEMORY_FACT_FRAMEBUFFER = UINT64_C(1) << 5,
    STAGE0_MEMORY_FACT_RESERVED_RANGES = UINT64_C(1) << 6
};

typedef enum {
    STAGE0_PHASE_OBSERVE_ONLY = 1,
    STAGE0_PHASE_NORMALIZE_IF_APPROVED = 2,
    STAGE0_PHASE_PRODUCE_EVIDENCE = 3,
    STAGE0_PHASE_PREPARE_DESCRIPTOR = 4,
    STAGE0_PHASE_TRANSFER = 5,
    STAGE0_PHASE_PRE_KERNEL_GATE = 6
} stage0_phase_t;

typedef enum {
    OK_TO_EVALUATE_TRANSFER = 0,
    ABORT_UNKNOWN_EL = 1,
    ABORT_BAD_STACK = 2,
    ABORT_TRANSLATION_UNKNOWN = 3,
    ABORT_MAPPING_UNPROVEN = 4,
    ABORT_MEMORY_OWNERSHIP_UNPROVEN = 5,
    ABORT_COLLISION = 6,
    ABORT_DESCRIPTOR_INVALID = 7,
    ABORT_OUTPUT_BUFFER_INVALID = 8,
    ABORT_PERSISTENCE_POLICY = 9,
    ABORT_TRANSFER_GATE_BLOCKED = 10
} stage0_status_t;

typedef struct __packed {
    uint8_t magic[8];
    uint16_t version;
    uint16_t record_size;
    uint32_t flags;
    uint8_t capture_id[STAGE0_CAPTURE_ID_SIZE];
    uint8_t started_at_utc[STAGE0_UTC_TEXT_SIZE];
    uint8_t ended_at_utc[STAGE0_UTC_TEXT_SIZE];
    uint8_t producer[STAGE0_PRODUCER_TEXT_SIZE];
    uint8_t source_interface[STAGE0_SOURCE_TEXT_SIZE];
    uint8_t dreyzeos_image_sha256[STAGE0_SHA256_SIZE];
    uint8_t stage0_image_sha256[STAGE0_SHA256_SIZE];
} stage0_session_header_t;

typedef struct __packed {
    uint8_t magic[8];
    uint16_t version;
    uint16_t record_size;
    uint32_t phase;
    uint64_t present_mask;
    uint64_t proven_mask;
    uint64_t current_el;
    uint64_t pc;
    uint64_t sp;
    uint64_t daif;
    uint64_t sctlr_el1;
    uint64_t tcr_el1;
    uint64_t ttbr0_el1;
    uint64_t ttbr1_el1;
    uint64_t mair_el1;
    uint64_t vbar_el1;
    uint64_t cpacr_el1;
} stage0_cpu_record_t;

/* Same fixed wire layout; phase distinguishes raw from post-normalization. */
typedef stage0_cpu_record_t stage0_raw_cpu_record_t;
typedef stage0_cpu_record_t stage0_post_normalization_cpu_record_t;

typedef struct __packed {
    uint8_t magic[8];
    uint16_t version;
    uint16_t record_size;
    uint32_t flags;
    uint64_t present_mask;
    uint64_t proven_mask;
    uint64_t sctlr_el1;
    uint64_t tcr_el1;
    uint64_t ttbr0_el1;
    uint64_t ttbr1_el1;
    uint64_t mair_el1;
    uint32_t granule_log2;
    uint32_t va_bits;
    uint32_t pa_bits;
    uint32_t table_pages_required;
    uint32_t table_pages_present;
    uint32_t region_count;
    uint8_t table_bytes_sha256[STAGE0_SHA256_SIZE];
} stage0_mmu_record_t;

typedef enum {
    STAGE0_ADDRESS_SPACE_UNKNOWN = 0,
    STAGE0_ADDRESS_SPACE_PHYSICAL = 1,
    STAGE0_ADDRESS_SPACE_VIRTUAL = 2
} stage0_address_space_t;

#define STAGE0_RANGE_PRESENT          (1U << 0)
#define STAGE0_RANGE_BOUNDS_PROVEN    (1U << 1)
#define STAGE0_RANGE_READABLE         (1U << 2)
#define STAGE0_RANGE_WRITABLE         (1U << 3)
#define STAGE0_RANGE_EXECUTABLE       (1U << 4)
#define STAGE0_RANGE_OWNERSHIP_PROVEN (1U << 5)

typedef struct __packed {
    uint64_t base;
    uint64_t length;
    uint32_t address_space;
    uint32_t flags;
} stage0_range_t;

typedef struct __packed {
    uint8_t magic[8];
    uint16_t version;
    uint16_t record_size;
    uint32_t flags;
    uint64_t present_mask;
    uint64_t proven_mask;
    stage0_range_t runtime_dram;
    stage0_range_t stage0_code;
    stage0_range_t stage0_stack;
    stage0_range_t scratch_output;
    stage0_range_t kernel_payload;
    stage0_range_t framebuffer;
    uint32_t reserved_range_count;
    uint32_t reserved_ranges_complete;
    stage0_range_t reserved_ranges[STAGE0_MAX_RESERVED_RANGES];
} stage0_memory_record_t;

typedef struct __packed {
    uint8_t magic[8];
    uint16_t version;
    uint16_t record_size;
    uint32_t status;
    uint32_t phase;
    uint32_t pre_kernel_gate_evaluated;
    uint32_t pre_kernel_gate_satisfied;
    uint32_t transfer_performed;
    uint32_t reserved;
} stage0_result_t;

/* Use the existing fixed-width ABI directly; this does not define V2. */
typedef loader_handoff_descriptor_t stage0_handoff_descriptor_v1_t;

/* Boolean proof inputs only; no pointers or target addresses are accepted. */
typedef struct {
    uint32_t current_el_present;
    uint32_t current_el_proven;
    uint32_t current_el;
    uint32_t stack_proven;
    uint32_t translation_proven;
    uint32_t mappings_proven;
    uint32_t memory_ownership_proven;
    uint32_t collision_audit_complete;
    uint32_t collision_free;
    uint32_t descriptor_prefix_trusted;
    uint32_t descriptor_structure_valid;
    uint32_t output_buffer_valid;
    uint32_t persistence_policy_proven;
    uint32_t persistent_write_required;
    uint32_t pre_kernel_gate_evaluated;
    uint32_t pre_kernel_gate_satisfied;
} stage0_gate_facts_t;

stage0_result_t stage0_reference_evaluate(const stage0_gate_facts_t *facts);

_Static_assert(sizeof(stage0_session_header_t) == 244,
               "stage0 session header layout changed");
_Static_assert(sizeof(stage0_cpu_record_t) == 120,
               "stage0 CPU record layout changed");
_Static_assert(sizeof(stage0_mmu_record_t) == 128,
               "stage0 MMU record layout changed");
_Static_assert(sizeof(stage0_range_t) == 24,
               "stage0 range layout changed");
_Static_assert(sizeof(stage0_memory_record_t) == 568,
               "stage0 memory record layout changed");
_Static_assert(sizeof(stage0_result_t) == 36,
               "stage0 result layout changed");
#define STAGE0_ASSERT_OFFSET(type, member, expected) \
    _Static_assert(offsetof(type, member) == (expected), \
                   #type "." #member " offset changed")

_Static_assert(sizeof(STAGE0_SESSION_MAGIC) == 9,
               "session magic must be eight bytes plus NUL");
_Static_assert(sizeof(STAGE0_RAW_CPU_MAGIC) == 9,
               "raw CPU magic must be eight bytes plus NUL");
_Static_assert(sizeof(STAGE0_POST_CPU_MAGIC) == 9,
               "post-normalization CPU magic must be eight bytes plus NUL");
_Static_assert(sizeof(STAGE0_MMU_MAGIC) == 9,
               "MMU magic must be eight bytes plus NUL");
_Static_assert(sizeof(STAGE0_MEMORY_MAGIC) == 9,
               "memory magic must be eight bytes plus NUL");
_Static_assert(sizeof(STAGE0_RESULT_MAGIC) == 9,
               "result magic must be eight bytes plus NUL");

STAGE0_ASSERT_OFFSET(stage0_session_header_t, capture_id, 16);
STAGE0_ASSERT_OFFSET(stage0_session_header_t, started_at_utc, 52);
STAGE0_ASSERT_OFFSET(stage0_session_header_t, ended_at_utc, 84);
STAGE0_ASSERT_OFFSET(stage0_session_header_t, dreyzeos_image_sha256, 180);
STAGE0_ASSERT_OFFSET(stage0_session_header_t, stage0_image_sha256, 212);
STAGE0_ASSERT_OFFSET(stage0_cpu_record_t, current_el, 32);
STAGE0_ASSERT_OFFSET(stage0_cpu_record_t, cpacr_el1, 112);
STAGE0_ASSERT_OFFSET(stage0_mmu_record_t, present_mask, 16);
STAGE0_ASSERT_OFFSET(stage0_mmu_record_t, sctlr_el1, 32);
STAGE0_ASSERT_OFFSET(stage0_mmu_record_t, table_bytes_sha256, 96);
STAGE0_ASSERT_OFFSET(stage0_range_t, address_space, 16);
STAGE0_ASSERT_OFFSET(stage0_memory_record_t, runtime_dram, 32);
STAGE0_ASSERT_OFFSET(stage0_memory_record_t, reserved_ranges, 184);
STAGE0_ASSERT_OFFSET(stage0_result_t, status, 12);
STAGE0_ASSERT_OFFSET(stage0_result_t, transfer_performed, 28);

_Static_assert(sizeof(stage0_handoff_descriptor_v1_t) == 128,
               "Loader Handoff ABI V1 changed");
_Static_assert(offsetof(stage0_handoff_descriptor_v1_t, payload_pa) == 32,
               "Loader Handoff ABI V1 payload_pa offset changed");
_Static_assert(offsetof(stage0_handoff_descriptor_v1_t, device_tree_range) == 104,
               "Loader Handoff ABI V1 device_tree_range offset changed");

#undef STAGE0_ASSERT_OFFSET
