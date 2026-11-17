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
Hardware bring-up will evaluate U-Boot SPL, DDR initialization and the appropriate
OpenSBI payload mode. Firmware placement, ROM image format and boot media remain
hardware questions; successful QEMU boot does not validate any of them.

## Extension boundaries

- `configs/`: separately reviewable board and experimental profiles.
- `board/artinchip/d211/` and `d213/`: future board configuration and DTS notes.
- `patches/linux/`, `patches/uboot/`, `patches/opensbi/`: future upstream-bound
  patch queues. Empty queues are not enabled in M0 builds.
- `package/`: optional Buildroot packages when concrete requirements exist;
  `external.mk` already discovers standard package makefiles.
- `docs/`: decisions, measured validation and hardware research.

Do not add a vendor SDK environment, binary prebuilt toolchain or copied kernel
tree as an integration layer. Use upstream Kconfig, DTS bindings, standard driver
subsystems, the U-Boot driver model and generic OpenSBI interfaces wherever they
match the hardware. Keep board policy separate from SoC descriptions.
