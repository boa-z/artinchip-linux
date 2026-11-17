# Contributing

Use English for documentation, commit messages and upstream submissions. Keep
patches small and describe the problem, observable behavior and actual validation.
Use `Signed-off-by` for upstream submissions only when you can certify the
Developer Certificate of Origin: <https://developercertificate.org/>.

For platform changes, run host checks, build the affected profile, execute its
QEMU smoke test and inspect the collected manifest. Keep a passing baseline when
investigating another kernel. Report failures without treating experiments as
verified support. CI runs both profiles independently and preserves failure logs.

Before pushing, inspect `git diff --check`, the complete staged diff and the file
list. Never commit build trees, SDK sources, credentials or private host settings.
Commit and push verified increments to the authorized development branch. Do not
rewrite remote history to conceal a mistake. Follow the repository owner's branch
policy; do not create PRs or merge branches without authorization.

## Upstream patches

Research the current upstream implementation before reusing vendor code. Identify
the correct subsystem and maintainers using the upstream `MAINTAINERS` file and
`scripts/get_maintainer.pl`. Read Linux `Documentation/process/submitting-patches.rst`,
`Documentation/process/coding-style.rst` and the applicable subsystem guidance.
Use `scripts/checkpatch.pl`, compile checks, binding validation (`dt_binding_check`)
and board DT validation (`dtbs_check`) as appropriate. Passing QEMU is insufficient
evidence for a physical SoC driver.

Each future patch queue must identify its exact upstream base, origin, license,
maintainers, hardware dependencies, review/submission status and tests. Separate
bindings, SoC description, reusable drivers and board enablement into reviewable
changes. Add standard compatible strings and schemas; avoid vendor ABI shortcuts
when a documented standard subsystem interface fits the hardware.

For Buildroot, follow its package conventions and `utils/check-package`; for
U-Boot, use current driver model, Kconfig and device-tree conventions; for OpenSBI,
prefer generic platform and FDT drivers over a private SoC platform fork.

Third-party code retains its own license and attribution. The owner's permission
to choose this project's license does not change third-party licensing.
