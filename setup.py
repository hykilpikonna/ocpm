import pathlib

from setuptools import setup

import ocpm

# The directory containing this file
HERE = pathlib.Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()

# This call to setup() does all the work
setup(
    name="ocpm",
    version=ocpm.__version__,
    description="OpenCore Package Manager by HyDEV",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/hykilpikonna/ocpm",
    author="Azalea Gui",
    author_email="me@hydev.org",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    packages=['ocpm'],
    package_data={'ocpm': ['ocpm/data/*']},
    include_package_data=True,
    install_requires=['setuptools', 'hypy_utils', 'ruamel.yaml', 'requests', 'tqdm',
                      'packaging'],
    entry_points={
        "console_scripts": [
            "ocpm=ocpm.main:run",
        ]
    },
)
