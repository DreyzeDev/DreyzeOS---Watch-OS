# EV-000A static target metadata audit

Audit baseline: 339df831fc26f8da5b0021bcee3b94b0e89412c5 (master).
Scope: static/offline inspection only. No Watch/iPhone interaction, firmware
execution, payload execution, or device-state change was performed.

## Evidence policy

The hashes below make the inspected bytes reproducible. The exact OTA was not
downloaded in full: only its BuildManifest and kernelcache ZIP entries were
fetched from the Apple CDN URL recorded in `ota_file_list.txt`. The remote
BuildManifest entry was byte-identical to the checked-in manifest, and the
kernelcache component's SHA-384 matched the digest declared by that manifest.
The whole-archive SHA-256 was not recomputed locally. These checks establish
component-to-manifest consistency, not cryptographic Apple signing,
physical-device identity, IPS source authentication, or runtime state.

## Local source inventory

| Artifact | Local SHA-256 | Use / limitation |
|---|---|---|
| research/ipsw/21U580/BuildManifest.plist | faa2132c1d59a71b1ffff2326d1b0ee382b97a81dd614c9ef9e3468c0f830093 | Exact package BuildManifest; its fetched OTA entry is byte-identical and it declares the kernelcache component digest. |
| research/ipsw/21U580/Restore.plist | 4ccfab3f140a08ea1ed6836993e92fe3069611d6d3d24bf027e8654311be7e60 | Explicit board config, platform and chip ID, plus product/version/build. |
| research/ipsw/21U580/Info.plist | dccf5671ccd25b8629ea733a68fcdf3f8ac8eb54203d91e8b32fbb421fd036be | Supported device/model and OS/build metadata. |
| research/ipsw/21U580/AssetData_Info.plist | 43f60b9acb6c06c1bb8cdcb4aab8561bdb01575a1b05518a7baf46d19e9ea656 | HardwareModel, ProductType, ProductVersion and Build. |
| research/ipsw/21U580/analysis_summary.txt | e5c9fa70e70240be4f5da0220d875440b717f14ebbf72c0724e5badff814998d | Parsed static ADT root properties, including N131bAP and Watch4,2. |
| research/ipsw/21U580/nodes_dump.txt | c5e202a13937e975fd46ad675fb673ff47e2c7fce535aad60308aea3bf8c92ef | Static ADT node data, including apple,tempest CPU compatibles and T8006-compatible devices; not a target-kernel ISA header. |
| docs/DEVTREE_REPORT.md | 0b035360ba92d25a9c2f1c1bb8c0b9bd458679c92b31e7f4f538f31c137d9fa5 | Records the claimed OTA source path/hash for the ADT extraction; it is a report, not the absent OTA/ADT binary. |
| research/t8006_evidence/observed_watchos_report.json | e1e12a750d0eb1518f576c899f3dc91346ee11fcb0bd8d7afacc24436dad656e | Sanitized extraction from the supplied IPS; report-content evidence, not independent source authentication. |
| research/t8006_evidence/target_kernel_architecture_21U580.json | 912829aef2fe9c21b8cd833bb782773248f894a6534467346269bf0095c958db | Sanitized package-provenance and Mach-O-header result; firmware bytes remain outside Git. |
| research/t8006_evidence/watchos_report_provenance_envelope.json | 3cefa8230a7474dce99851ba822527a095d12611929bbce4a31e4fdd08812c41 | Records all target metadata fields and a proven content/profile metadata match; report source evidence status remains UNKNOWN. |

## Exact kernelcache provenance chain

The OTA file list points to the Apple CDN package URL recorded in
`research/ipsw/21U580/ota_file_list.txt` and lists the archive size as
2,780,878,873 bytes. The CDN HEAD response advertised the same outer SHA-256
as that record (`f331199e...ddcc78`); the complete archive was not locally
downloaded or hashed.

The OTA ZIP's `AssetData/boot/BuildManifest.plist` entry was range-fetched,
Deflate-decoded, CRC-32 checked, and compared byte-for-byte with the checked-in
manifest (SHA-256
`faa2132c1d59a71b1ffff2326d1b0ee382b97a81dd614c9ef9e3468c0f830093`). Its
BuildIdentity 0 explicitly names `Watch4,2`, `N131bAP`, chip ID `0x8006`,
watchOS `10.6.1`, build `21U580`, and
`Manifest.KernelCache.Info.Path=kernelcache.release.watch4`.

The matching ZIP member is `AssetData/boot/kernelcache.release.watch4`.
After ZIP Deflate decoding its 15,221,732 bytes are an IM4P container of type
`krnl` (description `KernelCacheBuilder_release-2674.140.2`). SHA-384 of those
exact wrapper bytes is
`fe8df14d2739b5be99e010c4573a95ea376efa9f46c66622974281405632780935df776b0a1c21775c4fbccfb8e95f5c`,
exactly matching the 48-byte digest in the fetched, byte-identical BuildManifest.
This establishes the digest algorithm by direct match, not by assuming it from
the digest length.

The IM4P OCTET STRING payload begins with LZFSE signature `bvx2`; offline
LZFSE decoding yields a 46,825,472-byte Mach-O. The inner header is:

| Field | Exact value | Interpretation |
|---|---|---|
| Magic | `0xfeedfacf` (`cf fa ed fe`) | 64-bit Mach-O, little-endian |
| `cputype` | `0x0100000c` | `CPU_TYPE_ARM64` |
| `cpusubtype` | `0x00000002` | ARM64E subtype |
| `filetype` | `0x0000000c` | `MH_FILESET` |
| Architecture | AArch64 / ARM64E | CONFIRMED for this exact 21U580 kernelcache component |

The exact intermediate/output sizes and SHA-256/SHA-384 values are recorded
in `target_kernel_architecture_21U580.json`. The untouched component wrapper,
LZFSE payload, and Mach-O are retained only in the local analysis cache outside
the repository; no Apple firmware binary is committed.

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
| target/kernel architecture | AArch64 (ARM64E) | Exact OTA kernelcache component; see `target_kernel_architecture_21U580.json` | Mach-O magic `0xfeedfacf`, `cputype=0x0100000c` (`CPU_TYPE_ARM64`), subtype `2` (ARM64E); component SHA-384 matches BuildManifest digest. | Exact Watch4,2 / N131bAP / T8006 / 21U580 package component. | YES — exact target binary header | The process `ARM64_32` field is not used as kernel architecture evidence. This proves kernel ISA, not loader state or DreyzeOS handoff compatibility. |
| metadata_match | true | Updated provenance envelope plus exact package/profile evidence above | Model, board, SoC, OS, build, and target-kernel architecture all match the fixed project target; explicit `metadata_match=true` fact is recorded. | Target metadata consistency only; no persistent-device identity claim. | YES — content/profile comparison | The envelope validator reports EV-000A proof state `PROVEN` but status `LIKELY` because its IPS source attribution remains `UNKNOWN`; physical identity and EV-000B remain separate. |

## Conclusion

The prior architecture gap is closed: the exact `kernelcache.release.watch4`
component from the 21U580 Watch4,2 package matches the BuildManifest's declared
SHA-384 and its inner Mach-O header is ARM64E/AArch64. The fixed target profile
metadata comparison is now explicitly true and complete. The verifier reports
EV-000A proof state `PROVEN` / status `LIKELY`, because the pre-existing IPS
export's source attribution remains `UNKNOWN`; this does not make the IPS
authentic, bind it to a physical unit, or satisfy EV-000B.

EV-000B remains BLOCKED and EV-000C remains UNKNOWN/non-critical. The exact
kernel architecture does not prove DreyzeOS placement, executable mapping,
entry EL, stack, CPU/MMU state, memory ownership, collisions, or control
transfer. No hardware interaction is implied or authorized.

Final hardware gates remain:

    LOADER CONTRACT = BLOCKED
    FIRST HARDWARE EXECUTION = NOT READY
