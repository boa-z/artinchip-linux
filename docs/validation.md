# M0 validation

Implementation is in progress. Results must be updated from actual native build,
QEMU boot and GitHub Actions runs; the presence of a profile is not a passing test.

| Check | Status |
| --- | --- |
| GitHub authenticated identity | Confirmed `boa-z` |
| Buildroot 2026.08.1 source and tag | Archive fetched, SHA256 recorded, tag commit resolved |
| Native host dependencies | Available; Buildroot dependency check passed |
| Baseline build and QEMU smoke | In progress |
| Linux 7.3.5 source | Official archive available, published SHA256 recorded |
| Linux 7.3.5 build and QEMU smoke | Pending |
| GitHub Actions | Pending first push |

No hardware boot, D211/D213 device driver validation, U-Boot boot chain or
bit-for-bit reproducibility claim is made by M0.
