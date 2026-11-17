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
