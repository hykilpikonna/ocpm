#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import requests
import ruamel.yaml
import tqdm as tqdm
from hypy_utils import printc
from packaging import version
from tqdm.contrib.concurrent import thread_map

from .interaction import print_updates, sizeof_fmt
from .models import Kext, Release


try:
    term_len = os.get_terminal_size().columns
    bar_len = int(term_len * 0.4)
except Exception:
    bar_len = 20


def get_latest_release(kext: Kext, repos: dict, pre: bool):
    # Lowercase keys
    repos = {k.lower(): v for k, v in repos['Repos'].items()}
    name = kext.name.lower()

    # Find repo
    assert name in repos, f'Kext {kext.name} is not found in our repos. (If it\'s open source, feel free to add it in!)'
    repo_info = repos[name]

    if isinstance(repo_info, str):
        repo = repo_info
    else:
        repo = repo_info['Repo']
        artifact = repo_info.get('Artifact')

    assert 'github.com/' in repo, f'For {kext.name}: {repo} is not a github repo, skipping...'
    repo = repo.split('github.com/')[1]

    # Check latest version
    headers = {}
    if 'GH_TOKEN' in os.environ:
        headers['Authorization'] = f'token {os.environ["GH_TOKEN"]}'
    releases = requests.get(f'https://api.github.com/repos/{repo}/releases', headers=headers).json()
    if not pre:
        releases = [r for r in releases if not r['prerelease']]
    latest = releases[0]

    return Release.from_github(latest)


def download_file(url: str, file: str | Path):
    """
    Helper method handling downloading large files from `url` to `filename`.
    Returns a pointer to `filename`.

    https://stackoverflow.com/a/42071418/7346633
    """
    file = Path(file)
    if file.is_file():
        return file

    chunk_size = 1024
    r = requests.get(url, stream=True)
    with open(file, 'wb') as f:
        pbar = tqdm.tqdm(unit=" MB", total=int(r.headers['Content-Length']) / 1024 / 1024,
                         bar_format='{desc} {rate_fmt} {remaining} [{bar}] {percentage:.0f}%', ascii=' #', desc=file.name[:bar_len].ljust(bar_len))
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                pbar.update(len(chunk) / 1024 / 1024)
                f.write(chunk)
    return file


def download_updates(efi: Path, updates: list[tuple[Kext, Release]]):
    # Create temporary directory
    with TemporaryDirectory() as tmp:
        start = time.time_ns()

        tmp = Path(tmp)
        kexts = tmp / 'extract'
        kexts.mkdir(parents=True, exist_ok=True)
        backup = efi.parent / f'Backups/{datetime.now().strftime("%m-%d %H-%M")}'
        backup.mkdir(parents=True, exist_ok=True)

        print('Downloading zip files...')
        files = [(k, r, download_file(r.artifact.url, tmp / r.artifact.name)) for k, r in updates]

        print()
        print('Extracting kexts...')

        def extract(k: Kext, f: Path):
            if f.suffix != '.zip':
                print(f'Unable to process {f.name}. Currently only zip files are supported.')
                return None

            with ZipFile(f, 'r') as zipf:
                lower = k.name.lower() + '.kext/'

                def find_name():
                    for n in zipf.namelist():
                        if n.lower().endswith(lower):
                            return n

                    return None

                name = find_name()
                if not find_name():
                    print(f'Unable to find {k.name}.kext in {f.name}, skipping.')
                    return None

                for to_extract in zipf.namelist():
                    if to_extract.startswith(name):
                        zipf.extract(to_extract, kexts)

                return kexts / name

        extracted = [(k, r, extract(k, f)) for k, r, f in files]
        extracted = [e for e in extracted if e[2]]

        print(f'Backing up original kexts to {backup}...')
        for k, r, e in extracted:
            shutil.move(k.path, backup / k.name)

        print(f'Installing new kexts...')
        for k, r, e in extracted:
            shutil.move(e, k.path)

        print()
        print(f'✨ All Done in {(time.time_ns() - start) / 1e6:,.0f}s!')


def run():
    parser = argparse.ArgumentParser(description='OpenCore Package Manager by HyDEV')
    parser.add_argument('cmd', help='Command (update)')
    parser.add_argument('--efi', help='EFI Directory Path', default='.')
    parser.add_argument('--pre', action='store_true', help='Use pre-release')
    parser.add_argument('-y', action='store_true', help='Say yes')

    printc('\n&fOpenCore Package Manager v1.0.0 by HyDEV\n')
    args = parser.parse_args()

    if args.cmd.lower() != 'update':
        print(f'Unknown Command: {args.cmd}')
        return

    # Normalize EFI Path
    efi = Path(args.efi)
    if (efi / 'EFI').is_dir():
        efi = efi / 'EFI'
    assert (efi / 'OC').is_dir(), 'Open Core directory (OC) not found.'

    # Find kexts
    kexts_dir = efi / 'OC' / 'Kexts'
    kexts = [str(f) for f in os.listdir(kexts_dir)]
    kexts = [kexts_dir / f for f in kexts if f.lower().endswith('.kext')]

    kexts = [Kext(k) for k in kexts]
    print(f'🔍 Found {len(kexts)} kexts in {kexts_dir}')
    # print_kexts(kexts)

    # Read Repo
    with open(Path(__file__).parent / 'data' / 'OCKextRepos.yml') as f:
        repos = ruamel.yaml.safe_load(f)

    # Get latest repos with multithreading
    def get_latest(k: Kext):
        try:
            return get_latest_release(k, repos, args.pre)
        except AssertionError as e:
            print(e)
            return None

    latests = thread_map(get_latest, kexts, desc='Fetching Updates'.ljust(bar_len), max_workers=32, bar_format='{desc} {rate_fmt} {remaining} [{bar}] {percentage:.0f}%', ascii=' #', unit=' pkg')

    # Compare versions
    updates: list[tuple[Kext, Release]]
    updates = [(k, l) for k, l in zip(kexts, latests) if l and version.parse(l.tag) > version.parse(k.version)]

    if len(updates) == 0:
        print(f'✨ Everything up-to-date!')
        exit(0)

    # Print updates
    printc(f'\n✨ Found {len(updates)} Updates:')
    print_updates(updates)

    # Download prompt
    print()
    print(f'Total download size: {sizeof_fmt(sum(l.artifact.size for k, l in updates))}')
    proceed = 'y' if args.y else input(f'🚀 Ready to fly? [y/N] ')

    if proceed.lower().strip() != 'y':
        print()
        print('😕 Huh, okay')
        exit(0)

    print()
    download_updates(efi, updates)


if __name__ == '__main__':
    run()
