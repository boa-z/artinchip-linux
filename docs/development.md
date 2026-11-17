# Development guide

## Native host

The initial development host uses Debian 13 on x86-64. The implementation also
targets Ubuntu 24.04 in CI. Buildroot's own dependency check is authoritative.
The helper checks the native tools and supports installing their Debian/Ubuntu
packages without performing a system upgrade. Root is only needed for installing
packages. Authentication is handled interactively by sudo, never stored by the
project. Python 3.11+ is required by the orchestration scripts.

Buildroot builds its own host flex, bison and other required package tools; the
minimal QEMU profile does not require system flex/bison or OpenSSL development
headers. Add host dependencies only when a concrete package requires them.

## Build commands

Run `./scripts/build.sh COMMAND [PROFILE]` from any working directory. Profiles
are `baseline` (default) and `linux-7.3.5`.

| Command | Effect |
| --- | --- |
| `fetch` | Download, verify and extract the pinned Buildroot source |
| `configure` | Apply the profile defconfig; overwrites local configuration edits |
| `build` | Configure if necessary and build incrementally |
| `test` | Boot and assert guest behavior, then require clean poweroff |
| `run` | Start an interactive serial session; use guest `poweroff` to exit |
| `artifacts` | Collect images, configs, logs, manifest and SHA256 sums |
| `clean` | Run Buildroot clean for that profile, keeping its config |
| `distclean` | Remove only that profile's complete output directory |

Shared `.cache/dl/` retains upstream source archives. `.cache/buildroot-*` holds
the verified source extraction. Output trees are deliberately separate for the
two kernels; do not copy toolchains or package stamp files between profiles.
Switching toolchain, libc or architecture requires a clean rebuild. A kernel-only
investigation can use upstream Buildroot's `linux-dirclean` target, but the
checked-in profiles must remain independently buildable from empty output.

`BR2_JLEVEL` controls package-internal parallelism. Top-level Buildroot package
parallelism is not enabled. The default reserves roughly 1.5 GiB available memory
per compiler job, with a maximum of eight. `JOBS=1` is suitable when other work
uses the host's RAM. Do not kill unrelated host services to make builds fit.

## Provenance and reproducibility

`sources.lock.json` pins Buildroot's release tag commit and the official source
archive SHA256. The archive hash is the executable fetch constraint; the commit
records the corresponding upstream tag. Buildroot's hash checks are forced for
all downloaded packages. Custom Linux/OpenSBI hashes are under `board/qemu/patches`.
The kernel 7.3.5 hash comes from kernel.org's published checksum list.

`BR2_REPRODUCIBLE=y`, UTC, the C locale and a fixed source epoch remove common
timestamp variation. A reproducible configuration and traceable images do not
prove bit-identical results across different host compilers. Compare two clean
builds in a controlled host environment before making a bit-reproducibility claim.

The artifact manifest records the project commit, dirty-worktree state, source
lock, selected versions, all built package directories, QEMU version and file
hashes. After modifying sources, rebuild and re-run smoke tests before exporting
artifacts. Artifacts are evidence for that exact build, not a firmware release.

## Smoke test contract

The test launches the built `fw_jump.bin`, `Image` and `rootfs.ext2` with QEMU
`virt`, two virtual CPUs and 512 MiB guest RAM. It checks the OpenSBI banner,
serial root login, shell execution, exact kernel release, `riscv64` architecture,
BusyBox availability, root mount, temporary-file I/O and clean poweroff.
Output markers are assembled inside the guest, preventing serial command echo
from satisfying the assertions. A timeout, early QEMU exit, failed assertion or
missing image fails the command. Guest networking uses QEMU user networking;
there are no forwarded host ports and no external network dependency in the test.

Raw local build logs may include local paths. Review logs before sharing them.
Never add private proxy settings, SDK paths or authentication material to a profile.
