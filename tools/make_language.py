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

Run this again whenever the port gains text: it brings **every** language file under `localization/` up to
date at once, and the template with them.  A file keeps every phrase translated and only the new ones arrive
empty; nothing is ever removed.  Name one file to do only that one, or to start one under the name the
Language row should give it (`py tools/make_language.py "Bahasa Melayu"`).
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


def update(path: str, phrases: list) -> tuple:
    """Bring one language file up to date: every phrase it lacks arrives empty, nothing it has is touched.
    Returns (added, translated, phrases in it), or None with the reason when the file cannot be read."""
    had = {}
    if os.path.isfile(path):
        try:
            with io.open(path, encoding='utf-8') as fh:
                had = json.load(fh)
        except ValueError as exc:
            return None, '%s is there but is not readable as JSON: %s' % (path, exc)
        if not isinstance(had, dict):
            return None, '%s is not a map of phrases' % path
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
    count = sum(1 for key in table if not key.startswith('@'))
    return (added, done, count, bool(table.get('@plural')), bool(had)), None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('language', nargs='?',
                        help='one language file to bring up to date, or to start, by its name without .json '
                             '("Bahasa Melayu", ru); with nothing, every file under localization/ and %s.json'
                             % TEMPLATE)
    parser.add_argument('--into', help='write one file somewhere else than localization/')
    args = parser.parse_args(argv)

    # Which files: the one named, or every language file there is, and the template a new language starts
    # from.  With nothing named this used to write the template and nothing else, so a phrase the port had
    # gained reached a new translator and never the languages already written (user request, 2026-09-29).
    if args.into:
        paths_ = [args.into]
    elif args.language:
        paths_ = [os.path.join(paths.LOCALIZATION, '%s.json' % args.language)]
    else:
        names = [name for name in localization.available() if name != localization.ENGLISH]
        if TEMPLATE not in names:
            names.append(TEMPLATE)
        paths_ = [os.path.join(paths.LOCALIZATION, '%s.json' % name) for name in names]

    failed = False
    for path in paths_:
        phrases = every_phrase(besides=os.path.basename(path))
        result, problem = update(path, phrases)
        where = os.path.relpath(path, ROOT)
        if result is None:
            print(problem)
            failed = True
            continue
        added, done, count, counted, existed = result
        if existed:
            print('%s: %d new, %d of %d translated.' % (where, added, done, count))
        else:
            print('%s: written with %d phrases, every one of them empty.' % (where, count))
        if not counted:
            print('    Say how the language counts in "@plural" at the top: the choices are in "@plural guide".')
    print('An empty phrase stays English, so a file can be used before it is finished.')
    if not args.language and not args.into:
        print('%s.json is for starting a new language: the game offers it in Settings while it is there, and a'
              % TEMPLATE)
        print('build leaves it out.  When it is ready, rename it to what the Language row should call it.')
    print('Then: py tools/verify_localization.py')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
