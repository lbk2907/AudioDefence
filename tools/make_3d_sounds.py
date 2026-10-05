"""Make 3D sounds - .mhr files - from research recordings - .sofa files - with the repository's makemhr.

Every .sofa in the folder that has no .mhr as new as itself is made into one of the same name beside it, which
Settings -> Sound -> 3D sound then lists (audiodefence/s3d/makehrtf.py, which the game uses to do the same from
that row on Windows).  The folder is the hrtf folder beside the game: run from the repository, its own top-level
hrtf; or name another, such as a built game's.  Double-clicked, the window waits at the end so what happened can
be heard.  Windows only, as makemhr is: on the Mac, make the .mhr on a Windows computer.  The README's "Your own
3D sound" says where research sets are and under what terms.

    py tools/make_3d_sounds.py                      the repository's hrtf folder
    py tools/make_3d_sounds.py dist/AudioDefence/hrtf
    py tools/make_3d_sounds.py --all                make every one again, new or not
"""
from __future__ import annotations

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from audiodefence.s3d import makehrtf, sound3d             # noqa: E402


def main(argv) -> int:
    ap = argparse.ArgumentParser(description='Make .mhr 3D sounds from the .sofa files in a folder.')
    ap.add_argument('folder', nargs='?', help='where the .sofa files are, and the .mhr files go '
                                              '(default: the hrtf folder beside the game)')
    ap.add_argument('--all', action='store_true', help='make every one again, even those already made')
    args = ap.parse_args(argv)
    folder = os.path.abspath(args.folder or sound3d.folder())
    if not makehrtf.can_make():
        print('makemhr is not here, or this is not Windows: %s' % makehrtf.MAKEMHR)
        return 2
    if not os.path.isdir(folder):
        print('There is no folder %s.' % folder)
        return 2
    files = makehrtf.waiting(folder, everything=args.all)
    if not files:
        print('Nothing to make in %s: every .sofa there has its .mhr already.' % folder)
        return 0
    print('Making %d 3D sound%s in %s, with makemhr on %d threads.'
          % (len(files), '' if len(files) == 1 else 's', folder, makehrtf.THREADS))
    failed = 0
    for sofa in files:
        name = os.path.basename(sofa)
        print('%s ...' % name, flush=True)
        began = time.perf_counter()
        problem = makehrtf.make(sofa)
        if problem:
            failed += 1
            print('  not made: %s' % problem)
        else:
            print('  made %s, in %.0f seconds.' % (os.path.basename(makehrtf.target_of(sofa)),
                                                   time.perf_counter() - began))
    print('Done: %d made, %d not.' % (len(files) - failed, failed) if failed else
          'Done. Choose them in Settings, Sound tab, 3D sound.')
    return 1 if failed else 0


def run() -> int:
    """With no arguments and a keyboard at the other end - a double-click - the window waits at the end."""
    argv = sys.argv[1:]
    try:
        return main(argv)
    finally:
        if not argv and sys.stdin.isatty():
            try:
                input('Press Enter to close this window.')
            except EOFError:
                pass


if __name__ == '__main__':
    sys.exit(run())
