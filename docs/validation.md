# M0 validation

M0 baseline evidence was collected on 2026-11-17. Hardware bring-up has separate
acceptance criteria; these QEMU results do not establish board support.

| Check | Status |
| --- | --- |
| GitHub authenticated identity | Confirmed `boa-z` |
| Buildroot 2026.08.1 source and tag | Archive fetched, SHA256 recorded, tag commit resolved |
| Native host dependencies | Available; Buildroot dependency check passed |
| Baseline build and QEMU smoke | Native build passed; serial smoke passed in 9.98 seconds |
| Linux 7.3.5 source | Official archive available, published SHA256 recorded |
| Linux 7.3.5 build and QEMU smoke | Passed in GitHub Actions |
| GitHub Actions | Both profiles passed, including artifact upload |

Verified CI: [run 44123924925](https://github.com/boa-z/artinchip-linux/actions/runs/44123924925),
project commit `8fef748`. Both matrix jobs completed successfully. The native
baseline was also replayed from its collected artifacts after cleaning the build
tree; that test passed in 7.94 seconds. Local artifacts retain the actual source
manifest and configuration state, including the dirty-worktree indicator where
development was ongoing during collection.

The first native build stopped at Linux header download verification because the
external tree lacked `linux-headers/linux-headers.hash`. This is now included,
and the retried build successfully installed the 6.18.7 headers. Both profiles
explicitly select 6.18.7 userspace headers independently of the kernel version.

The initial CI run `44120112434` failed; it is retained in history. The corrected
run above is the passing evidence. Linux 7.3.5 was built in CI rather than
duplicating its complete toolchain build on the native server.

No physical-board boot, device driver validation, U-Boot hardware boot chain or
bit-for-bit reproducibility claim is made by M0.

# M1 software validation (hardware pending)

The physical target is D213ECV-DEMO-V4-0; `d211_demo128_nand` is only the
vendor profile name. The native M0 artifact replay passed again during M1.

| Check | Native result |
| --- | --- |
| Independent board rootfs | Build passed; 4,698,112-byte UBIFS, format 4, zlib |
| Rootfs geometry/capacity | 2 KiB I/O, 124 KiB LEB, maximum 480 LEBs; passed |
| Vendor SPL, U-Boot and OpenSBI | Direct builds passed outside the Luban build system |
| Rootfs-only AiBurn container | Generated; environment/FIT/component CRC/capacity checks passed |
| Partition and malformed-image tests | 11 passed |
| Buildroot external configuration/patch checks | Passed without warnings |
| Linux 6.18.52 | Complete profile build passed after host OpenSSL and SPI API fixes |
| Experimental Linux 6.18 FIT/update container | SHA256 payload hashes, address/partition bounds and component CRC checks passed |
| New rootfs mounted by original Linux 5.10 | Not verified; only static ABI/format checks passed |
| AiBurn recognition/flashing and physical Linux 6.18 boot | Not verified; no board serial log available |

The initial rootfs-only image SHA256 is
`691afe83820af1ce798dfc54b2c05c7c2eca910e4dea0db49897f80ea67ed757`.
This identifies that native package, not every subsequent build. Each package
carries its own SHA256SUMS, source/component provenance and hardware status.
The board CI workflow builds software evidence only; its result must be checked
independently of the native result. Hardware acceptance remains outstanding.

The native Linux 6.18.52 `Image.gz` is 5,734,204 bytes; the decompressed Image is
10,913,280 bytes and its RISC-V runtime image size is 11,227,136 bytes. The FIT is
5,908,753 bytes, below the 12 MiB kernel partition. The matching UBIFS is
4,825,088 bytes. The experimental update targets exactly `kernel` and
`ubiroot:rootfs`, and its SHA256 is
`fede0e17412d637fd4682114b1070315e23183866a26beb59f2eba1f899dbe49`.

The kernel source's release is 6.18.52 at the pinned reference commit. Initial
native attempts failed on missing host OpenSSL headers and the legacy scalar
SPI chip-select API. Buildroot now supplies host OpenSSL and applies the separate
SPI accessor patch. The successful rebuild started from a fresh kernel extraction,
so it exercised the committed patch application path. Inherited DTS warnings and
vendor-driver warnings remain; no DT schema, hardware-driver or boot pass is implied.

## Clean-runner M1 evidence

[D213ECV software run 44146580354](https://github.com/boa-z/artinchip-linux/actions/runs/44146580354)
passed at project commit `5813a00bfb069dc72f331a4a57b6e718b8643073`. Both board
profiles, direct boot-component builds, FIT checks, rootfs-only packaging,
experimental kernel/rootfs packaging and artifact upload succeeded. The uploaded
artifact was downloaded again: all four checksum sets passed, and both firmware
containers passed the independent CRC/bounds/protected-target verifier.

[Download the software artifact](https://github.com/boa-z/artinchip-linux/actions/runs/44146580354/artifacts/14359131839)
within its 14-day retention window. These are the **CI package** SHA256 values:

| Package directory | `.img` SHA256 |
| --- | --- |
| `d213ecv-stock510-rootfs-update` | `530655e7dcbc04490a536dd16e2b5bb0d0dadebba1546525570bb479bd0ec4e6` |
| `d213ecv-linux618-update` | `6bcd2d237399b90054efc53479ae776f3813330acd6bd4bfbc14a229a7c71a81` |

CI and native images are not byte-identical. All six boot assets and the board
DTB matched between them. Differences include random UBIFS UUIDs, a toolchain
GDB helper containing its build-prefix path, and `os-release` version metadata
from different project build states. The embedded kernel config also records
Rust compiler detection on the runner even though this profile does not enable
Rust kernel code. Bit-for-bit reproducibility is **not established**; pinning
sources and recording per-build hashes must not be described as that stronger
claim. Further reproducibility work should isolate Buildroot version detection
from the enclosing project Git repository, normalize optional host-tool detection
and remove irrelevant target debugger paths before evaluating deterministic
filesystem image generation.

Native builds used development intermediates. Their manifest `project_commit`
and `working_tree_dirty` fields describe the later collection/packaging step,
not an attestation that every intermediate was rebuilt at that commit. The
clean-runner artifact above is the authoritative commit-associated software
validation evidence. Neither set of artifacts establishes factory Linux 5.10
mount compatibility, AiBurn flashing success or physical Linux 6.18 boot.

## Latest M0 regression

[QEMU run 44146580357](https://github.com/boa-z/artinchip-linux/actions/runs/44146580357)
tests the same software commit `5813a00`. Its baseline job passed compilation,
Linux 6.18.7 boot/shell smoke, artifact collection and upload. The serial log
contains `QEMU smoke test PASS` and identifies Linux 6.18.7.

As of 2026-11-17 19:21 UTC, the Linux 7.3.5 matrix job is still in its
build step. Its current result and the overall workflow result are **pending**,
not passed. The earlier Linux 7.3.5 success in run `44123924925` remains valid
historical evidence, but it does not establish this latest run's outcome. The
separate M1 board workflow above is complete and successful.

# M2 SD/RAM early boot investigation

The operator subsequently reported physical M1 success with vendor Linux
5.10.44 + the independent Buildroot rootfs: NAND/UBI/UBIFS, BusyBox, file I/O
and reboot persistence passed. This updates the earlier hardware-pending
statements above for that combination only. Linux 6.18.52 still has no observed
Linux output after U-Boot `Starting kernel ...`. The operator's FIT hash checks
and loading/decompression success establish handoff progress, not a Linux boot.

Native M2 software verification on 2026-11-18:

- A separate diagnostic kernel built from the SHA-checked pinned archive with
  versioned patches using six compiler jobs. Only D213ECV_EARLY_DEBUG and
  RISCV_SBI_V01 differ from the M1 final config. Normal M1 kernel, DTB and
  rootfs outputs were not overwritten. Inherited vendor driver/DTS warnings
  remain; this is not a DT schema or runtime-driver validation pass.
- 22 tests passed, none skipped, including real FIT payload corruption for
  Kernel/OpenSBI/DTB, mutated load/entry, built-in UART requirements, DTB
  checks, runtime-overlap rejection and emitted E0 register/stack checks.
- Manual linked-head disassembly confirmed physical UART access before MMU
  and m2_uart_va loads after relocation, and marker placement around setup_vm,
  relocate_enable_mmu, soc_early_init and start_kernel.
- Python compile checks, shell syntax and git whitespace checks passed.
- Both M1 rootfs-only and legacy kernel+rootfs AiBurn packaging passed again
  using existing native Buildroot outputs. These were software regression
  packages, not instructions to flash NAND for M2.
- M0 baseline artifact replay again produced `QEMU smoke test PASS`.
- All generated RAM bundle SHA256SUMS entries verified. The baseline FIT is
  byte-identical to the retained original `artifacts/kernel-6.18.itb`.
  Baseline/offset use identical compressed kernel, final config and DTB.

| RAM debug FIT | SHA256 |
| --- | --- |
| baseline-40000000.itb | `2f4a5eee7ca058b29cf59cafa808ec1e982660f0a8e478e885ed9731de87463c` |
| offset-40200000.itb | `c7a788db0dd8b6cfd2ea88e0fe7b7e4632e2c19a418b54bf60100531aa960222` |
| diagnostic-40200000.itb | `6cc840a00b76d5a00e5352359bc359d310b291d636b6ade275688252c07daebc` |

The baseline Image has text_offset=0x200000, image_size=11227136 and file
size=10913280. At candidate 0x40200000 its runtime extent is
[0x40200000,0x40cb5000), below the actual FIT buffer
[0x41200000,0x417a2911). DDR is [0x40000000,0x48000000).
Both addresses satisfy RV64 PMD alignment; the offset is not established as
the hardware failure cause. A confirmed console configuration defect is the
loss of the vendor 5.10 SBI v0.1 default in 6.18, preventing earlycon=sbi with
OpenSBI 0.9. The optional diagnostic configuration enables that fallback.
MMIO silence and the exact early failure instruction still require hardware.

Local bundles record the pre-M2 HEAD plus working_tree_dirty=true and actual
source/config/ELF/input hashes, rather than falsely claiming a clean build at
a later commit. Existing baseline intermediates are identified by content
hash; they were intentionally reused. The workflow now builds all three RAM
variants and runs the same checks on a clean runner, alongside the M1 packages.

**M2 CI has not run:** startup `gh auth status` reported invalid existing boa-z
credentials and `gh api user` returned HTTP 401. No GitHub write was attempted;
no account was switched or new credential created. Local validation cannot be
reported as GitHub Actions success. Restore the existing boa-z authentication,
verify the identity, then push the authorized main commit and inspect the
actual workflow result. Earlier M0/M1 CI evidence above remains historical.

See [the bilingual M2 operator guide](m2-early-boot-debug.md). Next hardware
tests must use microSD fatload + bootm into RAM, without saveenv or NAND writes.

# Single-file experimental system installer

The board workflow for M2 commit `725f95feb383aab1ec7f243a5fd6131fe979b066`
subsequently completed successfully:
https://github.com/boa-z/artinchip-linux/actions/runs/44300874852.
This supersedes the initial authentication/CI blocker above for that commit.
It remains software evidence, not Linux 6.18 hardware boot evidence.

At the operator's subsequent request for one flashable image, an explicit
`firmware.py pack --system-update` mode was added. It includes persistent
SPL/U-Boot (with vendor OpenSBI 0.9)/env+env_r/logo/kernel/rootfs targets while
preserving Recovery, BBT, userid, Falcon bytes and ubisystem:user. It uses the
M2 0x40200000 diagnostic kernel, not the old 0x40000000 control. The new boot
environment selects normal U-Boot, omits falcon_save and enables console logs.
There is still no physical verification of these rebuilt boot components or
of the replacement Linux 6.18 kernel. Do not call it a validated bootable release.

Native software results: 26 tests passed with no skips; real full-system
packaging and explicit system verification passed; all artifact SHA256SUMS
verified; selective rootfs-only and kernel+rootfs packaging regressions passed.
The system verifier rejects protected partitions even in its expanded mode,
requires the full target set and exact redundant environment mapping, and the
packer rejects differing OpenSBI payloads between kernel FIT and boot manifest.
The workflow now additionally reproduces this system package; its result must
be checked separately from the already-passing M2 workflow above.

The local `.img` is under `artifacts/d213ecv-linux618-system-update/`, alongside
its source/component/environment manifest, SHA256SUMS and standalone guide.
[System update and OpenSBI upgrade analysis](system-update.md) describes the
write scope, experimental hardware status and the reviewed upstream v1.9
compatibility gaps. It is intended for an existing factory-layout board with
Recovery present, not a full-chip erase/blank-NAND Recovery reconstruction.
