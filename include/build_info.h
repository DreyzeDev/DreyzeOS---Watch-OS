/*
 * DreyzeOS — Build Provenance & Version Header
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 */

#pragma once

#include "types.h"

#ifndef DREYZEOS_VERSION_STRING
#define DREYZEOS_VERSION_STRING "DreyzeOS 0.1.0-research"
#endif

#ifndef DREYZEOS_TARGET
#define DREYZEOS_TARGET "Apple Watch Series 4 / T8006"
#endif

#ifndef DREYZEOS_ARCH
#define DREYZEOS_ARCH "AArch64"
#endif

#ifndef GIT_COMMIT_SHA
#define GIT_COMMIT_SHA "unknown"
#endif

#ifndef DREYZEOS_CANONICAL_BRANCH
#define DREYZEOS_CANONICAL_BRANCH "master"
#endif

typedef struct {
    const char *version_string;
    const char *target;
    const char *arch;
    const char *git_commit_sha;
    const char *canonical_branch;
    uint32_t   fb_test_pattern_enabled;
} build_provenance_t;

/* Retrieve build provenance metadata */
const build_provenance_t *build_get_provenance(void);
