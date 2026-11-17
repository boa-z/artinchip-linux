# M0 validation

Implementation is in progress. Results must be updated from actual native build,
QEMU boot and GitHub Actions runs; the presence of a profile is not a passing test.

| Check | Status |
| --- | --- |
| GitHub authenticated identity | Confirmed `boa-z` |
| Buildroot 2026.08.1 source and tag | Archive fetched, SHA256 recorded, tag commit resolved |
| Native host dependencies | Available; Buildroot dependency check passed |
| Baseline build and QEMU smoke | Rebuilding after header hash correction |
| Linux 7.3.5 source | Official archive available, published SHA256 recorded |
| Linux 7.3.5 build and QEMU smoke | Pending |
| GitHub Actions | Both profiles started; final results pending |

The first native build stopped at Linux header download verification because the
external tree lacked `linux-headers/linux-headers.hash`. This is now included,
and the retried build successfully installed the 6.18.7 headers. Both profiles
explicitly select 6.18.7 userspace headers independently of the kernel version.

No hardware boot, D211/D213 device driver validation, U-Boot boot chain or
bit-for-bit reproducibility claim is made by M0.
