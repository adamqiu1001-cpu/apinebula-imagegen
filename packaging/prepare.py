"""Fetch pinned runtimes/wheels; use only on the native packaging platform."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from urllib.request import urlopen
import time

from build_packages import ROOT, DOWNLOADS, check_build_host

TARGETS = {
    'macos': [('macos-arm64', 'aarch64-apple-darwin', 'macosx_11_0_arm64'),
              ('macos-x64', 'x86_64-apple-darwin', 'macosx_11_0_x86_64')],
    'windows': [('windows-x64', 'x86_64-pc-windows-msvc', 'win_amd64')],
}
LICENSES = ['LICENSE', 'LICENSE.bdb.txt', 'LICENSE.bzip2.txt', 'LICENSE.cpython.txt',
            'LICENSE.expat.txt', 'LICENSE.libX11.txt', 'LICENSE.libXau.txt', 'LICENSE.libedit.txt',
            'LICENSE.libffi.txt', 'LICENSE.liblzma.txt', 'LICENSE.libuuid.txt', 'LICENSE.libxcb.txt',
            'LICENSE.mpdecimal.txt', 'LICENSE.ncurses.txt', 'LICENSE.openssl-3.txt', 'LICENSE.sqlite.txt',
            'LICENSE.tcl.txt', 'LICENSE.tix.txt', 'LICENSE.zlib-ng.txt', 'LICENSE.zlib.txt',
            'LICENSE.zstd.txt', 'python-licenses.rst']


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def download(url, path, expected=None):
    if path.exists() and (expected is None or digest(path) == expected):
        return
    partial = path.with_suffix(path.suffix + '.part')
    for attempt in range(3):
        try:
            with urlopen(url, timeout=45) as r, partial.open('wb') as f:
                shutil.copyfileobj(r, f, length=1024 * 1024)
            if expected and digest(partial) != expected:
                raise ValueError('Downloaded runtime checksum mismatch: ' + path.name)
            partial.replace(path)
            return
        except (OSError, ValueError):
            if attempt == 2:
                raise
            print('Retrying download:', path.name, flush=True)
            time.sleep(1)


def prepare(target):
    check_build_host(target)
    if sys.version_info[:2] != (3, 13):
        raise ValueError('Maintainer build tools require Python 3.13; end users do not need Python')
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / 'packaging/runtime-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    shutil.copy2(manifest_path, DOWNLOADS / manifest_path.name)
    for name, triple, wheel_platform in TARGETS[target]:
        asset = next(x for x in manifest['assets'] if triple in x['name'])
        archive = DOWNLOADS / asset['name']
        print('Preparing', name, flush=True)
        download(asset['browser_download_url'], archive, asset['digest'].split(':')[1])
        runtime = DOWNLOADS / ('runtime-' + name)
        stage = DOWNLOADS / ('extract-' + name)
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir()
        try:
            with tarfile.open(archive) as t:
                t.extractall(stage, filter='data')
            if runtime.exists():
                shutil.rmtree(runtime)
            (stage / 'python').rename(runtime)
        finally:
            shutil.rmtree(stage)
        wheels = DOWNLOADS / ('wheels-' + name)
        wheels.mkdir(exist_ok=True)
        lock = ROOT / 'packaging/locks' / (name + '.txt')
        common = ['--only-binary=:all:', '--platform', wheel_platform, '--python-version', '3.13',
                  '--implementation', 'cp', '--abi', 'cp313', '--require-hashes', '-r', str(lock),
                  '--disable-pip-version-check']
        subprocess.run([sys.executable, '-m', 'pip', 'download', '--dest', str(wheels), '--find-links', str(wheels)] + common, check=True)
        site = runtime / ('Lib/site-packages' if target == 'windows' else 'lib/python3.13/site-packages')
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--target', str(site), '--upgrade',
                        '--no-compile', '--no-index', '--find-links', str(wheels)] + common, check=True)
        print('Ready:', name, flush=True)
    licenses = DOWNLOADS / 'runtime-licenses'
    licenses.mkdir(exist_ok=True)
    for name in LICENSES:
        download('https://raw.githubusercontent.com/astral-sh/python-build-standalone/'
                 + manifest['release'] + '/' + name, licenses / name)
    print('Preparation complete. No API key used and no image request submitted.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=['macos', 'windows'])
    args = parser.parse_args()
    prepare(args.target)
