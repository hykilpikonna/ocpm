#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import time
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import requests
import ruamel.yaml
import tqdm as tqdm
from hypy_utils import printc, ensure_dir
from packaging import version
from tqdm.contrib.concurrent import thread_map

from .interaction import print_updates, sizeof_fmt
from .models import Kext, Release


try:
    term_len = os.get_terminal_size().columns
    bar_len = int(term_len * 0.4)
except Exception:
    bar_len = 20


def get_latest_release(name: str, repos: dict, pre: bool):
    # Lowercase keys
    repos = {k.lower(): v for k, v in repos['Repos'].items()}
    name = name.lower()

    # Find repo
    assert name in repos, f'Kext {name} is not found in our repos. (If it\'s open source, feel free to add it in!)'
    repo_info = repos[name]

    if isinstance(repo_info, str):
        repo = repo_info
    else:
        repo = repo_info['Repo']
        artifact = repo_info.get('Artifact')

    assert 'github.com/' in repo, f'For {name}: {repo} is not a github repo, skipping...'
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


def extract_kext(kext_name: str, zip_file: Path, tmp_dir: Path) -> Path | None:
    if zip_file.suffix != '.zip':
        print(f'Unable to process {zip_file.name}. Currently only zip files are supported.')
        return None

    with ZipFile(zip_file, 'r') as zipf:
        lower = kext_name.lower() + '.kext/'

        def find_name():
            for n in zipf.namelist():
                if n.lower().endswith(lower):
                    return n

            return None

        name = find_name()
        if not name:
            print(f'Unable to find {kext_name}.kext in {zip_file.name}, skipping.')
            return None

        for to_extract in zipf.namelist():
            if to_extract.startswith(name):
                zipf.extract(to_extract, tmp_dir)

        return tmp_dir / name


def download_updates(efi: Path, updates: list[tuple[Kext, Release]]):
    # Create temporary directory
    with TemporaryDirectory() as tmp:
        start = time.time_ns()

        tmp = Path(tmp)
        kexts = ensure_dir(tmp / 'extract')

        print('Downloading zip files...')
        files = [(k, r, download_file(r.artifact.url, tmp / r.artifact.name)) for k, r in updates]

        print()
        print('Extracting kexts...')

        extracted = [(k, r, extract_kext(k.name, f, kexts)) for k, r, f in files]
        extracted = [e for e in extracted if e[2]]

        # Backup if needed
        existing = [t for t in extracted if t[0].path.is_dir()]
        if len(existing) > 0:
            backup = ensure_dir(efi.parent / f'Backups/{datetime.now().strftime("%m-%d %H-%M")}')
            print(f'Backing up original kexts to {backup}...')
            for k, r, e in existing:
                shutil.move(k.path, backup / k.name)

        print(f'Installing new kexts...')
        for k, r, e in extracted:
            shutil.move(e, k.path)

        print()
        print(f'✨ All Done in {(time.time_ns() - start) / 1e6:,.0f}s!')


def get_latest_list(names: list[str], repos: dict, args) -> list[Release]:
    def get_latest(s: str):
        try:
            return get_latest_release(s, repos, args.pre)
        except AssertionError as e:
            print(e)
            return None

    return thread_map(get_latest, names, desc='Fetching Kexts'.ljust(bar_len), max_workers=32, bar_format='{desc} {rate_fmt} {remaining} [{bar}] {percentage:.0f}%', ascii=' #', unit=' pkg')


def update(args, repos: dict, kexts: list[Kext], efi: Path):
    latests = get_latest_list([k.name for k in kexts], repos, args)

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


def install(args, repos: dict, kexts: list[Kext], efi: Path):
    names = args.install
    latests = get_latest_list(names, repos, args)

    # Compare versions
    updates: list[tuple[Kext, Release]]
    updates = [(Kext(efi / 'OC' / 'Kexts' / (n + '.kext'), n, version=l.tag), l) for n, l in zip(names, latests) if l]

    if not updates:
        printc('&cNo kexts found. Exiting')
        return

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
    enable(names, find_kexts(efi), efi)


def enable(names: list[str], kexts: list[Kext], efi: Path):
    config_plist: dict = plistlib.loads((efi / 'OC' / 'Config.plist').read_bytes())
    config_kexts: list[dict] = config_plist['Kernel']['Add']

    def conf_kext_index() -> dict[str, dict]:
        return {k['BundlePath'].split('.kext')[0]: k for k in config_kexts}

    # Find relevant kexts
    index: dict[str: Kext] = {k.path.name.lower().split('.kext')[0]: k for k in kexts}
    kexts: list[Kext] = [index.get(n.lower()) for n in names]
    for n, orig in zip(kexts, names):
        assert n, f'{orig} is not found'

    # Modify config.plist
    for k in kexts:
        # Kext config entry doesn't exist, create one
        if k.name not in conf_kext_index():
            exec_path = f'Contents/MacOS/{k.name}'
            exec_path = exec_path if (k.path / exec_path).is_file() else ''
            if not exec_path and (k.path / 'Contents/MacOS').is_dir():
                execs = os.listdir(k.path / 'Contents/MacOS')
                if execs:
                    exec_path = f'Contents/MacOS/{execs[0]}'

            config_kexts.append({
                'Arch': 'x86_64',
                'BundlePath': k.path.name,
                'Comment': '',
                'Enabled': True,
                'ExecutablePath': str(exec_path),
                'MaxKernel': '',
                'MinKernel': '',
                'PlistPath': 'Contents/Info.plist'
            })
        else:
            conf_kext_index()[k.name]['Enabled'] = True

    # Save config.plist
    (efi / 'OC' / 'Config.plist').write_bytes(plistlib.dumps(config_plist))
    print('Enabled!')


def find_kexts(efi: Path) -> list[Kext]:
    kexts_dir = efi / 'OC' / 'Kexts'
    kexts = [str(f) for f in os.listdir(kexts_dir)]
    kexts = [kexts_dir / f for f in kexts if f.lower().endswith('.kext')]
    kexts = [Kext.from_path(k) for k in kexts]
    return kexts


def run():
    parser = argparse.ArgumentParser(description='OpenCore Package Manager by HyDEV')
    parser.add_argument('-U', '--update', action='store_true', help='Update')
    parser.add_argument('-S', '--install', nargs='+', help='Install packages')
    parser.add_argument('-E', '--enable', nargs='+', help='Enable packages in Kexts directory')
    # parser.add_argument('-D', '--disable', nargs='+', help='Disable packages')
    parser.add_argument('--efi', help='EFI Directory Path', default='.')
    parser.add_argument('--pre', action='store_true', help='Use pre-release')
    parser.add_argument('-y', action='store_true', help='Say yes')

    printc('\n&fOpenCore Package Manager v1.0.0 by HyDEV\n')
    args = parser.parse_args()

    # Normalize EFI Path
    efi = Path(args.efi)
    if (efi / 'EFI').is_dir():
        efi = efi / 'EFI'
    assert (efi / 'OC').is_dir(), 'Open Core directory (OC) not found.'

    # Find kexts
    kexts = find_kexts(efi)
    print(f'🔍 Found {len(kexts)} kexts in {efi}')

    # Read Repo
    with open(Path(__file__).parent / 'data' / 'OCKextRepos.yml') as f:
        repos = ruamel.yaml.safe_load(f)

    if args.update:
        return update(args, repos, kexts, efi)

    if args.install:
        return install(args, repos, kexts, efi)

    if args.enable:
        return enable(args.enable, kexts, efi)


if __name__ == '__main__':
    run()
