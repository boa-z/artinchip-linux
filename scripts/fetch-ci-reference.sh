#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Cold CI checkouts only. Native developers should use existing references.
set -euo pipefail
if [ "$#" -lt 3 ]; then
    echo "Usage: $0 URL COMMIT DESTINATION [SPARSE_PATH ...]" >&2
    exit 2
fi
url=$1
revision=$2
destination=$3
shift 3
if [ -e "$destination" ]; then
    echo "Reference destination already exists; refusing to replace it" >&2
    exit 1
fi
git init --initial-branch=source-import "$destination"
git -C "$destination" remote add origin "$url"
git -C "$destination" fetch --depth=1 --filter=blob:none origin "$revision"
if [ "$#" -gt 0 ]; then
    git -C "$destination" sparse-checkout init --cone
    git -C "$destination" sparse-checkout set "$@"
fi
git -C "$destination" checkout --detach "$revision"
test "$(git -C "$destination" rev-parse HEAD)" = "$revision"
