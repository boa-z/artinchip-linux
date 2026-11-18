# M2: D213ECV Linux 6.18 early boot / 早期启动调试

Physical target: **ArtInChip D213ECV-DEMO-V4-0**, 128 MiB DDR3 and
128 MiB Winbond SPI NAND. `d211_demo128_nand` is a legacy vendor profile name.

## Evidence and scope

The operator reports real-board M1 success: vendor Linux **5.10.44** boots the
independent Buildroot rootfs in `ubiroot:rootfs`; SPI NAND, UBI, UBIFS, BusyBox,
file I/O and persistence across reboot pass. This is operator-supplied evidence,
not a new automated hardware test. The original recovery and NAND layout remain.

Linux **6.18.52** currently reaches only U-Boot's `Starting kernel ...`.
SD `fatload`, `iminfo`, all three FIT hashes, kernel decompression and FDT loading
were observed to pass. Neither `earlycon=sbi` nor
`earlycon=uart8250,mmio32,0x18710000` produced subsequent Linux output.
**Linux 6.18 hardware boot is not verified.** Static checks and CI cannot change
that status. No new NAND image is needed for this experiment.

## Address investigation and evidence

The pinned Linux tree is `boa-z/d211-linux-6.18` commit
`d8e6fff434d60e0e5198d70296d8d94df548962d`. The pinned U-Boot/OpenSBI source is
`boa-z/luban` commit `6812c56d060c7e88e5e5e831a7c915227485b788`.
Analysis uses the exported committed sources, not uncommitted reference edits.

Relevant Linux sources are `Documentation/arch/riscv/boot.rst`,
`Documentation/arch/riscv/boot-image-header.rst`,
`arch/riscv/include/asm/image.h`, `arch/riscv/kernel/head.S`, and
`arch/riscv/mm/init.c:setup_vm()`. The boot ABI requires a0=boot hart,
a1=physical DTB, satp=0 and a PMD-aligned physical kernel (2 MiB for RV64).
Header 0.2 declares `RISCV\0\0\0`, `RSC\x05`, flags=0, and S-mode RV64
`text_offset=0x200000`. Header `image_size` includes the runtime footprint,
including BSS; it must not be replaced by compressed length or file length.

`DDR base + text_offset` is **0x40200000**. This is the header-consistent
candidate used by the U-Boot RISC-V `booti_setup()` relocation rule. However,
**0x40000000 is also 2 MiB aligned**. Linux derives physical `_start` with
PC-relative early code and checks PMD alignment; the offset alone does not
prove the old placement causes the silence. The vendor 5.10 `head.S` also
contains the same S-mode offset. Do not describe the candidate as a proven fix.

In vendor U-Boot, `common/bootm.c` takes a normal FIT kernel's load/entry from
FIT properties; `arch/riscv/lib/bootm.c:boot_jump_linux()` calls `images->ep`
with `gd->arch.boot_hart` and the fixed-up FDT. It does not apply the RISC-V
`booti_setup()` header relocation to this ordinary gzip FIT path. The first
Image instruction jumps to `_start_kernel`; FIT entry equals Image load, not
load+text_offset a second time. ELF entry is a **virtual** link address and
must not be used as the FIT physical entry. Per-variant `*-elf.txt` records
ELF LOAD virtual/physical values; ELF p_paddr values are image-relative in this
build, not proof of the board's actual load address.

U-Boot is S-mode; resident OpenSBI was entered earlier by SPL. The preserved
OpenSBI FIT blob is a compatibility payload, not a request to replace/restart
resident firmware in this normal `bootm` path. `cleanup_before_linux()` for
C906 disables interrupts, flushes and disables caches. Capture real `bdinfo`
and the final FDT before assuming the board has the same runtime placement.

## Config, console and device tree findings

The existing reference defconfig and final Buildroot config select
ARCH_ARTINCHIP, MACH_D211, MMU, RISCV_SBI, PRINTK, SERIAL_EARLYCON,
SERIAL_EARLYCON_RISCV_SBI, SERIAL_8250, SERIAL_8250_CONSOLE and
**SERIAL_8250_ARTINCHIP=y**. The UART driver and
`artinchip,aic-uart-v1.0` match are present and built in, not modules.
The kernel is S-mode, UP, with the inherited MEDLOW model and T-Head MAE/CMO
errata enabled. Do not infer that enabling optional ISA support means that
unsupported instructions execute unconditionally. Legacy `rv64gcxthead` DT
ISA parsing relies on RISCV_ISA_FALLBACK; C906 errata, SBI queries, SATP probing
and early alternatives remain suspects until stage markers locate the failure.

MEDLOW is inherited from vendor 5.10 and the 6.18 reference. This fork explicitly
compiles `mm/init.o`, early `alternative.o`, `cpufeature.o`, `sbi_ecall.o` and
T-Head errata code with MEDANY; it is not sufficient to blame MEDLOW without
examining the actual pre-MMU call chain. M2 retains the code model as a control.

Vendor 5.10 Kconfig defaults RISCV_SBI_V01 to y; Linux 6.18 removes that
default, and the inherited defconfig does not explicitly enable it.
The configuration comparison uses the pinned vendor 5.10 defconfig/Kconfig,
the pinned 6.18 reference defconfig/Kconfig and the actual Buildroot `.config`.
A factory fully resolved `.config` or `/proc/config.gz` was not supplied; 5.10
defaults are source evidence, not an extracted configuration of the running board.

| Setting | Vendor 5.10 source | 6.18 reference / M1 final | Optional diagnostic final |
| --- | --- | --- | --- |
| CMODEL | MEDLOW in defconfig | MEDLOW | MEDLOW |
| SBI v0.1 | default y | no default; final n | y |
| SBI earlycon | enabled in defconfig | y | y |
| 8250 console | enabled in defconfig | y | y |
| ArtInChip UART | vendor implementation present | built-in y | built-in y |
| MMU / privilege | S-mode vendor path | MMU=y, M_MODE off | unchanged |
| ARCH_ARTINCHIP / MACH_D211 | vendor legacy platform | y / y | unchanged |
| C906 MAE / CMO | vendor implementation | upstream-style T-Head errata y | unchanged |

A confirmed **console configuration defect** is RISCV_SBI_V01=n in the final
6.18 config. `drivers/tty/serial/earlycon-riscv-sbi.c:early_sbi_setup()` uses
DBCN if available, otherwise the legacy SBI console only when V01 is enabled;
otherwise it returns ENODEV. Vendor OpenSBI 0.9 implements legacy console
putchar (`lib/sbi/sbi_ecall_legacy.c`) and predates DBCN. Thus `earlycon=sbi`
cannot work with this existing configuration. This explains that failed
console choice, **not** the MMIO earlycon failure or the entire boot failure.
The optional diagnostic config enables V01; the normal M1 config is preserved.

The final DTB retains hart0, RV64, Sv39, 4 MHz timebase, vendor CLINT/PLIC
interrupt routing, 128 MiB memory at 0x40000000, and UART0 at 0x18710000,
reg-shift=2, reg-io-width=4. M2 checks these without changing clock, DMA or
pinctrl descriptions. The embedded `/chosen/bootargs` still contains
`rdinit=/init earlycon=sbi loglevel=7`; it is **not a usable NAND root command
line by itself**. Vendor U-Boot's `image_setup_linux()` / `fdt_chosen()` copies
the environment `bootargs` into the handoff DTB. Use the explicit temporary
command below and inspect the fixed-up `/chosen` before the final handoff.

## Build and artifact differences

First build the normal M1 Linux profile and boot components as described in
[m1-d213ecv.md](m1-d213ecv.md). Its existing `kernel-6.18.itb` is preserved.
Then, as an ordinary user, from the repository root:

```sh
JOBS=6 python3 scripts/ram-debug.py --diagnostic
(cd artifacts/d213ecv-linux618-ram-debug && sha256sum -c SHA256SUMS)
```

The output directory must be empty. Use `--output artifacts/<new-name>` for a
repeat run. The script verifies the pinned kernel archive, extracts separate
sources under ignored `output/`, applies versioned M1 and optional M2 patches,
and calls kernel make directly with the existing Buildroot cross compiler.
It does not invoke the Luban build system or edit the reference checkout.
Normal Buildroot output, rootfs, M1 FIT and NAND packages are not overwritten.

| FIT | Kernel/config | Load = entry | Purpose |
| --- | --- | --- | --- |
| `baseline-40000000.itb` | Existing M1 kernel | 0x40000000 | Exact address control |
| `offset-40200000.itb` | Same kernel bytes and DTB | 0x40200000 | Change only load/entry |
| `diagnostic-40200000.itb` | Opt-in markers + legacy SBI console | 0x40200000 | Locate pre-console failure |

Test baseline and offset with identical bootargs, reset between runs, then use
the diagnostic variant. Diagnostic config changes are explicitly two toggles:
D213ECV_EARLY_DEBUG=y and RISCV_SBI_V01=y. Keep that distinction when comparing.
SHA256SUMS covers all bundle files. `manifest.json` records the project commit,
dirty status, actual source/config/ELF/Image hashes, pinned source version and
checks. Each FIT has its own header/layout JSON and final `.config`; ELF
reports record actual link information. Dirty local builds are labeled as such.
A clean CI build provides commit-associated evidence once the workflow passes.

The FIT builder supports `--load 0x40200000 --entry 0x40200000`. Its default
remains the M1 load at 0x40000000, explicitly labeled as a legacy header-offset
exception in reports. Other header/load inconsistencies are rejected.

RAM checks use max(file size, header image_size) and half-open ranges. They
reject overlaps with FIT staging at 0x41200000 (actual FIT size), DTB staging
budget [0x42200000,0x42400000), resident SBI [0x47fe0000,0x48000000), DTB
reserved-memory entries, and a conservative U-Boot/heap/stack/relocated-FDT
guard [0x46000000,0x47fe0000). **The guard is a policy, not measured bdinfo.**
Pinned U-Boot reserves a top-of-RAM OpenSBI slot and Falcon/U-Boot FDT budgets;
normal `bootm` may relocate FDT. If real bdinfo/reservations differ, stop and
revise the explicit RAM plan. Do not disable relocation or set fdt_high blindly.

## Stage instrumentation

The optional GPL-2.0-only patch lives in
`board/artinchip/d213ecv-demo128-nand/debug-patches/`. The Kconfig default is n;
normal production/Buildroot profiles do not apply this patch. No UART clock,
baud divisor, reset or pinctrl is changed. UART must already work in U-Boot.
Each byte polls LSR.THRE at most 65536 times, then skips a byte on timeout.
Polling cannot time out an interconnect transaction that never returns; an
MMIO access fault remains possible on hardware, so no marker is proof of
absence of execution. Keep the uninstrumented address controls.

| Marker | Exact insertion | What reaching it establishes |
| --- | --- | --- |
| E0 | `head.S`, first `_start_kernel` instructions | Image entry branch reached, physical UART accessible |
| E1 | `head.S`, immediately before `call setup_vm` | CSR setup, BSS clear, hart save and initial stack reached |
| E2 | `head.S`, after `relocate_enable_mmu` returns | setup_vm, SATP transition and virtual return completed |
| E3 | `head.S`, before `call soc_early_init` | Trap vector, virtual stack/task environment restored |
| E4 | `head.S`, before `tail start_kernel` | soc_early_init returned; start_kernel is about to be entered |
| E5 | `earlycon.c`, after `register_console` | Earlycon setup returned a valid console and registration completed |

E0/E1 use physical UART0 MMIO. `setup_vm()` adds a dedicated FIX_M2_UART PTE
using PAGE_KERNEL_IO after establishing fixmap page tables. E2–E4 load its
virtual address from a data symbol assigned by setup_vm after SATP mode
selection (the fixmap address is not a compile-time constant in this kernel); E5 uses the same fixmap. No physical UART
pointer is dereferenced with MMU enabled. Assembly macros scratch only t0–t3
at sites where they are not live, preserve a0/a1, ra, sp and saved registers,
and use no stack/calls/ecalls before initialization. Firmware SBI is not used
by markers, allowing SBI failure to be investigated independently. Diagnostic
builds must compile and their head.o disassembly must be inspected; these are
still unverified hardware instrumentation.

Interpret the **last complete** marker: none = entry/handoff/UART access
unresolved; E0 = pre-setup_vm failure; E1 = setup_vm/early SBI/alternatives or
MMU transition; E2/E3 = post-MMU setup/SoC early init; E4 = start_kernel through
setup_arch/SBI/early parameter parsing before successful console registration;
E5 with no text = console write/output path. E4 is before the call, not proof
start_kernel executed its body. Preserve all partial characters and reset logs.
Additional instrumentation can then narrow a specific interval; these markers
do not identify an exact instruction or uniquely distinguish each SBI call.

## SD and U-Boot procedure (English)

Copy the three `.itb` files and SHA256SUMS to an existing readable FAT partition
on microSD using your workstation. Do not format NAND or replace the SD
partition table for this test. Verify hashes before copying and after reading
back. Capture **115200 8N1, no flow control**, from reset through the complete
experiment. Retain the initial factory boot log and bootargs/partition listing.

Interrupt normal boot. Record `version`, `bdinfo`, `printenv bootargs`,
`printenv bootcmd`, `printenv fdt_high`, `printenv bootm_low`,
`printenv bootm_size`. Ensure real relocation, stack/malloc and firmware/FDT
regions are clear of the reported ranges. A missing environment variable may
simply be unset. Do not publish unique identifiers or private host details.

Run each variant after a reset. Substitute only the FIT filename:

```text
mmc dev 0
mmc rescan
fatls mmc 0:1
setenv bootargs 'console=ttyS0,115200n8 earlycon=uart8250,mmio32,0x18710000,115200 keep_bootcon ignore_loglevel loglevel=8 memblock=debug ubi.mtd=10 root=ubi0:rootfs rootfstype=ubifs init=/linuxrc ro'
fatload mmc 0:1 0x41200000 baseline-40000000.itb
iminfo 0x41200000
bootm 0x41200000#conf-1
```

Repeat with `offset-40200000.itb`, then `diagnostic-40200000.itb`. The first
mount is read-only to protect the validated rootfs; do not run write tests or
force rw during this RAM experiment. An existing init script may attempt a
remount; capture that behavior and avoid writing application data. A root
mount or init failure after Linux logs is useful progress and must be reported.

For a separate SBI-console control, keep the diagnostic FIT and change only
`earlycon=uart8250,mmio32,0x18710000,115200` to `earlycon=sbi` in the same
bootargs string. Do not interpret failed SBI output with the baseline config
as a new firmware regression.

To inspect the **handoff** FDT rather than just the embedded one, on U-Boot
builds supporting bootm subcommands, use this sequence **instead of** the final
single `bootm` above (after fatload/iminfo):

```text
bootm start 0x41200000#conf-1
bootm loados
bootm prep
fdt addr
fdt print /chosen
fdt print /memory@40000000
fdt print /reserved-memory
bootm go
```

Check the `bootm prep` output reports the working FDT location. `fdt addr`
prints the current working tree, which must match the prep log; if not, use
`fdt addr <actual address from prep>` before printing. Record the address and
confirm `/chosen/bootargs` matches the temporary string. If subcommands or
addresses are unavailable, capture `help bootm`, `help fdt`, the complete
normal bootm log and label final-FDT inspection as **not verified**.

All environment changes are RAM-only: **never run saveenv**. Do not use nand,
mtd, ubi write/remove, erase, update, AiBurn, or a full-chip operation. This
procedure does not need a new SPL, U-Boot, OpenSBI or rootfs.

On a hang, wait long enough to capture any watchdog/reset, then reset or power
cycle. Remove microSD if necessary, interrupt U-Boot, and use the existing
factory normal boot path. Do not save test environment variables or erase
Falcon/Recovery. Recovery validation is a separate task; retain the factory
recovery image and existing recovery procedure.

If Linux 6.18 reaches a shell, collect:

```sh
uname -a
cat /proc/version
cat /proc/cmdline
cat /proc/device-tree/model
cat /proc/mtd
mount
ubinfo -a
dmesg
cat /proc/cpuinfo
```

Return FIT filename + full SHA256, manifest/project commit, cold/reset boot,
complete U-Boot and Linux serial log, bdinfo, temporary bootargs, hash-check
results, final DTB address/bootargs if inspected, last marker, hang/reset timing,
and shell commands. Redact unique identifiers/private host details before
publishing. Do not report a kernel banner alone as a successful rootfs boot.

## 中文实机操作摘要

M1 的原厂 5.10.44 + Buildroot UBIFS 已由操作者验证，M2 的 6.18 目前只到
`Starting kernel ...`。本轮镜像全部用于 **SD 加载到 RAM**，不是 AiBurn 烧录包。
不要覆盖 NAND Kernel、SPL、U-Boot、OpenSBI、RootFS、Falcon 或 Recovery。

1. 将 bundle 中三个独立命名的 `.itb` 复制到 SD 的现有 FAT 分区，校验 SHA256。
2. 串口设为 115200 8N1、无流控，从上电开始保存完整日志。
3. 先记录上面的 version/bdinfo/printenv，确认真实 U-Boot 重定位/堆栈/FDT
   没有与报告中的 Kernel 和 FIT 区间相交。静态 guard 不是实板测量结果。
4. 依次测试 baseline → offset → diagnostic；每轮复位，上面完整 U-Boot
   命令仅替换文件名。前两版内核内容完全一致，只比较加载和入口地址。
5. 默认用 MMIO earlycon；诊断版还可单独改为 earlycon=sbi 作控制实验。
   只临时 setenv，**不执行 saveenv，不烧写、不擦除 NAND**。
6. 保存 E0–E5 最后完整标记和所有残缺字符。E1 后无 E2，重点调查
   setup_vm/早期 SBI/页表切换；E4 后无 E5，重点调查 start_kernel、SBI 初始化
   和 earlycon 注册；有 E5 而无正常日志，重点调查控制台输出路径。
   没有 E0 不能直接认定内核入口未执行，也可能是 MMIO 权限或访问问题。
7. 卡住后复位/断电，必要时拔出 SD，走已验证的原厂正常启动路径。
   RAM 环境丢失后恢复原厂启动；不要为恢复实验擦除 Falcon 或 Recovery。
8. 出现 6.18 Shell 后执行上面的只读检查命令，先不要写文件或强制 remount rw。
9. 反馈镜像文件名、完整 SHA256、构建提交、完整串口日志、bdinfo、bootargs、
   最后标记和是否能进 Shell。没有实板日志前，不宣称 6.18 启动修复成功。
