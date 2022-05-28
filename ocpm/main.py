#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import requests
import ruamel.yaml
import tqdm as tqdm
from hypy_utils import printc
from packaging import version
from tqdm.contrib.concurrent import thread_map

from .interaction import print_updates, sizeof_fmt
from .models import Kext, Release


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
    releases = requests.get(f'https://api.github.com/repos/{repo}/releases').json()
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
    chunk_size = 1024
    r = requests.get(url, stream=True)
    with open(file, 'wb') as f:
        pbar = tqdm.tqdm(unit="B", total=int(r.headers['Content-Length']))
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                pbar.update(len(chunk))
                f.write(chunk)
    return file


def download_updates(updates: list[tuple[Kext, Release]]):
    # Create temporary directory
    with TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        print('Downloading zip files...')
        for k, r in updates:
            download_file(r.artifact.url, r.artifact.name)


def run():
    parser = argparse.ArgumentParser(description='OpenCore Kext Updater by HyDEV')
    parser.add_argument('efi_path', help='EFI Directory Path')
    parser.add_argument('--pre', action='store_true', help='Use pre-release')
    parser.add_argument('-y', action='store_true', help='Say yes')

    printc('\n&fOpenCore Kext Updater v1.0.0 by HyDEV\n')
    args = parser.parse_args()

    # Normalize EFI Path
    efi = Path(args.efi_path)
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
    with open(Path(__file__).parent / 'OCKextRepos.yml') as f:
        repos = ruamel.yaml.safe_load(f)

    # Get latest repos with multithreading
    def get_latest(k: Kext):
        try:
            return get_latest_release(k, repos, args.pre)
        except AssertionError:
            return None

    term_len = os.get_terminal_size().columns
    bar_len = int(term_len * 0.4)
    latests = thread_map(get_latest, kexts, desc='Fetching Updates'.ljust(bar_len), max_workers=32, bar_format='{desc} {rate_fmt} {remaining} [{bar}] {percentage:.0f}%', ascii=' #', unit=' pkg')

    # Compare versions
    updates: list[tuple[Kext, Release]]
    updates = [(k, l) for k, l in zip(kexts, latests) if l and version.parse(l.tag) > version.parse(k.version)]

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

    download_updates(updates)


if __name__ == '__main__':
    run()
