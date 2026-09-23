/*
 * The executable is a Linux host fixture, not an Apple Watch entry point.
 * Empty evidence must fail closed at the first unmet prerequisite.
 */
#include "stage0_reference.h"

int main(void) {
    const stage0_gate_facts_t absent_evidence = {0};
    const stage0_result_t result =
        stage0_reference_evaluate(&absent_evidence);

    return (result.status == ABORT_UNKNOWN_EL &&
            result.transfer_performed == 0U) ? 0 : 1;
}
