/* Host-only deterministic gate model; intentionally has no transfer path. */
#include "stage0_reference.h"

static stage0_result_t make_result(stage0_status_t status,
                                   uint32_t gate_evaluated,
                                   uint32_t gate_satisfied) {
    stage0_result_t result = {
        .magic = STAGE0_RESULT_MAGIC_BYTES,
        .version = STAGE0_REFERENCE_SCHEMA_VERSION,
        .record_size = (uint16_t)sizeof(stage0_result_t),
        .status = (uint32_t)status,
        .phase = STAGE0_PHASE_PRE_KERNEL_GATE,
        .pre_kernel_gate_evaluated = gate_evaluated == 1U ? 1U : 0U,
        .pre_kernel_gate_satisfied = gate_satisfied == 1U ? 1U : 0U,
        .transfer_performed = 0U,
        .reserved = 0U
    };

    return result;
}

stage0_result_t stage0_reference_evaluate(const stage0_gate_facts_t *facts) {
    if (facts == 0 || facts->current_el_present != 1U ||
        facts->current_el_proven != 1U || facts->current_el != 1U) {
        return make_result(ABORT_UNKNOWN_EL, 0U, 0U);
    }
    if (facts->stack_proven != 1U) {
        return make_result(ABORT_BAD_STACK, 0U, 0U);
    }
    if (facts->translation_proven != 1U) {
        return make_result(ABORT_TRANSLATION_UNKNOWN, 0U, 0U);
    }
    if (facts->mappings_proven != 1U) {
        return make_result(ABORT_MAPPING_UNPROVEN, 0U, 0U);
    }
    if (facts->memory_ownership_proven != 1U) {
        return make_result(ABORT_MEMORY_OWNERSHIP_UNPROVEN, 0U, 0U);
    }
    if (facts->collision_audit_complete != 1U ||
        facts->collision_free != 1U) {
        return make_result(ABORT_COLLISION, 0U, 0U);
    }
    if (facts->descriptor_prefix_trusted != 1U ||
        facts->descriptor_structure_valid != 1U) {
        return make_result(ABORT_DESCRIPTOR_INVALID, 0U, 0U);
    }
    if (facts->output_buffer_valid != 1U) {
        return make_result(ABORT_OUTPUT_BUFFER_INVALID, 0U, 0U);
    }
    if (facts->persistence_policy_proven != 1U ||
        facts->persistent_write_required != 0U) {
        return make_result(ABORT_PERSISTENCE_POLICY, 0U, 0U);
    }
    if (facts->pre_kernel_gate_evaluated != 1U ||
        facts->pre_kernel_gate_satisfied != 1U) {
        return make_result(ABORT_TRANSFER_GATE_BLOCKED,
                           facts->pre_kernel_gate_evaluated,
                           facts->pre_kernel_gate_satisfied);
    }

    /* This is an evaluation result only. The artifact has no transfer code. */
    return make_result(OK_TO_EVALUATE_TRANSFER, 1U, 1U);
}
