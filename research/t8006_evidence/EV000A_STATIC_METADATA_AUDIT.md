# EV-000A static target metadata audit

Audit baseline: ea3690f97805b8a68eacd879a2419463b156489a (master).
Scope: existing repository artifacts only. No Watch/iPhone interaction, new
acquisition, firmware execution, or device-state change was performed.

## Evidence policy

The hashes below make the checked-in local artifact bytes reproducible. A
local SHA-256 does not authenticate Apple as the source, prove a particular
physical Watch produced an artifact, or establish runtime state. The original
OTA and raw DeviceTree/kernelcache payloads are not present in the repository.
docs/DEVTREE_REPORT.md records the OTA SHA-256 as
f331199e8415ecbc75df0c8a6e1974c4f54acfc5c2ea1555f6daefff92ddcc78, but that
archive hash cannot be rechecked against the absent archive here.

## Local source inventory

| Artifact | Local SHA-256 | Use / limitation |
|---|---|---|
| research/ipsw/21U580/BuildManifest.plist | faa2132c1d59a71b1ffff2326d1b0ee382b97a81dd614c9ef9e3468c0f830093 | Explicit Watch4,2 / N131bAP / chip / version / build identity; names the kernelcache component but does not contain its bytes. |
| research/ipsw/21U580/Restore.plist | 4ccfab3f140a08ea1ed6836993e92fe3069611d6d3d24bf027e8654311be7e60 | Explicit board config, platform and chip ID, plus product/version/build. |
| research/ipsw/21U580/Info.plist | dccf5671ccd25b8629ea733a68fcdf3f8ac8eb54203d91e8b32fbb421fd036be | Supported device/model and OS/build metadata. |
| research/ipsw/21U580/AssetData_Info.plist | 43f60b9acb6c06c1bb8cdcb4aab8561bdb01575a1b05518a7baf46d19e9ea656 | HardwareModel, ProductType, ProductVersion and Build. |
| research/ipsw/21U580/analysis_summary.txt | e5c9fa70e70240be4f5da0220d875440b717f14ebbf72c0724e5badff814998d | Parsed static ADT root properties, including N131bAP and Watch4,2. |
| research/ipsw/21U580/nodes_dump.txt | c5e202a13937e975fd46ad675fb673ff47e2c7fce535aad60308aea3bf8c92ef | Static ADT node data, including apple,tempest CPU compatibles and T8006-compatible devices; not a target-kernel ISA header. |
| docs/DEVTREE_REPORT.md | 0b035360ba92d25a9c2f1c1bb8c0b9bd458679c92b31e7f4f538f31c137d9fa5 | Records the claimed OTA source path/hash for the ADT extraction; it is a report, not the absent OTA/ADT binary. |
| research/t8006_evidence/observed_watchos_report.json | e1e12a750d0eb1518f576c899f3dc91346ee11fcb0bd8d7afacc24436dad656e | Sanitized extraction from the supplied IPS; report-content evidence, not independent source authentication. |
| research/t8006_evidence/watchos_report_provenance_envelope.json | cb5716f0ab7ae907dceda31f60a1ed66fb3887bd98e0c6c8936f207c034be9c4 | Current envelope leaves board/architecture and metadata_match absent; source evidence status is UNKNOWN. |

## Per-field result

The field table uses abbreviated hash labels for readability; each label maps
to one full SHA-256 in the source inventory immediately above.

| FIELD | VALUE | SOURCE ARTIFACT / SHA-256 | EXACT EVIDENCE | TARGET SPECIFICITY | PROVEN | WHY |
|---|---|---|---|---|---|---|
| model | Watch4,2 | BuildManifest.plist (faa213…0093); AssetData_Info.plist (43f60b…a656); analysis_summary.txt (e5c9fa…998d); IPS record (e1e12a…656e) | BuildManifest Ap,ProductType and SupportedProductTypes; asset ProductType; ADT root model; IPS modelCode. | Exact 21U580 package profile plus report content. | YES — static profile and report content | Direct values agree; this does not identify a unique physical Watch or authenticate the IPS source. |
| board | N131bAP / normalized n131bap | BuildManifest.plist (faa213…0093); Restore.plist (4ccfab…7e60); Info.plist (dccf56…36be); AssetData_Info.plist (43f60b…a656); analysis_summary.txt (e5c9fa…998d) | Ap,Target=N131bAP; DeviceClass=n131bap; BoardConfig=n131bap; SupportedDeviceModels / HardwareModel=N131bAP; ADT target-sub-type and compatible=N131bAP. | Explicit in 21U580 package metadata and static ADT; not inferred from Watch4,2. | YES — static profile | Multiple direct fields spell out the board; no model-to-board inference is used. |
| SoC | T8006 | BuildManifest.plist (faa213…0093); Restore.plist (4ccfab…7e60); nodes_dump.txt (c5e202…92ef); IPS record (e1e12a…656e) | ApChipID=0x8006; Restore Platform=t8006, CPID=32774 (0x8006); ADT T8006-compatible nodes; IPS AppleT8006 markers. | Exact firmware package profile; runtime markers are corroborating report content only. | YES — static package metadata | Chip/platform fields directly encode T8006. This does not prove live register state or a loader environment. |
| watchOS | 10.6.1 | BuildManifest.plist (faa213…0093); Restore.plist (4ccfab…7e60); Info.plist (dccf56…36be); AssetData_Info.plist (43f60b…a656); IPS record (e1e12a…656e) | ProductVersion / OSVersion=10.6.1; IPS os_version=Watch OS 10.6.1 (21U580). | Exact package profile plus report content. | YES — metadata values | Direct fields agree. |
| build | 21U580 | Same package sources above plus IPS record (e1e12a…656e) | ProductBuildVersion, Build, and IPS build substring are 21U580. | Exact package profile plus report content. | YES — metadata values | Direct fields agree. |
| target/kernel architecture | AArch64 | BuildManifest.plist (faa213…0093; full SHA above) names KernelCache path kernelcache.release.watch4 and declares a 48-byte digest; the kernelcache binary is absent. IPS record (e1e12a…656e) reports process cpuType=ARM64_32. | Manifest-declared component digest, decoded from its plist bytes: fe8df14d2739b5be99e010c4573a95ea376efa9f46c66622974281405632780935df776b0a1c21775c4fbccfb8e95f5c. No target-kernel Mach-O header or equivalent ISA evidence is present. IPS cpuType is process/runtime ABI data, not DreyzeOS loader architecture. The DreyzeOS ELF can establish only its own image format. | Target-specific proof absent. | NO | A package component name/digest is not a Mach-O architecture header. Exact kernelcache bytes are not in the checkout; the prior header assertion is not reproducible from current files. apple,tempest DeviceTree compatibles alone do not close this requirement. |
| metadata_match | true not established | Current envelope (cb5716…be9c4); sources above | Envelope target.metadata.board and .architecture are absent, metadata_match is absent, and source evidence_status=UNKNOWN. | Must cover the complete fixed project target and not imply physical identity. | NO | Architecture evidence is missing; the existing IPS source remains user-reported and the envelope does not record a proven complete comparison. Do not set this fact to true. |

## Conclusion

The old statement in docs/PRE_HARDWARE_AUDIT.md that target AArch64 mode is
confirmed by a kernelcache Mach-O header is not reproducible from this
checkout: no kernelcache.macho or kernelcache.release.watch4 file exists under
the 21U580 research directory. The BuildManifest component digest can identify
a future exact artifact, but does not reveal its Mach-O CPU type without the
bytes.

The static 21U580 package metadata now CONFIRMS the expected Watch4,2 /
N131bAP / T8006 / watchOS 10.6.1 / 21U580 profile at the artifact-content
level. It does not bind the old IPS to a persistent physical unit, prove the
IPS source independently, or provide target-kernel AArch64 evidence. DreyzeOS
being built as AArch64 is a project/image fact, not proof of target execution
compatibility.

EV-000A remains BLOCKED; metadata_match must remain absent/unproven. EV-000B
and EV-000C are unchanged. The smallest next static evidence item is the exact
kernelcache.release.watch4 component for this BuildManifest, with its package
association and declared digest verified, followed by inspection of its
Mach-O CPU type. Even then, only set metadata_match=true if the envelope's
complete metadata and source-status rules are met. No hardware interaction is
implied or authorized by this audit.

Final hardware gates remain:

    LOADER CONTRACT = BLOCKED
    FIRST HARDWARE EXECUTION = NOT READY
