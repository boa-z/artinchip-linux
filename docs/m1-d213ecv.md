# M1: D213ECV-DEMO-V4-0 NAND bring-up

The only physical validation target is **ArtInChip D213ECV-DEMO-V4-0**.
The vendor configuration name `d211_demo128_nand`, the vendor FIT/platform names
and existing `artinchip,d211` driver compatible strings are legacy interfaces.
They do not identify the physical target as D211.

## Validation states

Compilation, firmware packaging and hardware boot are separate results. M0's
native QEMU baseline and both QEMU CI profiles passed; see [validation.md](validation.md).

| Stage | Evidence/status |
| --- | --- |
| Standard Buildroot board rootfs | Built natively; UBIFS geometry/format/capacity checks passed |
| Vendor SPL/U-Boot/OpenSBI | Built directly from pinned source; no Luban build-system invocation |
| Rootfs-only AiBurn `.img` | Generated; FIT, environment layout, component CRC and SHA256 checks passed |
| Linux 6.18 reference integration | Separate profile; final compilation/CI results recorded in validation.md |
| New rootfs on the factory Linux 5.10 | Static ABI/filesystem contract checked; actual boot/mount unverified |
| AiBurn GUI recognition and physical flashing | Unverified |
| Physical Linux 6.18 boot | Unverified |

No board serial device or hardware boot log was available during initial
implementation. A software build or valid image container must not be reported as
successful hardware bring-up. Complete the Linux 5.10 rootfs-only board test before
trying the experimental kernel replacement.

## Independent builds

```sh
./scripts/host-deps.sh --check
./scripts/build.sh build d213ecv-demo128-nand
python3 scripts/firmware.py rootfs output/d213ecv-demo128-nand/images/rootfs.ubifs
./scripts/build.sh artifacts d213ecv-demo128-nand
```

This profile builds a small RV64 LP64D musl/BusyBox userspace using Buildroot's
hash-pinned Bootlin stable 2025.08-1 toolchain (GCC 14.3.0, Linux 5.4 headers).
It has no dependency on Luban, a vendor kernel or a pre-existing server toolchain.
The older headers avoid assuming kernel interfaces introduced after Linux 5.10.
The first generated rootfs was 4,698,112 bytes, UBIFS format 4, with zlib compression.
`/linuxrc` explicitly enters BusyBox init to preserve the factory `init=/linuxrc`
boot parameter. A 115200-baud `ttyS0` getty provides the development console.

The development image permits passwordless serial root login. It is a bring-up
image, not a production access-control configuration.

## Factory NAND layout

The layout is derived from the pinned vendor `target/d211/demo128_nand/image_cfg.json`.
Its normalized representation is checked in as `board/artinchip/d213ecv-demo128-nand/layout.json`.

| MTD | Partition | Offset | Size |
| --- | --- | --- | --- |
| 0 | spl | 0x0000000 | 1 MiB |
| 1 | uboot | 0x0100000 | 1 MiB |
| 2 | userid | 0x0200000 | 256 KiB |
| 3 | bbt | 0x0240000 | 256 KiB |
| 4 | env | 0x0280000 | 256 KiB |
| 5 | env_r | 0x02c0000 | 256 KiB |
| 6 | falcon | 0x0300000 | 256 KiB |
| 7 | logo | 0x0340000 | 768 KiB |
| 8 | kernel | 0x0400000 | 12 MiB |
| 9 | recovery | 0x1000000 | 16 MiB |
| 10 | ubiroot | 0x2000000 | 64 MiB |
| 11 | ubisystem | 0x6000000 | 32 MiB |

NAND geometry is 2 KiB minimum I/O, 128 KiB physical eraseblock, and 124 KiB
logical eraseblock (`0x1f000`, two 2 KiB UBI headers). UBIFS is limited to 480 LEBs,
leaving room in the 512-PEB root partition for UBI overhead and bad-block reserves.
Actual usable capacity depends on the flash's bad-block count. The `rootfs` UBI
volume uses ID 0 and autoresize; UBIFS growth is capped by its configured maximum.

AiBurn receives a raw `rootfs.ubifs` payload for the `ubiroot:rootfs` volume.
`rootfs.ubi` is an additional standard UBI container, not a whole-flash firmware
image. Do not substitute it for the UBIFS payload or write it to the entire NAND.

## Boot compatibility

The vendor U-Boot profile selects SPL and S-mode U-Boot. Important source values:

- SPL image load `0x42000000`, entry `0x42000100` after the AIC header.
- U-Boot text base `0x40004000`.
- Vendor OpenSBI firmware text base `0x47fe0000`, 128 KiB reserved near the top
  of the reference 128 MiB RAM layout.
- RAM updater assets: environment `0x41000000`, U-Boot FIT `0x41100000`, logo
  `0x42400000`, SPL container `0x40000000`, DDR initializer `0x00103000`.
- Kernel FIT staging `0x41200000`, kernel load/entry `0x40000000`, DTB
  destination `0x42200000` in the factory environment.
- NAND root parameters: `ubi.mtd=10 root=ubi0:rootfs rootfstype=ubifs` and
  `init=/linuxrc`; the factory environment supplies the complete `MTD` layout.

The factory kernel FIT includes Linux, a DTB and vendor `fw_dynamic.bin`.
The U-Boot FIT includes vendor OpenSBI, S-mode U-Boot and its DTB. These are
vendor handoff conventions; replacing OpenSBI or U-Boot with a current upstream
release has not been validated on this board. The M0 QEMU firmware is not a
substitute for this board firmware.

The vendor `falcon` partition stores a kernel/DT snapshot and the `boot_os`
environment variable controls the fast boot path. Kernel changes must be tested
through normal U-Boot before relying on that snapshot. Do not erase Recovery or
blindly overwrite Falcon to work around a boot failure. Record the current
`boot_os`, `boot_partition`, `MTD`, `UBI` and boot command before any board test.

The original environment disables runtime FIT verification (`verify=no`). New
kernel FITs contain SHA256 hashes that are verified by host packaging checks;
this milestone does not implement signed/secure boot or create signing keys.

## Source import and boot components

Use existing local references. Their paths are runtime arguments, never committed:

```sh
export LUBAN_REF=/path/to/existing/luban
export LINUX_REF=/path/to/existing/d211-linux-6.18
python3 scripts/import-kernel.py --source "$LINUX_REF"
python3 -m venv .cache/firmware-venv
.cache/firmware-venv/bin/pip install -r scripts/requirements-firmware.txt
.cache/firmware-venv/bin/python scripts/build-vendor-boot.py \
  --reference "$LUBAN_REF" --host output/d213ecv-demo128-nand/host
```

On Debian/Ubuntu, install `python3-venv` if needed. An existing `uv` installation
can create the same environment and install the same pinned requirements.
The source exporter reads committed Git objects, leaving reference checkouts
and their branches unchanged. Only the required boot subtrees, board resources
and binding headers are imported into the ignored cache. The source/build flow
does not invoke SDK `lunch`, `m`, or its Makefiles.

The direct U-Boot build imports clock/reset/display headers normally linked by
the SDK from Linux. Old OpenSBI requires explicit `zicsr`/`zifencei` ISA names with
modern binutils. This is an assembler compatibility setting for instructions
already used by the reference source, not a new hardware feature.

Source revisions, per-file licenses, original file hashes and local DTS changes
are recorded in `vendor-sources.json`. Imported boot sources remain in `.cache`.
U-Boot is GPL-2.0-or-later, OpenSBI uses its upstream BSD licensing, and the two
unmodified AIC packing helpers are Apache-2.0. The supplied PBP/DDR resources have
no per-file license statement; their provenance is recorded and no project MIT
relicensing is claimed. Review redistribution terms before a public binary release.

## Rootfs-only update package

```sh
export PATH="$PWD/output/d213ecv-demo128-nand/host/bin:$PATH"
.cache/firmware-venv/bin/python scripts/firmware.py pack \
  --components .cache/vendor-boot/components \
  --rootfs output/d213ecv-demo128-nand/images/rootfs.ubifs \
  --output artifacts/d213ecv-stock510-rootfs-update
python3 scripts/firmware.py verify \
  artifacts/d213ecv-stock510-rootfs-update/d213ecv-demo128-nand.img
(cd artifacts/d213ecv-stock510-rootfs-update && sha256sum -c SHA256SUMS)
```

Use a fresh output directory for each package. The wrapper verifies component
provenance hashes, redundant-environment CRC and partition layout, UBIFS geometry,
FIT references and available payload hashes, then invokes the existing AIC packer.
It rereads the resulting `.img` and checks every component's CRC and bounds.

The full factory partition map is retained, but the only flash target in this
package is `ubiroot:rootfs`. SPL, U-Boot, environment and logo updater entries are
RAM-download assets, not NAND write targets. Recovery, kernel, persistent env,
BBT, user data and bootloader partitions are excluded from the target list.
The verifier rejects protected-partition targets. This preserves Recovery at the
image protocol level; physical confirmation and correct AiBurn erase settings
remain part of the board test.

## Linux 6.18 integration

```sh
./scripts/build.sh build d213ecv-demo128-nand-linux618
./scripts/build.sh artifacts d213ecv-demo128-nand-linux618
python3 scripts/make-kernel-fit.py \
  --kernel output/d213ecv-demo128-nand-linux618/images/Image.gz \
  --dtb output/d213ecv-demo128-nand-linux618/images/d213ecv-demo128-nand.dtb \
  --opensbi .cache/vendor-boot/components/fw_dynamic.bin \
  --output artifacts/kernel-6.18.itb
.cache/firmware-venv/bin/python scripts/firmware.py pack \
  --components .cache/vendor-boot/components --kernel artifacts/kernel-6.18.itb \
  --rootfs output/d213ecv-demo128-nand-linux618/images/rootfs.ubifs \
  --output artifacts/d213ecv-linux618-update
```

The kernel is the pinned existing ArtInChip 6.18 reference. The board DTS retains
legacy driver compatibles, renames the physical model, updates DMA/pinctrl header
names, and preserves the vendor alternate pin encoding. DT compilation passes
with inherited warnings; this is not a mainline binding/schema pass. The kernel
fragment omits graphics, multimedia, sound and radio features unrelated to NAND
bring-up. Host OpenSSL is built by Buildroot for certificate tools.
An independent patch replaces two scalar `spi->chip_select` uses in the reference
SPI driver with `spi_get_chipselect(spi, 0)`, matching the Linux 6.18 API. The
unpatched reference fails compilation with the current toolchain; this fix has
not been verified against the physical SPI controller.

The FIT builder retains the factory addresses, includes SHA256 hashes and rejects
a kernel whose decompressed payload overlaps the factory FIT staging buffer or
whose runtime image would overlap the DTB destination. The image must fit the
12 MiB kernel partition. The experimental update writes `kernel` and
`ubiroot:rootfs`; Recovery remains excluded. Do not use it as evidence that the
factory fast-boot path or Linux 6.18 hardware drivers are verified.

## Board evidence and recovery

See [the Chinese operator guide](m1-d213ecv-zh.md) for AiBurn and serial steps.
Retain the factory recovery image and an independently recoverable boot route.
Collect logs from reset through SPL, OpenSBI, U-Boot, Linux and a working shell.
Record board revision, NAND identification, `/proc/mtd`, root mount, `uname`,
temporary I/O and persistence over a reboot. Keep Linux 5.10 and 6.18 test records
separate. Redact credentials and private host details before committing logs.

CI builds both rootfs stages, boot components, FITs and update containers, and
uploads software evidence. CI cannot validate the physical board, AiBurn's UI,
electrical connections or NAND bad-block behavior.
