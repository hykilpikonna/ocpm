# ocpm - OpenCore Package Manager [WIP]

![image](https://user-images.githubusercontent.com/22280294/170818152-b202a3ba-2a48-4ccd-8abe-4e4514b8ec67.png)

## Installation

You have to install python >3.7 with pip first, then:

```sh
pip install ocpm
```

## Usage

First, cd to your EFI directory, and then run `ocpm -U` to update all kexts.

Use `ocpm -I [kext names...]` to install kexts

## Features / To-do

* [x] Update kexts to the latest version
* [x] Install kexts
* [ ] Uninstall kexts
* [ ] Resolve dependencies
* [ ] Install specific versions of a kext
* [ ] Install OS-dependent kexts (like AirportItlwm)
* [ ] Update OpenCore itself
