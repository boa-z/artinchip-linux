# Hardware research and upstream strategy

## Scope and reference snapshots

This is an initial source review, not a hardware validation or a complete license
audit. No vendor code is copied into the M0 platform or made a build dependency.

- [Luban](https://github.com/boa-z/luban), local reference snapshot
  `6812c56d060c7e88e5e5e831a7c915227485b788`.
- [d211-linux-6.18](https://github.com/boa-z/d211-linux-6.18), existing local
  checkout at `d8e6fff434d60e0e5198d70296d8d94df548962d`.

The SDK's Linux 6.18 reference is a separate Git repository already present
inside the local SDK source area. Neither repository needed to be cloned.
Local paths and machine configuration are deliberately absent from this document.

## Initial observations

Luban's `target/d211/common/d211.dtsi` separates SoC description from board
configuration, includes OpenSBI domain descriptions and refers to a C906 CPU
region. Its header grants a per-file GPL v2-or-later or X11 license choice; that
permission explicitly does not cover the whole SDK. New bindings and DTS should
be checked file by file and expressed using current upstream schemas.

`source/uboot-2021.10/configs/d211_demo_defconfig` selects RISC-V S-mode U-Boot,
SPL, SPL RAM support and OpenSBI loading. The SDK's `package/opensbi/opensbi.mk`
uses the generic platform with extra vendor build options. These are clues for
the boot-chain investigation; they do not establish a required modern boot order
or justify importing the SDK packaging logic.

The Linux 6.18 reference contains ArtInChip clock/reset, pinctrl, DMA, UART,
MMC, SPI, I2C, watchdog, RTC, thermal and other drivers. Availability in that fork
does not establish upstream acceptance or compatibility with newer kernels.
Audit each candidate against the current subsystem before reuse. Multimedia and
display code remain outside this milestone.

## Next research steps

1. Compare current mainline support for C906-based Allwinner D1 and other RISC-V
   SoCs, including generic interrupt, timer, UART and cache-management paths.
2. Identify which D211 blocks match an existing documented IP block; use generic
   subsystem drivers only when register layout and behavior actually match.
3. Establish a minimal UART/timer/interrupt boot path before clocks, resets,
   pinctrl and storage. Review firmware responsibilities before adding kernel
   architecture hooks or vendor SBI calls.
4. Investigate current U-Boot SPL DDR setup, standard FIT/binman packaging and
   OpenSBI generic platform/FDT support against the ROM's documented requirements.
5. Keep D211 and D213 descriptions distinct until differences are supported by
   manuals or measured hardware behavior. Do not infer D213 support from D211.

No implementation is selected solely because it exists in the vendor tree.
Each future reuse decision must record provenance, license, upstream alternative,
interface changes and real hardware tests. Board enablement is a separate phase.

## Current upstream comparison (2026-11-17)

kernel.org listed mainline 7.4-rc3, stable 7.3.5 and longterm 6.18.64 during this
review. M0 deliberately retains Buildroot's 6.18.7 QEMU baseline and tests 7.3.5
separately. A later hardware kernel update should evaluate the current 6.18 LTS
patch level after establishing the reference fork's behavior.

The current Allwinner D1 description splits shared IP from board descriptions
and reuses compatible IP bindings. StarFive JH7110 supplies standard CPU cache
properties plus `riscv,isa-base` and `riscv,isa-extensions`, rather than making
new firmware interfaces out of device-tree properties. These are useful review
patterns, not evidence that their drivers match ArtInChip register layouts.

OpenSBI's current generic-platform documentation explicitly includes T-HEAD C9xx
and relies on FDT console, timer and IPI drivers. The latest release observed was
1.9; M0 pins 1.6. Evaluate existing T-HEAD cache/errata support before introducing
another private platform or SBI extension.

U-Boot's current RISC-V guide documents the conventional SPL -> OpenSBI -> S-mode
U-Boot -> Linux path, using FIT to carry firmware and U-Boot. The latest stable tag
observed was v2026.10, with v2027.01 release candidates available. Board work must
first understand the factory's DDR and ROM constraints, then assess which vendor
changes can be replaced with current driver-model/SPL implementations.

References reviewed:

- <https://www.kernel.org/releases.json>
- <https://github.com/torvalds/linux/tree/master/arch/riscv/boot/dts/allwinner>
- <https://github.com/torvalds/linux/blob/master/arch/riscv/boot/dts/starfive/jh7110.dtsi>
- <https://github.com/riscv-software-src/opensbi/blob/master/docs/platform/generic.md>
- <https://github.com/riscv-software-src/opensbi/blob/master/docs/platform/thead-c9xx.md>
- <https://docs.u-boot.org/en/latest/arch/riscv.html>
