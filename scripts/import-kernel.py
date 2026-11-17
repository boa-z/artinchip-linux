#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Export a pinned local kernel Git snapshot without using the Luban build system."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
PIN = json.loads((ROOT / 'board/artinchip/d213ecv-demo128-nand/vendor-sources.json').read_text())['kernel_reference']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Existing d211-linux-6.18 Git checkout')
    args = parser.parse_args()
    commit = PIN['commit']
    actual = subprocess.check_output(['git', '-C', str(args.source), 'rev-parse', commit + '^{commit}'], text=True).strip()
    if actual != commit:
        sys.exit('Pinned kernel commit is not available')
    dest = ROOT / '.cache/vendor' / ('linux-' + commit + '.tar.gz')
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix('.part')
    # git archive reads committed objects, not modifications in the reference worktree.
    proc = subprocess.Popen(['git', '-C', str(args.source), 'archive', '--format=tar',
                             '--prefix=linux-' + commit + '/', commit], stdout=subprocess.PIPE)
    with tmp.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as out:
        shutil.copyfileobj(proc.stdout, out)
    proc.stdout.close()
    if proc.wait():
        tmp.unlink()
        sys.exit('git archive failed')
    with tmp.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    hashfile = ROOT / 'board/artinchip/d213ecv-demo128-nand/hashes/linux/linux.hash'
    if hashfile.exists():
        expected = hashfile.read_text().splitlines()[-1].split()[1]
        if checksum != expected:
            tmp.unlink()
            sys.exit('Export differs from pinned source hash; no archive was installed')
    else:
        print('Initial source SHA256:', checksum)
    tmp.replace(dest)
    print('Imported pinned kernel into .cache/vendor/')


if __name__ == '__main__':
    main()
