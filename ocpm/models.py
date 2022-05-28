from __future__ import annotations

import plistlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


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


@dataclass()
class Artifact:
    size: int
    url: str
    name: str

    @classmethod
    def from_github(cls, obj: dict) -> "Artifact":
        return cls(obj['size'], obj['browser_download_url'], obj['name'])

    @classmethod
    def find_from_release(cls, raw: dict) -> "Artifact":
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
    # date: datetime

    @classmethod
    def from_github(cls, raw: dict) -> "Release":
        tag = raw['tag_name']
        if tag.startswith('v'):
            tag = tag[1:]

        # date = dateutil.parser.parse(raw['published_at'])
        artifact = Artifact.find_from_release(raw)

        return cls(tag, raw, artifact)
