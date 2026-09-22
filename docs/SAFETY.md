# DreyzeOS Safety Analysis

## Purpose

This document tracks the safety risk of every operation performed or considered
for the DreyzeOS research project on physical Apple Watch hardware.

**Ground Rule**: Any operation not explicitly marked SAFE is treated as UNSAFE
until proven otherwise.

---

## Safety Operation Table

| Operation | Risk Level | Reversible? | Can Reboot? | Bootloop Risk? | Touches Flash? | Tested on Series 4? | Notes |
|-----------|-----------|-------------|-------------|----------------|----------------|----------------------|-------|
| Reading device information (model, UDID) | NONE | N/A | No | No | No | CONFIRMED | Normal operation |
| Entering DFU mode | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | No | UNKNOWN | Public stock procedure is documented, but it was not executed or verified on this target |
| Entering Recovery mode | UNKNOWN/BLOCKED | UNKNOWN | UNKNOWN | UNKNOWN | No | UNKNOWN | Stock recovery/restore documentation is context only; arbitrary experimental-state recovery was not verified on this target |
| Reading kernelcache via Peepo | LOW-MED | YES | Possibly | No | No | UNKNOWN/BLOCKED for Watch4,2 | Public source targets Watch4,1; no device run |
| Reading DeviceTree via Peepo | LOW-MED | YES | Possibly | No | No | UNKNOWN/BLOCKED for Watch4,2 | Same constraints as kernelcache |
| RAM-only code injection via PongoOS | UNKNOWN/BLOCKED | UNKNOWN | UNKNOWN | UNKNOWN | NO | UNKNOWN for T8006 | PongoOS is a different-SoC reference; no DreyzeOS run or recovery proof |
| checkm8 DFU exploit on T8006 | BLOCKED | N/A | N/A | N/A | NO | CONFIRMED not a checkm8 target | Separate usbliter8 T8006 research was inspected statically only; no exploit execution |
| Modifying system partition | EXTREME | NO | Yes → bootloop | HIGH | YES | **NEVER** | PROHIBITED by project rules |
| Overwriting iBoot | EXTREME | NO (brick) | N/A | CERTAIN | YES | **NEVER** | PROHIBITED — permanent brick |
| Overwriting SecureROM area | EXTREME | NO (permanent) | N/A | CERTAIN | YES | **NEVER** | PROHIBITED — permanent brick |
| Writing to NAND flash | HIGH | Partial only | N/A | HIGH | YES | **NEVER** | PROHIBITED by project rules |
| Loading unsigned code via RAM exploit | UNKNOWN/BLOCKED | UNKNOWN | UNKNOWN | UNKNOWN | NO | UNKNOWN/BLOCKED | Requires a proven loader/handoff contract; recovery is not guaranteed |
| Poking unknown MMIO addresses | HIGH | Maybe | Likely | Possible | No | **NEVER without research** | Can freeze or crash device |
| Reading from unknown MMIO | MEDIUM | YES | Possible | Low | No | UNKNOWN | Less dangerous than writing |
| Disabling WDT (watchdog timer) | MEDIUM | YES (reboot) | Possibly | Low | No | UNKNOWN | Common in OS research |

---

## Pre-Experiment Checklist

Before ANY experiment on physical Apple Watch Series 4:

- [ ] Experiment is documented in this file with risk assessment
- [ ] Operation is classified as REVERSIBLE
- [ ] Device UDID and hardware model confirmed
- [ ] watchOS version documented
- [ ] Backup/restore path confirmed (DFU restore available)
- [ ] Operation does NOT touch flash storage
- [ ] Minimum 2 sources confirm the approach works on Series 4 specifically
- [ ] SAFETY.md row is filled in for the specific operation

---

## Apple Watch Series 4 DFU Restore Procedure

The following is public stock-documentation context only; it was not executed in this audit and does not guarantee recovery from an arbitrary experimental state.

If an experiment causes a bootloop or unrecoverable state:

1. Force restart: Hold Digital Crown + Side Button for 10 seconds
2. Enter DFU mode: Hold Side Button + Digital Crown simultaneously after restart
3. Connect to Mac with Apple Configurator 2 or iTunes
4. Select "Restore" (requires internet connection to download watchOS)

> **MAC REQUIRED**: DFU restore of Apple Watch requires macOS with  
> Apple Configurator 2 or iTunes. Windows cannot restore Apple Watch firmware.  
> Reason: Apple's restore protocol for Watch requires signed IPSW loading  
> via Apple servers, and the USB protocol used is only supported by  
> Apple Configurator 2 / iTunes on macOS.

---

## Status of watchOS on Test Device

| Field | Value |
|-------|-------|
| Device model | UNKNOWN — confirm before experiments |
| Hardware identifier | UNKNOWN — confirm (Watch4,1/2/3/4) |
| watchOS version | UNKNOWN — confirm before experiments |
| Jailbreak status | UNKNOWN |
| DFU accessibility | UNKNOWN |

---

## Prohibited Operations (Absolute Rules)

These operations are **permanently prohibited** regardless of research goals:

1. ❌ Writing to NAND flash / system partition
2. ❌ Overwriting iBoot or SecureROM
3. ❌ Performing any destructive operation without a confirmed restore path
4. ❌ Experimenting on a device you cannot afford to restore/replace
5. ❌ Claiming an operation is safe without documented confirmation on Series 4

---

## Philosophy

> "Reversibility is the most important property of any experiment."
>
> If you cannot restore the device to factory state, do not perform the experiment.
> A bricked Apple Watch with no macOS restore path is a dead device.
