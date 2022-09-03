from __future__ import annotations

from hypy_utils import printc

from .models import Kext, Release


def ver_diff(src: str, to: str):
    """
    Return the first decimal point that two version numbers differs
    """
    ssp = src.split('.')
    tsp = to.split('.')

    for i in range(len(ssp)):
        sv = ssp[i]
        tv = tsp[i]

        if sv.isnumeric() and tv.isnumeric():
            sv, tv = int(sv), int(tv)

        if sv != tv:
            return i

    return -1


def ver_color(src: str, to: str):
    """
    Compare versions and color output

    :param src: Source version
    :param to: Updated version
    :return: Compared version
    """
    tsp = to.split('.')

    try:
        i = ver_diff(src, to)
        return ('.'.join(tsp[:i]) + '.&a' + '.'.join(tsp[i:]) + '&r').strip('.')
    except Exception:
        return f'&a{to}&r'


def ver_color_prefix(src: str, to: str):
    i = ver_diff(src, to)
    if i > 2:
        return '&7'
    return ['&c', '&e', '&a'][i]


def len_nocolor(s: str):
    return len(s) - s.count('&') * 2


def ljust(s: str, l: int):
    return s + ' ' * (l - len_nocolor(s))


def rjust(s: str, l: int):
    return ' ' * (l - len_nocolor(s)) + s


def tabulate(lst: list[list[str]], headers: list[str]):
    """
    Print in table format, with justify and adjusted for colors
    """
    lens = [max(max(len_nocolor(it[col]) for it in lst), len_nocolor(headers[col])) for col in range(len(headers))]
    justify = [rjust if h.endswith(':') else ljust for h in headers]
    headers = [h[:-1] if h.endswith(':') else h for h in headers]

    # Add headers row
    lst.insert(0, [f'&f&n{h}&r' for h in headers])

    # Print list
    for it in lst:
        row = ' '.join(justify[col](v, lens[col]) for col, v in enumerate(it))
        printc(row)


def sizeof_fmt(num: int):
    """
    https://stackoverflow.com/a/1094933/7346633
    """
    for unit in ["B", "K", "M", "G", "T", "P", "E", "Z"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}"
        num /= 1024.0


def print_updates(updates: list[tuple[Kext, Release]]):
    upd_tbl = [[ver_color_prefix(k.version, l.tag) + k.name + '&r', k.version,
                ver_color(k.version, l.tag), sizeof_fmt(l.artifact.size)] for k, l in updates]
    tabulate(upd_tbl, ['Kext', 'Current', 'Latest', 'Size:'])
