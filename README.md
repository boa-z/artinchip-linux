# artinchip-linux

An independent, upstream-oriented embedded Linux platform for future ArtInChip
D211/D213 support. Standard Buildroot, Linux, OpenSBI and eventually U-Boot are
the integration boundaries. M1 imports pinned reference boot/kernel sources,
but never invokes or requires the complete Luban build system.

The current and only physical validation target is **D213ECV-DEMO-V4-0**.
M1 board build, firmware packaging, validation boundaries and operator instructions
are documented in [the hardware bring-up guide](docs/m1-d213ecv.md).

M0 provides a verified RISC-V 64-bit QEMU development baseline. M1 adds independent
board rootfs/kernel profiles and recovery-preserving AiBurn packaging. Physical
board Linux 5.10.44 with the independent rootfs has passed operator-reported
hardware tests. Linux 6.18 currently stops after U-Boot handoff; use the
[SD/RAM early-boot debug guide](docs/m2-early-boot-debug.md) for controlled
address comparisons and optional UART stage markers. Multimedia,
DRM/KMS and OTA remain outside the current bring-up work.

## Quick start

Use native Linux as an ordinary user, Python 3.11 or newer, at least 8 GiB RAM
(16 GiB recommended) and at least 15 GiB free disk per complete build profile.
On Debian/Ubuntu:

```sh
./scripts/host-deps.sh --check
# If dependencies are missing; sudo is used only for package installation:
./scripts/host-deps.sh --install
./scripts/build.sh configure baseline
./scripts/build.sh build baseline
./scripts/build.sh test baseline
./scripts/build.sh artifacts baseline
```

The script chooses up to eight compiler jobs based on available RAM. `JOBS=4`
overrides that choice; values above eight are rejected. Do not build with sudo.
If a network proxy is required, configure standard proxy environment variables
locally. Never commit proxy credentials or host-specific settings.

The baseline follows Buildroot's `qemu_riscv64_virt_defconfig`: Linux 6.18.7,
OpenSBI 1.6, the internal RISC-V toolchain, BusyBox and an ext2 root filesystem.
The system QEMU is used instead of building another host QEMU. The full pinned
Buildroot version, commit and source archive SHA256 are in
[sources.lock.json](sources.lock.json). Package versions and hashes come from
that Buildroot release and the checked-in board hash files.

## Kernel experiment

```sh
./scripts/build.sh build linux-7.3.5
./scripts/build.sh test linux-7.3.5
./scripts/build.sh artifacts linux-7.3.5
```

The experiment has an independent output directory. The baseline remains
available for comparison. Both profiles retain 6.18 userspace headers; upgrading
the kernel does not require upgrading the userspace ABI baseline. Neither
profile is considered verified until its actual build and boot checks pass.
See [validation](docs/validation.md) for recorded evidence and limitations.

A single-file experimental board system installer is documented in
[System update and OpenSBI status](docs/system-update.md). It installs the normal
boot components and Linux/rootfs while preserving the existing Recovery and device
data. Linux 6.18 physical boot remains unverified.

## Outputs and automation

Build trees and serial logs live in `output/<profile>/`; collected firmware,
kernel, rootfs, configurations, package provenance and SHA256 sums live in
`artifacts/<profile>/`. Both are ignored by Git. QEMU uses snapshot mode so boot
tests do not mutate the rootfs image. The development image allows a serial
root login without a password and is intended for isolated QEMU development.

GitHub Actions builds and boots both profiles, with read-only repository
permissions and commit-pinned actions. It uploads evidence even after failures.
The workflow is [here](.github/workflows/build.yml).

- [Development guide](docs/development.md)
- [Architecture and extension points](docs/architecture.md)
- [Hardware research and upstream strategy](docs/research.md)
- [Contribution guide](CONTRIBUTING.md)

## License

Original platform scripts and documentation are MIT licensed; see [LICENSE](LICENSE).
Upstream Buildroot-derived configuration and hash files retain GPL-2.0-or-later
licensing. Downloaded Linux, OpenSBI, BusyBox and toolchain components keep their
own licenses. See [NOTICE](NOTICE) and use Buildroot `legal-info` before distributing
binary images. This repository's license does not relicense third-party code.
