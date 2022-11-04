from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from ocpm.main import download_file, get_latest_release_repo

if __name__ == '__main__':
    while True:
        repo = input("Please type in github repo name (e.g. owner/repo): ")

        release = get_latest_release_repo(repo, False)

        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)

            download_file(release.artifact.url, tmp / "artifact.zip")

            with ZipFile(tmp / 'artifact.zip', 'r') as f:
                names = [a.strip('/') for a in f.namelist() if a.lower().endswith('.kext/')]
                print('\n'.join(names))

            repos_path = Path('ocpm/data/OCKextRepos.yml')
            yml = ''.join(f'\n  {Path(a).stem}: https://github.com/{repo}' for a in names)
            repos_path.write_text(repos_path.read_text() + yml)
