# D213ECV single-file system update / 单镜像系统更新

This package targets the existing **D213ECV-DEMO-V4-0**, 128 MiB SPI NAND,
with its factory partition layout and Recovery already present. It is an
**experimental Linux 6.18.52 system installation**, not a hardware-verified
bootable release. The operator has verified vendor Linux 5.10.44 plus the new
Buildroot rootfs; Linux 6.18 still needs physical boot evidence.

## What is installed

One AiBurn `.img` contains all normal system installation targets:

| NAND target | Contents |
| --- | --- |
| spl | Pinned vendor SPL + DDR/PBP boot resources |
| uboot | Vendor U-Boot 2021.10 FIT with vendor OpenSBI 0.9 and DTB |
| env and env_r | Factory layout plus a debuggable normal-U-Boot boot policy |
| logo | Pinned vendor logo FIT |
| kernel | Linux 6.18.52, load/entry 0x40200000, optional E0–E5 instrumentation |
| ubiroot:rootfs | Independent Buildroot UBIFS rootfs |

**Recovery, BBT, userid, Falcon partition and ubisystem:user are not targets.**
The package is a complete normal-system update on an existing factory-layout
board. It intentionally does not recreate Recovery on a blank/repartitioned
NAND or represent a 128 MiB raw NAND clone. Do not choose full-chip erase.

This is broader than the earlier rootfs-only and kernel+rootfs updates:
it also replaces SPL, U-Boot, OpenSBI and persistent environment settings.
These newly built boot components passed compilation/static packaging checks;
their successful execution on hardware has not been established.
Have the board's known-good factory image and ROM/AiBurn recovery procedure
available before deciding to replace the boot components.

The environment changes are tracked in
`board/artinchip/d213ecv-demo128-nand/system-update-env.json`:
`boot_os=no` forces the normal U-Boot path, bootdelay=3 permits interruption,
MMIO earlycon and ttyS0 console are explicit, quiet is removed, and nand_boot
omits falcon_save. The existing Falcon bytes are preserved and not trusted
for the replacement kernel. Recovery boot selection remains supported by the
vendor branch in nand_boot. Both environment partitions are deliberately
replaced; save any board-specific custom environment beforehand.

## Reproduction

Build the normal M1 board profiles and vendor boot components as documented
in [M1](m1-d213ecv.md), then build the [M2 RAM diagnostic bundle](m2-early-boot-debug.md).
As an ordinary user, from the project root:

```sh
export PATH="$PWD/output/d213ecv-demo128-nand/host/bin:$PATH"
.cache/firmware-venv/bin/python scripts/firmware.py pack --system-update \
  --components .cache/vendor-boot/components \
  --kernel artifacts/d213ecv-linux618-ram-debug/diagnostic-40200000.itb \
  --rootfs output/d213ecv-demo128-nand-linux618/images/rootfs.ubifs \
  --output artifacts/d213ecv-linux618-system-update
python3 scripts/firmware.py verify --system-update \
  artifacts/d213ecv-linux618-system-update/d213ecv-linux618-system-update.img
(cd artifacts/d213ecv-linux618-system-update && sha256sum -c SHA256SUMS)
```

Use a fresh output directory when repackaging. The explicit `--system-update`
flag enables the larger persistent write target set. The default verifier and
default pack behavior retain the M1 selective-update policy. System verification
requires all system components and exact env;env_r mapping, rejects Recovery
or other protected targets, and checks partition capacities and CRCs. Packing
also checks FIT payload hashes, RISC-V Image/RAM layout, UBIFS geometry,
factory environment CRC/layout, component provenance, and agreement between
the OpenSBI in the kernel FIT and the boot component manifest.

`firmware-manifest.json` records the actual component/rootfs hashes and boot
environment overrides. SHA256SUMS covers the final package and manifests.
CI reproduces the package after the M1/M2 builds and static tests and uploads
it under `artifacts/d213ecv-linux618-system-update/` in the board artifact.
CI success is software evidence only.

## AiBurn and serial verification / 烧录与验证

1. 核对板卡为 D213ECV-DEMO-V4-0、128 MiB SPI NAND，保留原厂完整固件和恢复方法。
2. 选择 `d213ecv-linux618-system-update.img`，先验证同目录 SHA256SUMS。
3. 在匹配板卡的原厂 AiBurn 中核对写入目标为上表七个分区/卷（env 与 env_r
   分别计数）。不要启用整片擦除，不修改分区表；Recovery、BBT、userid、Falcon
   和 ubisystem 必须保留。AiBurn 识别和实际写入本包尚需操作者验证。
4. 此包会更新 SPL/U-Boot/OpenSBI/环境，不要把它当成之前仅更新 RootFS 的包。
   若暂不希望更换启动组件，请先使用 M2 的 SD/RAM 调试包。
5. 从复位前开始采集 115200 8N1、无流控的完整串口日志，记录 OpenSBI、U-Boot、
   Linux 标记和最后停机位置。没有 Linux 输出时，不反复全片重刷，反馈完整日志。
6. 若进入 Shell，收集 uname -a、/proc/cmdline、/proc/mtd、mount、ubinfo -a、dmesg。
   先确认 Kernel 6.18、UBIFS 挂载与分区表，再单独验证持久化和恢复。

Flashable container generation does not establish physical bootability.
Linux 6.18 must not be advertised as working until serial evidence is obtained.

## OpenSBI status and upgrade route

OpenSBI is resident RISC-V **M-mode firmware**. It provides the SBI interface
used by S-mode U-Boot/Linux for timers, hart control and other machine services.
In this board's normal path: Boot ROM → DDR/PBP/SPL → OpenSBI → U-Boot → Linux.
The resident firmware is started by SPL from the U-Boot FIT; replacing an
OpenSBI blob carried in a kernel FIT alone does not update that resident copy
when booting through normal U-Boot.

The board currently retains vendor OpenSBI **0.9**, pinned by Luban source commit
`6812c56d060c7e88e5e5e831a7c915227485b788`. QEMU uses upstream **1.6**.
GitHub's upstream latest-release API reported **v1.9** (published 2026-07-01)
on 2026-11-18: https://github.com/riscv-software-src/opensbi/releases/tag/v1.9.
The reviewed release resolves to commit
`cbf9f6734dd85a982c63e3cb5db7ffe09da839ca`. This is release discovery,
not a new board build source pin or compatibility result.

Upstream v1.9 includes generic T-Head C9xx support. However, the pinned vendor
firmware adds `fw_save_boot_param`/`fw_get_boot_param`, a scratch slot and next
stage a3 forwarding. The vendor U-Boot expects that a3 to identify boot media
and boot reason. The upstream v1.9 `fw_dynamic.S` reviewed here does not retain
that custom protocol. The vendor 8250 FDT driver also recognizes
`artinchip,aic-uart-v1.0`; the reviewed upstream v1.9 8250 FDT match table
does not contain that compatible. The unchanged board DTB therefore needs
serial-binding/platform integration before assuming the generic platform
provides its console.
The board's PMP domain, C906 CSR/cache/errata/reset behavior, DT fixups and the
128 KiB resident region at 0x47fe0000 also require explicit review.

An upgrade is feasible as a separate board integration task: pin v1.9 source
and archive hash, document or replace the vendor boot-parameter ABI with a
standard handoff, adapt the minimum platform/serial/reset/PMP support, check
firmware size/runtime reservation and boot both unchanged 5.10 and 6.18 with
serial evidence. Test in a recoverable boot arrangement before distributing a
replacement persistent boot chain. Keep the known-good 0.9 image as a control.
**This system-update image deliberately contains vendor 0.9, not untested 1.9.**
