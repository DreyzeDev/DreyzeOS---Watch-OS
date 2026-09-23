/* Host-only C tests for the frozen Stage-0 reference contract. */
#include "stage0_reference.h"

static int expect(stage0_gate_facts_t facts, stage0_status_t expected) {
    const stage0_result_t first = stage0_reference_evaluate(&facts);
    const stage0_result_t second = stage0_reference_evaluate(&facts);

    if (first.status != (uint32_t)expected ||
        first.status != second.status ||
        first.version != STAGE0_REFERENCE_SCHEMA_VERSION ||
        first.record_size != sizeof(stage0_result_t) ||
        first.phase != second.phase ||
        first.pre_kernel_gate_evaluated != second.pre_kernel_gate_evaluated ||
        first.pre_kernel_gate_satisfied != second.pre_kernel_gate_satisfied ||
        first.transfer_performed != 0U || second.transfer_performed != 0U) {
        return 1;
    }
    return 0;
}

static stage0_gate_facts_t all_proven(void) {
    const stage0_gate_facts_t facts = {
        .current_el_present = 1U,
        .current_el_proven = 1U,
        .current_el = 1U,
        .stack_proven = 1U,
        .translation_proven = 1U,
        .mappings_proven = 1U,
        .memory_ownership_proven = 1U,
        .collision_audit_complete = 1U,
        .collision_free = 1U,
        .descriptor_prefix_trusted = 1U,
        .descriptor_structure_valid = 1U,
        .output_buffer_valid = 1U,
        .persistence_policy_proven = 1U,
        .persistent_write_required = 0U,
        .pre_kernel_gate_evaluated = 1U,
        .pre_kernel_gate_satisfied = 1U
    };

    return facts;
}

int main(void) {
    stage0_gate_facts_t facts = {0};
    const stage0_result_t null_result = stage0_reference_evaluate(0);

    if (null_result.status != ABORT_UNKNOWN_EL ||
        null_result.transfer_performed != 0U) {
        return 18;
    }

    if (sizeof(stage0_session_header_t) != 244U ||
        sizeof(stage0_cpu_record_t) != 120U ||
        sizeof(stage0_mmu_record_t) != 128U ||
        sizeof(stage0_memory_record_t) != 568U ||
        sizeof(stage0_result_t) != 36U ||
        sizeof(stage0_handoff_descriptor_v1_t) != 128U ||
        offsetof(stage0_handoff_descriptor_v1_t, payload_pa) != 32U ||
        offsetof(stage0_handoff_descriptor_v1_t, device_tree_range) != 104U) {
        return 1;
    }

    if (expect(facts, ABORT_UNKNOWN_EL) != 0) return 2;

    facts = all_proven();
    facts.current_el_proven = 0U;
    if (expect(facts, ABORT_UNKNOWN_EL) != 0) return 3;

    facts = all_proven();
    facts.current_el = 0U;
    if (expect(facts, ABORT_UNKNOWN_EL) != 0) return 19;

    facts = all_proven();
    facts.stack_proven = 0U;
    if (expect(facts, ABORT_BAD_STACK) != 0) return 4;

    facts = all_proven();
    facts.translation_proven = 0U;
    if (expect(facts, ABORT_TRANSLATION_UNKNOWN) != 0) return 5;

    facts = all_proven();
    facts.mappings_proven = 0U;
    if (expect(facts, ABORT_MAPPING_UNPROVEN) != 0) return 6;

    facts = all_proven();
    facts.memory_ownership_proven = 0U;
    if (expect(facts, ABORT_MEMORY_OWNERSHIP_UNPROVEN) != 0) return 7;

    facts = all_proven();
    facts.collision_audit_complete = 0U;
    if (expect(facts, ABORT_COLLISION) != 0) return 8;

    facts = all_proven();
    facts.collision_free = 0U;
    if (expect(facts, ABORT_COLLISION) != 0) return 9;

    facts = all_proven();
    facts.descriptor_prefix_trusted = 0U;
    if (expect(facts, ABORT_DESCRIPTOR_INVALID) != 0) return 10;

    facts = all_proven();
    facts.descriptor_structure_valid = 0U;
    if (expect(facts, ABORT_DESCRIPTOR_INVALID) != 0) return 11;

    facts = all_proven();
    facts.output_buffer_valid = 0U;
    if (expect(facts, ABORT_OUTPUT_BUFFER_INVALID) != 0) return 12;

    facts = all_proven();
    facts.persistence_policy_proven = 0U;
    if (expect(facts, ABORT_PERSISTENCE_POLICY) != 0) return 13;

    facts = all_proven();
    facts.persistent_write_required = 1U;
    if (expect(facts, ABORT_PERSISTENCE_POLICY) != 0) return 14;

    facts = all_proven();
    facts.pre_kernel_gate_evaluated = 0U;
    if (expect(facts, ABORT_TRANSFER_GATE_BLOCKED) != 0) return 15;

    facts = all_proven();
    facts.pre_kernel_gate_satisfied = 0U;
    if (expect(facts, ABORT_TRANSFER_GATE_BLOCKED) != 0) return 16;

    facts = all_proven();
    if (expect(facts, OK_TO_EVALUATE_TRANSFER) != 0) return 17;

    return 0;
}
