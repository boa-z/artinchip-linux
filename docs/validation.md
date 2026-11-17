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
| Linux 6.18 | Rebuild in progress after host OpenSSL and SPI API fixes |
| New rootfs mounted by original Linux 5.10 | Not verified; only static ABI/format checks passed |
| AiBurn recognition/flashing and physical Linux 6.18 boot | Not verified; no board serial log available |

The initial rootfs-only image SHA256 is
`691afe83820af1ce798dfc54b2c05c7c2eca910e4dea0db49897f80ea67ed757`.
This identifies that native package, not every subsequent build. Each package
carries its own SHA256SUMS, source/component provenance and hardware status.
The board CI workflow builds software evidence only; its result must be checked
independently of the native result. Hardware acceptance remains outstanding.
