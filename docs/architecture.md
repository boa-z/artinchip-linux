# Architecture

The repository is a standard Buildroot `BR2_EXTERNAL` tree. Upstream source is
fetched into an ignored cache; project configuration remains small and reviewable.

```text
sources.lock.json + configs/ + board/qemu/patches/
                  |
          standard Buildroot
                  |
       internal RISC-V toolchain
                  |
    OpenSBI + Linux + BusyBox + ext2 rootfs
                  |
       QEMU virt -> serial smoke test
                  |
       images + hashes + provenance
```

QEMU loads OpenSBI as M-mode firmware and the kernel as the next S-mode payload.
QEMU supplies the `virt` device tree. Virtio supplies the block device and network
interface. The kernel mounts the ext2 image, BusyBox init starts the system, and
the smoke test logs in through the serial console.

U-Boot is intentionally not in the M0 QEMU boot path: direct OpenSBI-to-Linux
boot matches the upstream Buildroot baseline and keeps the initial test small.
M1 adds an independent board pipeline for D213ECV-DEMO-V4-0. Buildroot manages
the pinned Bootlin external toolchain, BusyBox and UBIFS images. A source importer
exports the pinned existing Linux 6.18 reference and applies a small local patch
queue. A separate boot builder compiles selected vendor U-Boot/OpenSBI sources
with ordinary `make`, then the existing vendor container encoder creates AiBurn
updates. It never invokes the Luban SDK build system.

The first package targets only the rootfs volume to keep the factory Linux 5.10
test independent of a kernel replacement. The experimental second package adds a
Linux 6.18 FIT. Both retain the factory partition layout and exclude Recovery.
Host checks validate format, geometry, bounds and hashes; actual RAM handoff,
ROM loading, AiBurn behavior and NAND operation require physical evidence. See
[the M1 guide](m1-d213ecv.md) for the addresses, sources and validation boundaries.

## Extension boundaries

- `configs/`: separately reviewable board and experimental profiles.
- `board/artinchip/d211/` and `d213/`: future board configuration and DTS notes.
- `board/artinchip/d213ecv-demo128-nand/`: current physical-target policy, DTS,
  source provenance, NAND layout and reference-kernel compatibility patches.
- `patches/linux/`, `patches/uboot/`, `patches/opensbi/`: future upstream-bound
  patch queues. Empty queues are not enabled in M0 builds.
- `package/`: optional Buildroot packages when concrete requirements exist;
  `external.mk` already discovers standard package makefiles.
- `docs/`: decisions, measured validation and hardware research.

Do not add a vendor SDK environment, unmanaged binary toolchain or copied kernel
tree as an integration layer. Use upstream Kconfig, DTS bindings, standard driver
subsystems, the U-Boot driver model and generic OpenSBI interfaces wherever they
match the hardware. Keep board policy separate from SoC descriptions.
