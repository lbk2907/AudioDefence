"""Write localization/template.json: every phrase the port can show or speak, ready to be filled in.

    py tools/make_language.py                double-click it, or run it with nothing after it

Run it and it writes `localization/template.json`, a flat map from each English phrase to an empty one.
Those phrases are everything the port can put in front of a player - the text-carrying calls in its own
code, and the phrases of the game's own data - so a translator has the list rather than having to find it.

Fill the empty ones in, in any order.  An empty phrase is left alone by the game, so the file works from
the first line: what is translated is translated, and the rest stays English.  While it is there the game
offers it in Settings as a language of its own, so it can be heard while it is being written, without a
code being chosen or anything being renamed.

Some phrases have a gap the game fills in: `%i` a number, `%s` a name or a word ("You need %i stars to play
this level").  Write your sentence round the same gaps.  They are filled in the English order; to change the
order, number them by their place in the English (`%2$s ... %1$s`).  A word that changes with a number is
written with all its forms in braces, where your language puts it: "I have %i {apple|apples}".  How your
language counts goes once in the file, in the entry "@plural", which this writes empty, with the choices
written out beside it in "@plural guide" (`localization.PLURAL_GUIDE`).

When it is ready, rename it to whatever the Language row should say - `Deutsch.json`, `de.json`: the row
offers a language by its file's name, whatever that is, and nothing in the code needs to change.
`template.json` is not committed: it belongs to whoever is writing it.

Run this again whenever the port gains text.  A file that is already there keeps every phrase translated
and only the new ones arrive empty; nothing is ever removed.  Pass a language code to do the same for one
that has been renamed already (`py tools/make_language.py ru`).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import verify_localization as verifier                             # noqa: E402  (its collectors are the point)
from audiodefence import localization, paths                       # noqa: E402

#: what a translator works in until they choose a code for it (GameParameters.TEMPLATE_LANGUAGE)
TEMPLATE = 'template'


def every_phrase(besides: str = '') -> list:
    """Every phrase a translator should be given.

    Two sources, because neither is enough on its own.  The first is what `verify_localization.py` walks -
    the text-carrying calls in the port's own code, and the phrases of the game's data.  The second is the
    phrases the languages already written know, because the first has a blind spot: a phrase of one word
    ("Play", "Settings", "Quit", "Armory") looks exactly like an identifier, and `is_plumbing` has to treat
    it as one or the list would fill with sound names and keys.  Those words are some of the first a player
    meets, and a language that had only the first source would leave the main menu in English.

    So a new file starts with everything the languages before it found, and anyone writing the first
    language for a project still gets the walked list.  `besides` is the file being written, whose own
    phrases are already in hand.
    """
    seen = {}
    for source in (verifier.code_phrases(), verifier.data_phrases()):
        for text, _where in source:
            if text in verifier.LEFT_ALONE:
                continue
            seen.setdefault(text, None)
    folder = paths.LOCALIZATION
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if not name.endswith('.json') or name == besides:
                continue
            try:
                with io.open(os.path.join(folder, name), encoding='utf-8') as fh:
                    known = json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(known, dict):
                for text in known:
                    if not text.startswith('@'):           # about that file, not a phrase
                        seen.setdefault(text, None)
    return sorted(seen)


def dump(table: dict) -> str:
    """The file as it is written: the entries about the file ("@plural" and its guide) first, where a
    translator opening it sees them, then every phrase in order.  Sorted whole, they would come after the
    phrases that start with a space or a percent sign, a hundred and eighty lines down."""
    about = sorted(key for key in table if key.startswith('@'))
    ordered = {key: table[key] for key in about}
    ordered.update((key, table[key]) for key in sorted(table) if not key.startswith('@'))
    return json.dumps(ordered, ensure_ascii=False, indent=1) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('language', nargs='?', default=TEMPLATE,
                        help="a language already renamed from the template (ru, de); the default writes "
                             'localization/%s.json' % TEMPLATE)
    parser.add_argument('--into', help='write somewhere else than localization/<code>.json')
    args = parser.parse_args(argv)

    path = args.into or os.path.join(paths.LOCALIZATION, '%s.json' % args.language)
    had = {}
    if os.path.isfile(path):
        try:
            with io.open(path, encoding='utf-8') as fh:
                had = json.load(fh)
        except ValueError as exc:
            print('%s is there but is not readable as JSON: %s' % (path, exc))
            return 1
        if not isinstance(had, dict):
            print('%s is not a map of phrases' % path)
            return 1

    phrases = every_phrase(besides=os.path.basename(path))
    table = dict(had)
    table.setdefault('@plural', '')                        # the language's counting rule: see above
    table['@plural guide'] = localization.PLURAL_GUIDE    # the choices, where the translator is looking
    added = 0
    for text in phrases:
        if text not in table:
            table[text] = ''
            added += 1

    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(dump(table))

    done = sum(1 for key, value in table.items() if value and not key.startswith('@'))
    where = os.path.relpath(path, ROOT)
    if had:
        print('%s: %d phrases the port can show, %d of them new here.' % (where, len(phrases), added))
    else:
        print('%s: written with %d phrases, every one of them empty.' % (where, len(phrases)))
    phrases_in = sum(1 for key in table if not key.startswith('@'))
    print('%d of %d translated. Fill in the empty ones, in the same order or any other.' % (done, phrases_in))
    if not table.get('@plural'):
        print('Say how your language counts in "@plural" at the top: the choices are in "@plural guide".')
    if done < phrases_in:
        print('An empty phrase stays English, so the file can be used before it is finished.')
    if args.language == TEMPLATE:
        print('The game offers it in Settings as a language while it is there, so it can be heard as it is')
        print('written. When it is ready, rename it to what the Language row should call it.')
    print('Then: py tools/verify_localization.py --language %s' % args.language)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
