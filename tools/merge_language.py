"""Put the lines of a language file someone sent into the game's own.

    py tools/merge_language.py FILE LANGUAGE

FILE is the file that was sent: a whole language, or a copy with a few lines fixed.  LANGUAGE is the game's
file to put them in, by its name without .json ("ru", "Deutsch"); if there is none of that name yet, it is
made, which is how a new language becomes part of the game.

Every line FILE has translated goes into LANGUAGE, in the place that line already has there: the files are
written in one order, so only the lines that really changed are different, and that is all a commit of it
shows.  A line FILE leaves empty changes nothing.  A line the game does not have is not added, and is named,
since it is most likely one the game has since reworded.  Nothing is taken out.  Each line that changes is
printed, as it was and as it is now, and "@plural" too when FILE counts differently.

Then run py tools/verify_localization.py, and commit.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import make_language                                               # noqa: E402  (its list of lines)
from audiodefence import localization                              # noqa: E402


def merge(sent: dict, table: dict, known: set) -> tuple:
    """Put what `sent` has translated into `table`.  Returns (the lines changed, as (English, was, now);
    the lines the game does not have)."""
    changed, unknown = [], []
    for key, value in sent.items():
        if not isinstance(value, str) or not value.strip():
            continue
        if key == '@plural':
            if localization.plural_rule_named(value)[0] != localization.plural_rule_named(table.get(key))[0]:
                changed.append((key, table.get(key, ''), value))
                table[key] = value
            continue
        if key.startswith('@'):                            # about that file, not a phrase
            continue
        if key not in known:
            unknown.append(key)
            continue
        if table.get(key, '') != value:
            changed.append((key, table.get(key, ''), value))
            table[key] = value
    return changed, unknown


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('file', help='the file that was sent')
    parser.add_argument('language', help='the game\'s language file to put it in, by its name without .json '
                                         '("ru", "Deutsch")')
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')   # the lines are in any language
    except (AttributeError, ValueError):
        pass

    sent, problem = localization.read_file(args.file)
    if problem:
        print(problem)
        return 1
    target = localization.file_for(args.language)
    table = {}
    if os.path.isfile(target):
        table, problem = localization.read_file(target)
        if problem:
            print(problem)
            return 1
    if os.path.abspath(args.file) == os.path.abspath(target):
        print('That is the game\'s own file already: there is nothing to put in it.')
        return 1

    phrases = make_language.every_phrase(besides=os.path.basename(target))
    known = set(phrases) | {key for key in table if not key.startswith('@')}
    changed, unknown = merge(sent, table, known)

    where = os.path.relpath(target, ROOT)
    existed = os.path.isfile(target)
    with open(target, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(localization.dump(table))
    localization.fill_in(target, phrases)                  # every line the game has, the new ones empty

    for key, was, now in changed:
        print(key)
        print('    was: %s' % (was or '(empty)'))
        print('    now: %s' % now)
    print()
    print('%s: %d line%s changed%s.' % (where, len(changed), '' if len(changed) == 1 else 's',
                                         '' if existed else ', in a new file'))
    if unknown:
        print('%d line%s the game does not have, so not put in (reworded since, most likely):'
              % (len(unknown), '' if len(unknown) == 1 else 's'))
        for key in unknown:
            print('    %s' % key)
    print('Then: py tools/verify_localization.py, and commit.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
