#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "Usage: $0 LUBAN_CHECKOUT [FIRMWARE_OUTPUT]" >&2
    exit 2
fi
reference=$(realpath "$1")
if [ "$#" -eq 2 ]; then
    firmware=$(realpath -m "$2")
fi
cd "$(dirname "$0")/.."
firmware=${firmware:-"$PWD/artifacts/d213ecv-linux510-system-update"}
if compgen -G "$firmware/*.img" >/dev/null; then
    echo 'Use a fresh output directory for a new package' >&2
    exit 1
fi
python=$(command -v python3)
profile=d213ecv-demo128-nand-linux510
build="output/$profile"
components=.cache/vendor-boot/components
revision=$("$python" -c 'import json; print(json.load(open("board/artinchip/d213ecv-demo128-nand/vendor-sources.json"))["vendor_kernel"]["commit"])')
archive="linux-5.10.44-$revision.tar.gz"
read -r _ expected_hash _ < <(awk '$1 == "sha256" { print; exit }' board/artinchip/d213ecv-demo128-nand/linux510/linux/linux.hash)
mkdir -p .cache/vendor
if ! printf '%s  %s\n' "$expected_hash" ".cache/vendor/$archive" | sha256sum -c --status; then
    temporary=$(mktemp .cache/vendor/linux510.XXXXXXXX)
    trap 'rm -f "$temporary"' EXIT
    git -C "$reference" -c tar.umask=0002 archive --format=tar --mtime=2026-01-01T00:00:00Z \
        --prefix=linux-5.10.44/ "$revision:source/linux-5.10" | gzip -n -6 > "$temporary"
    printf '%s  %s\n' "$expected_hash" "$temporary" | sha256sum -c
    mv "$temporary" ".cache/vendor/$archive"
fi

./scripts/build.sh build "$profile"
./scripts/build.sh artifacts "$profile"
for option in ARCH_ARTINCHIP MACH_D211 MMU RISCV_SBI RISCV_SBI_V01 \
              SERIAL_8250_CONSOLE SERIAL_8250_ARTINCHIP SPI_ARTINCHIP \
              MTD_SPI_NAND MTD_UBI UBIFS_FS UBIFS_FS_ZLIB; do
    if ! grep -Fxq "CONFIG_$option=y" "artifacts/$profile/linux.config"; then
        echo "Required built-in CONFIG_$option=y missing" >&2
        exit 1
    fi
done
"$python" scripts/build-vendor-boot.py --reference "$reference" --host "$build/host"
export PATH="$PWD/$build/host/bin:$PATH"
work=$(mktemp -d .cache/vendor/linux510-fit.XXXXXXXX)
trap 'rm -rf "$work"' EXIT
"$python" scripts/make-kernel-fit.py --legacy-baseline \
    --kernel "$build/images/Image" --dtb "$components/u-boot.dtb" \
    --opensbi "$components/fw_dynamic.bin" --output "$work/kernel-5.10.44.itb"
"$python" scripts/firmware.py pack --system-update --vendor-linux510 \
    --components "$components" --kernel "$work/kernel-5.10.44.itb" \
    --rootfs "$build/images/rootfs.ubifs" --output "$firmware"
cp "$work"/* "$firmware/"
cp "artifacts/$profile/linux.config" "artifacts/$profile/buildroot.config" \
   "$components/u-boot.dtb" "$firmware/"
"$python" scripts/firmware.py verify --system-update "$firmware/d213ecv-linux510-system-update.img"
(
    cd "$firmware"
    find . -maxdepth 1 -type f ! -name 'SHA256SUMS*' -print0 | LC_ALL=C sort -z \
        | xargs -0 -r sha256sum -- > SHA256SUMS.new
    mv SHA256SUMS.new SHA256SUMS
)
