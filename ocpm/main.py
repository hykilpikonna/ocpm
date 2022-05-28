#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import plistlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from packaging import version

import dateutil.parser
import pandas
import requests
import tqdm as tqdm
import ruamel.yaml
import semver
from hypy_utils import printc
from pandas import DataFrame
from tqdm.contrib.concurrent import thread_map

from interaction import print_updates, sizeof_fmt


@dataclass()
class Kext:
    path: Path

    name: str
    id: str
    version: str
    sdk_os: str
    min_os: str

    def __init__(self, path: Path):
        self.path = path

        # Find plist file
        plist = path / 'Contents' / 'Info.plist'
        if not plist.is_file():
            print(f'Error loading {path.name}: Cannot find Info.plist')

        # Load plist file
        plist = plistlib.loads(plist.read_bytes())

        self.name = plist['CFBundleName']
        self.id = plist['CFBundleIdentifier']
        self.version = plist['CFBundleVersion']
        self.sdk_os = plist.get('DTSDKName')
        self.min_os = plist.get('LSMinimumSystemVersion')

        if self.sdk_os:
            self.sdk_os = self.sdk_os.replace('macosx', '')


def print_kexts(kexts: list[Kext]):
    df = DataFrame(kexts)
    df = df.drop(columns=['path', 'id'])
    # df['path'] = df['path'].apply(lambda x: x.name.replace('.kext', ''))
    print(df.to_string())


@dataclass()
class Artifact:
    size: int
    url: str
    name: str

    @classmethod
    def from_github(cls, obj: dict) -> "Artifact":
        return cls(obj['size'], obj['browser_download_url'], obj['name'])


def find_artifact(raw: dict) -> Artifact:
    assets = raw['assets']
    if len(assets) == 1:
        return Artifact.from_github(assets[0])

    # Filter out DEBUG artifacts
    assets = [a for a in assets if not a['name'].endswith('DEBUG.zip')]
    return Artifact.from_github(assets[0])


@dataclass()
class Release:
    tag: str
    raw: dict
    artifact: Artifact
    date: datetime

    @classmethod
    def from_github(cls, raw: dict) -> "Release":
        tag = raw['tag_name']
        if tag.startswith('v'):
            tag = tag[1:]

        date = dateutil.parser.parse(raw['published_at'])
        artifact = find_artifact(raw)

        return cls(tag, raw, artifact, date)


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
    proceed = input(f'🚀 Ready to fly? [y/N] ')

    if proceed.lower().strip() != 'y':
        print()
        print('😕 Huh, okay')
        exit(0)


if __name__ == '__main__':
    run()
