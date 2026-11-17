#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
mode=${1:---check}
case "$mode" in
    --check) ;;
    --install)
        . /etc/os-release
        case "$ID" in
            debian|ubuntu)
                sudo apt-get update
                sudo apt-get install --no-install-recommends -y \
                    build-essential bash bc binutils bzip2 ca-certificates cpio curl \
                    file findutils gawk git gzip libncurses-dev patch perl python3 \
                    qemu-system-misc rsync sed tar unzip wget which xz-utils
                ;;
            *) echo "See docs/development.md for dependencies on $ID" >&2; exit 1 ;;
        esac
        ;;
    *) echo "Usage: $0 [--check|--install]" >&2; exit 2 ;;
esac
missing=0
for tool in gcc g++ make bash bc bzip2 cpio curl file find awk git gzip patch perl \
            python3 qemu-system-riscv64 rsync sed tar unzip wget which xz; do
    if ! command -v "$tool" >/dev/null; then
        echo "Missing: $tool" >&2
        missing=1
    fi
done
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python >= 3.11 required"'
if [ "$missing" -ne 0 ]; then exit 1; fi
echo "Host tools available. Buildroot performs its full dependency check during build."
