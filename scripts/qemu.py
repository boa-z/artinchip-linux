#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Boot the built OpenSBI/kernel/rootfs and test a real serial login."""
import argparse
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent


def command(images):
    executable = shutil.which('qemu-system-riscv64')
    if not executable:
        raise RuntimeError('Install qemu-system-riscv64 (Debian: qemu-system-misc)')
    for name in ('fw_jump.bin', 'Image', 'rootfs.ext2'):
        if not (images / name).is_file():
            raise RuntimeError(f'Missing {name}; build this profile first')
    return [executable, '-machine', 'virt', '-m', '512M', '-smp', '2',
            '-bios', str(images / 'fw_jump.bin'), '-kernel', str(images / 'Image'),
            '-append', 'console=ttyS0 rootwait root=/dev/vda ro panic=1',
            '-drive', f'file={images / "rootfs.ext2"},format=raw,if=none,id=rootfs',
            '-device', 'virtio-blk-device,drive=rootfs', '-snapshot',
            '-netdev', 'user,id=net0', '-device', 'virtio-net-device,netdev=net0',
            '-display', 'none', '-serial', 'stdio', '-monitor', 'none', '-no-reboot']


def smoke(cmd, output, expected, timeout):
    started = time.monotonic()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    transcript = ''
    logged_in = False
    sent_test = False
    passed = False
    error = 'Timed out waiting for QEMU smoke test'
    # printf assembles result markers so echoed input cannot satisfy the check.
    script = (
        "printf '\\nM0_%s\\n' SHELL; uname -a; "
        f"if test \"$(uname -m)\" = riscv64 && test \"$(uname -r)\" = '{expected}' "
        "&& test \"$(id -u)\" = 0 && test -x /bin/busybox "
        "&& grep -q ' / ' /proc/mounts "
        "&& printf 'rootfs-ok' > /tmp/m0-check && test \"$(cat /tmp/m0-check)\" = rootfs-ok; "
        "then printf '\\nM0_%s\\n' PASS; else printf '\\nM0_%s\\n' FAIL; fi; poweroff\n"
    )
    try:
        with (output / 'smoke.log').open('w') as log:
            while time.monotonic() - started < timeout:
                for key, _ in selector.select(timeout=1):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    text = data.decode(errors='replace')
                    sys.stdout.write(text)
                    sys.stdout.flush()
                    log.write(text)
                    log.flush()
                    transcript += text
                if not logged_in and re.search(r'login:\s*$', transcript):
                    proc.stdin.write(b'root\n')
                    proc.stdin.flush()
                    logged_in = True
                if logged_in and not sent_test and re.search(r'[#]\s*$', transcript):
                    proc.stdin.write(script.encode())
                    proc.stdin.flush()
                    sent_test = True
                if re.search(r'(?m)^M0_FAIL\r?$', transcript):
                    error = 'Guest checks failed'
                    break
                if re.search(r'(?m)^M0_PASS\r?$', transcript):
                    passed = True
                if proc.poll() is not None:
                    if not passed:
                        error = f'QEMU exited before PASS (status {proc.returncode})'
                    break
            else:
                passed = False
            passed = (passed and proc.poll() == 0 and 'OpenSBI' in transcript
                      and re.search(r'(?m)^M0_SHELL\r?$', transcript) is not None)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        selector.close()
        proc.stdin.close()
        proc.stdout.close()
    result = {'passed': passed, 'expected_kernel': expected,
              'duration_seconds': round(time.monotonic() - started, 2),
              'checks': ['OpenSBI banner', 'serial root login', 'shell', 'uname release',
                         'riscv64 architecture', 'BusyBox', 'root mount', 'tmp file I/O', 'poweroff']}
    if not passed:
        result['error'] = error
    (output / 'smoke-result.json').write_text(json.dumps(result, indent=2) + '\n')
    if not passed:
        raise RuntimeError(error + '; see smoke.log')
    print('\nQEMU smoke test PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('run', 'test'))
    parser.add_argument('profile', choices=('baseline', 'linux-7.3.5'))
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--images', type=Path, help='Explicit artifact directory instead of output images')
    args = parser.parse_args()
    output = ROOT / 'output' / args.profile
    cmd = command((args.images.resolve() if args.images else output / 'images'))
    if args.mode == 'run':
        os.execvp(cmd[0], cmd)
    lock = json.loads((ROOT / 'sources.lock.json').read_text())
    output.mkdir(parents=True, exist_ok=True)
    expected = lock['baseline_kernel' if args.profile == 'baseline' else 'experimental_kernel']
    smoke(cmd, output, expected, args.timeout)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError) as exc:
        sys.exit(str(exc))
