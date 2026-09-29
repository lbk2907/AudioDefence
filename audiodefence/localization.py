"""PORT ADDITION: an optional localization layer, so a player can read and hear the port's own text in
another language than English.

Where the text comes from.  The port's text is its own - labels, hints, screen titles, the settings rows -
and the original game's, read out of the bundle's plists and `en.lproj`.  Neither is rewritten: everything
the player sees or hears passes through `View.label`, `View.hint`, `View.text`, `MenuItem.label`,
`MenuItem.hint`, `MenuScreen.title`, `AccessibleScreen.page_title`, `data.localized` and, in the end,
`Speech.speak`, so the text is translated on the way out.

How it is stored.  One JSON file per language under `localization/`, a flat map of an English phrase to
the phrase in that language, for example `localization/ru.json`.  Translations are data, so a language is
added by writing a file, not by touching code.  Nothing is translated while the language is English, which
is the default: a player who does not choose one sees exactly what the port always showed.

Whole phrases are the keys rather than single words, so a translation does not depend on how the port
assembled a line.  A phrase with substitutions (`%i` a number, `%s` anything else) becomes a rule, and the
translator writes the sentence their language wants around the same substitutions:

* **Order.**  `%s` and `%i` are filled in the order the English has them.  `%1$s`, `%2$s`... name one by
  its place in the English instead, so a sentence can put the second first: "%s is now %s" can be
  "%2$s ... %1$s".
* **Word forms.**  A word that changes with a number is written with all its forms between braces,
  wherever the language puts it: "I have %i {apple|apples}".  The braces go with the nearest number
  before them (or, if there is none, the first after), and the form is chosen by the language's own rule.
* **The rule** is named once in the file, in the entry "@plural", from `PLURAL_RULES`: how many forms a
  word has and which number takes which.  An entry starting with "@" is about the file, not a phrase.

No language lives in this module (user request, 2026-09-28): whatever is particular to one - its words,
its forms, its sentences - is in its own file, so a translator of any language has what the Russian one
had.
"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata

from . import paths

log = logging.getLogger('localization')

#: The language the port is written in, and the one used when nothing is chosen.
ENGLISH = 'en'

#: How a language chooses between the forms of a counted word: (how many forms, which one a number takes).
#: A language file names its rule in "@plural" and writes the forms in this order.  Arithmetic only - the
#: forms themselves are the language file's - and named after the languages that use them; the order
#: follows the Unicode plural categories.  A fraction takes the form the language gives 1.5.
def _one_other(n: float, whole: bool) -> int:            # 1 apple, 2 apples
    return 0 if whole and n == 1 else 1


def _one_below_two(n: float, whole: bool) -> int:        # 0 and 1 take the first form, 1.5 too
    return 0 if n < 2 else 1


def _east_slavic(n: float, whole: bool) -> int:          # 1, 21, 101 | 2-4, 22-24 | 0, 5-20, 25...
    if not whole:
        return 1
    n = int(n)
    if n % 10 == 1 and n % 100 != 11:
        return 0
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return 1
    return 2


def _polish(n: float, whole: bool) -> int:               # only 1 | 2-4, 22-24 | the rest
    if not whole:
        return 1
    n = int(n)
    if n == 1:
        return 0
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return 1
    return 2


def _czech(n: float, whole: bool) -> int:                # 1 | 2-4 | the rest
    if not whole:
        return 1
    return 0 if n == 1 else 1 if 2 <= n <= 4 else 2


def _arabic(n: float, whole: bool) -> int:               # 0 | 1 | 2 | 3-10 | 11-99 | the rest
    if not whole:
        return 5
    n = int(n)
    if n in (0, 1, 2):
        return n
    if 3 <= n % 100 <= 10:
        return 3
    if 11 <= n % 100 <= 99:
        return 4
    return 5


#: The ways of counting a file can name in "@plural".  README.md, "Words that change with a number", explains
#: them to translators, number by number: a rule added here is added there.
PLURAL_RULES = {
    'none': (1, lambda n, whole: 0),     # Malay, Indonesian, Chinese, Japanese, Korean, Thai, Vietnamese
    'one-other': (2, _one_other),        # English, German, Dutch, Spanish, Italian, Swedish, Greek
    'french': (2, _one_below_two),       # French, Brazilian Portuguese
    'east-slavic': (3, _east_slavic),    # Russian, Ukrainian, Belarusian
    'polish': (3, _polish),              # Polish
    'czech': (3, _czech),                # Czech, Slovak
    'arabic': (6, _arabic),              # Arabic
}
#: the rule a file that names none is read with
DEFAULT_PLURAL = 'one-other'

#: A substitution in a template.  No space in the flags, so a bare percent sign in the game's own writing
#: ("10% damage") is not taken for one.
_SPEC = re.compile(r'%[-+#0]*[0-9]*(?:\.[0-9]+)?[a-zA-Z]')
#: In a translation, also a substitution named by its place in the English ("%2$s"), and a word's forms
#: ("{apple|apples}", at least two of them, so a brace the translation means as a brace is left).
_VALUE_TOKEN = re.compile(r'%(?:(\d+)\$)?[-+#0]*[0-9]*(?:\.[0-9]+)?[a-zA-Z]|\{([^{}|]*(?:\|[^{}|]*)+)\}')
#: A word's forms on their own, for a template asked for with its gaps still empty.
_FORMS = re.compile(r'\{([^{}|]*(?:\|[^{}|]*)+)\}')
#: A substitution that is a number however it was written: "45", "1 000", "45.67", "45,67".
_NUMBER = re.compile(r'^-?\d[\d\s\u00a0]*(?:[.,]\d+)?$')

#: How the port joins the pieces of one line: "Gyro, Turns slowest", "Aiming. Selected", "A and B".
_SEGMENT_COMMA = re.compile(r'(, |; |: | -- )')
#: the glue the port puts between a row's title and its status
_TAIL_COMMA = re.compile(r', ')
_SEGMENT_SENTENCE = re.compile(r'(\. )')
_SEGMENT_JOIN = re.compile(r'( and | or )')
_SEPARATORS = ('. ', ', ', '; ', ': ', ' -- ')

_table: dict = {}
_rules: list = []
_weak_rules: list = []
_lower: dict = {}
_scan: list = []
_language: str | None = None
_plural = PLURAL_RULES[DEFAULT_PLURAL]

# --- the phrase table --------------------------------------------------------------------------

def file_for(language: str) -> str:
    return os.path.join(paths.LOCALIZATION, '%s.json' % language)


def available() -> tuple:
    """The languages a build carries, the port's own first: a language is a file, and its name is the
    file's own name without ".json" - the name the Language row offers it by, so a translator names the
    file what the language calls itself.  Taken in the composed form, so a name spelt with a letter a Mac
    keeps as two characters (the Russian short i) is the same name everywhere."""
    names = [ENGLISH]
    folder = paths.LOCALIZATION
    if os.path.isdir(folder):
        for entry in sorted(os.listdir(folder)):
            if entry.endswith('.json'):
                name = unicodedata.normalize('NFC', entry[:-len('.json')])
                if name != ENGLISH and name not in names:
                    names.append(name)
    return tuple(names)


# --- how a language counts ------------------------------------------------------------------------

def plural_rule_named(text) -> tuple:
    """(the rule, or None; the rule it was probably meant to be, or None) for what a file wrote in "@plural".

    Forgiving about how it is written, since a translator types it by hand: capitals, spaces, underscores
    and hyphens do not matter ("East Slavic", "east_slavic", "eastslavic"), and a name one or two letters
    out ("east-slavik") is taken for the one it is nearest, as long as nothing else is as near."""
    import difflib
    if not text:
        return None, None
    wanted = re.sub(r'[^a-z]', '', str(text).lower())
    squashed = {re.sub(r'[^a-z]', '', name): name for name in PLURAL_RULES}
    if wanted in squashed:
        return squashed[wanted], None
    near = difflib.get_close_matches(wanted, list(squashed), n=2, cutoff=0.8)
    if len(near) == 1:
        return squashed[near[0]], squashed[near[0]]
    return None, (squashed[near[0]] if near else None)


def load(language: str, force: bool = False) -> bool:
    """Read that language's file, and build its rules.  English - or a file that is not there - clears
    everything, which leaves `translate` returning what it is given."""
    global _table, _language, _rules, _weak_rules, _lower, _scan, _plural
    if not force and language == _language:
        return bool(_table)
    _language = language
    _table, _rules, _weak_rules, _lower, _scan = {}, [], [], {}, []
    _plural = PLURAL_RULES[DEFAULT_PLURAL]
    if language == ENGLISH:
        return False
    path = file_for(language)
    try:
        with open(path, encoding='utf-8') as fh:
            phrases = json.load(fh)
    except (OSError, ValueError) as exc:
        log.warning('localization: cannot read %s: %s', path, exc)
        return False
    if not isinstance(phrases, dict):
        log.warning('localization: %s is not a map of phrases', path)
        return False
    _table = {str(key): str(value) for key, value in phrases.items() if value and not str(key).startswith('@')}
    rule, _meant = plural_rule_named(phrases.get('@plural'))
    if rule is None:
        if phrases.get('@plural'):
            log.warning('localization: %s names a plural rule there is none of: %s', path, phrases.get('@plural'))
        rule = DEFAULT_PLURAL
    _plural = PLURAL_RULES[rule]
    _rules, _weak_rules = _build_rules(_table)
    _lower = {key.lower(): value for key, value in _table.items()}
    _scan = _build_scan(_table)
    log.info('localization: %s, %d phrases', language, len(_table))
    return True


def language() -> str:
    """The language the player chose, or English.  Imported here rather than at the top: the settings
    singleton imports this module's callers."""
    try:
        from .game.parameters import GameParameters
        return GameParameters.shared().language()
    except Exception:                                    # noqa: BLE001 - before the settings exist
        return ENGLISH


def follow() -> None:
    """Load the chosen language if it is not the one already loaded.  Called by whoever translates."""
    chosen = language()
    if chosen != _language:
        load(chosen)


def phrases() -> dict:
    """The phrases loaded now: what the verifier walks through."""
    return _table


# --- numbers and plurals -----------------------------------------------------------------------

def form_for(number, forms: list) -> str:
    """The form of a counted word that goes with `number`, by the loaded language's rule.  Fewer forms
    than the rule has are not an error a player should hear: the last one written stands in."""
    try:
        value = abs(float(re.sub(r'[\s\u00a0]', '', str(number)).replace(',', '.')))
    except ValueError:
        return forms[0]
    index = _plural[1](value, value == int(value))
    return forms[min(index, len(forms) - 1)]


# --- rules built from the table ----------------------------------------------------------------

def _escape_literal(text: str) -> str:
    """Escape the fixed part of a key, letting a colon be spaced either way: "X : buy" and "X: buy" are
    the same line to the player."""
    out = []
    for piece in re.split(r'(\s*:\s*)', text):
        out.append(r'\s*:\s*' if re.fullmatch(r'\s*:\s*', piece) else re.escape(piece))
    return ''.join(out)


def _template_regex(key: str):
    """The rule for a phrase with substitutions.

    Returns the pattern, how many substitutions there are and whether each substitution is a number.
    """
    key = key.replace('%%', '%')                        # %% prints one percent sign in the source
    parts = []
    numeric = []
    position = 0
    for match in _SPEC.finditer(key):
        parts.append(_escape_literal(key[position:match.start()]))
        spec = match.group(0)
        is_number = spec[-1] in 'diu'
        numeric.append(is_number)
        if is_number:
            parts.append(r'(-?\d[\d\s\u00a0]*)')
        elif match.start() == 0:
            # A substitution the line opens with does not reach back across ", ": the port glues a row's
            # title in front of its status with one ("Fuse, Grenade Launcher required, press Enter to go
            # to armory"), and "%s required, ..." swallowed the title with the weapon, so the translation
            # named the challenge as though it were the thing to buy.  Such a line now reaches
            # `_translate_segments`, which translates the head and the phrase behind it apart.
            parts.append(r'((?:(?!, ).)+?)')
        else:
            parts.append(r'(.+?)')
        position = match.end()
    parts.append(_escape_literal(key[position:]))
    return re.compile('^' + ''.join(parts) + '$'), len(numeric), numeric


def _foreign(text: str) -> bool:
    """Whether text already holds letters of a script other than the Latin the port is written in, which
    is the sign it has been translated already and must not be again."""
    return any(ch.isalpha() and ord(ch) > 0x24F for ch in text)


def _substitution(text: str) -> str:
    """Translate what the port put into a template - a key's name, a weapon, a card - and the words it
    joins them with ("Z or X"), which the language file carries as " or " and " and ".  A short name ("Z",
    "F") is not looked up on its own, but the word between two of them still is."""
    if _foreign(text):
        return text
    if re.search(r'[A-Za-z]{3,}', text):
        text = translate(text)
    for joint in (' or ', ' and '):
        target = _table.get(joint)
        if target and joint in text:
            text = target.join(translate(part) for part in text.split(joint))
    return text


def _make_rule(value: str, count: int, numeric: list):
    """The rule itself: put the substitutions where the translation has them, in its order or by their
    place in the English (`%2$s`), choose each word's form by the number it goes with, and translate
    whatever the port put in, since that is text too."""
    value = value.replace('%%', '%')
    tokens = []                                     # (kind, text or index or forms)
    position = 0
    sequential = 0
    for token in _VALUE_TOKEN.finditer(value):
        tokens.append(('text', value[position:token.start()]))
        if token.group(0).startswith('{'):
            tokens.append(('forms', token.group(2).split('|')))
        else:
            if token.group(1):
                index = int(token.group(1)) - 1
            else:
                index = sequential
                sequential += 1
            tokens.append(('sub', index))
        position = token.end()
    tokens.append(('text', value[position:]))
    first_number = next((item for kind, item in tokens if kind == 'sub'), None)

    def rule(match):
        filled = {}
        numbers = {}
        for index in range(count):
            raw = match.group(index + 1)
            if not raw:
                filled[index] = raw or ''
                continue
            digits = re.sub(r'[^\d]', '', raw)
            if digits and (numeric[index] or digits == raw.strip()):
                filled[index] = numbers[index] = digits
            else:
                raw = _substitution(raw)
                filled[index] = raw
                if _NUMBER.match(raw.strip()):
                    numbers[index] = raw.strip()
        out = []
        last = first_number
        for kind, item in tokens:
            if kind == 'text':
                out.append(item)
            elif kind == 'sub':
                out.append(filled.get(item, ''))
                last = item
            else:
                # with no number to go by, the last form - the one a language uses for "however many"
                out.append(form_for(numbers[last], item) if last in numbers else item[-1])
        return ''.join(out)
    return rule


def _build_rules(table: dict):
    """Rules from the table: the exact ones first, then the general ones.

    Order matters: a general rule for "%s diamonds" would otherwise catch "Buy for 100 diamonds" and
    translate only its last word.
    """
    rules = []
    for key, value in table.items():
        if not value or '%' not in key:
            continue
        regex, count, numeric = _template_regex(key)
        literal = len(_SPEC.sub('', key))
        specs = len(_SPEC.findall(key))
        rules.append((specs, -literal, regex, _make_rule(value, count, numeric)))
    rules.sort(key=lambda item: (item[0], item[1]))
    strong, weak = [], []
    for specs, neg_literal, regex, rule in rules:
        (strong if specs >= 2 or -neg_literal >= 12 else weak).append((regex, rule))
    return strong, weak


def _build_scan(table: dict):
    """Phrases to look for inside a long line the port glued together, longest first.

    Only phrases of several words: single words are caught by an exact match, and searching for them
    rewrites the case of a word in the middle of a sentence.
    """
    items = []
    for key, value in table.items():
        if not value or '%' in key or len(key) < 8 or ' ' not in key:
            continue
        pattern = re.compile(r'(?<![\w])%s(?![\w])' % re.escape(key))
        items.append((len(key), pattern, value))
    items.sort(key=lambda item: -item[0])
    return [(pattern, value) for _length, pattern, value in items]


def _apply_rules(text: str, rules):
    for regex, rule in rules:
        match = regex.match(text)
        if match:
            return rule(match)
    return None


#: the conjunctions `_SEGMENT_JOIN` splits on.  They are phrases in their own right - " and " is in the
#: table - so a line that can be split by one and translated no further would come back with only its
#: conjunction in the new language, every other word still English, which reads worse than leaving the
#: line alone.  A conjunction is substituted, but it does not by itself make a line translated.
_JOINS = (' and ', ' or ')


def _parts(text: str, splitter):
    """Translate piece by piece.  None when not one piece was found."""
    parts = splitter.split(text)
    if len(parts) == 1:
        return None                                      # nothing to split, and no recursion
    changed = False
    out = []
    for part in parts:
        if part in _JOINS:                               # glue, not a piece: see _JOINS
            out.append(_table.get(part, part))
            continue
        if part in _SEPARATORS:
            out.append(part)
            continue
        stripped = part.strip()
        found = _table.get(stripped) or _table.get(part)
        if found:
            changed = True
            out.append(found)
            continue
        replaced = _apply_rules(stripped, _rules) \
            or _apply_rules(stripped, _weak_rules)
        if replaced is not None:
            changed = True
            out.append(replaced)
            continue
        # A piece may hold more than one sentence ("Main Menu. Play"), and its parts may be joined by a
        # conjunction ("More Power Ups! and Glue Barrels"); the port assembles lines both ways.
        nested = None
        if splitter is not _SEGMENT_SENTENCE:
            nested = _parts(part, _SEGMENT_SENTENCE)
        if nested is None and splitter is not _SEGMENT_JOIN:
            nested = _parts(part, _SEGMENT_JOIN)
        if nested is not None:
            changed = True
            out.append(nested)
        else:
            out.append(part)
    return ''.join(out) if changed else None


def _translate_segments(text: str):
    """Translate by pieces: first a head that is itself a phrase, then by commas, then by sentences, then
    by the conjunctions the port joins with.

    The head is tried first because a weapon's description is full of commas of its own: the whole line is
    in the table while its pieces are not.
    """
    for match in _SEGMENT_COMMA.finditer(text):
        head = text[:match.start()].strip()
        if not head:
            continue
        translated = (_table.get(head) or _apply_rules(head, _rules))
        if translated:
            return translated + match.group(0) + translate(text[match.end():])
    # Then a tail that is a phrase with a separator of its own, which splitting at every separator would cut
    # in two: a row's title glued in front of "%s required, press Enter to go to armory".
    for match in _TAIL_COMMA.finditer(text):
        tail = text[match.end():].strip()
        if not _SEGMENT_COMMA.search(tail):
            continue
        translated = (_table.get(tail) or _apply_rules(tail, _rules))
        if translated:
            return translate(text[:match.start()]) + match.group(0) + translated
    by_comma = _parts(text, _SEGMENT_COMMA)
    if by_comma is not None:
        return by_comma
    by_sentence = _parts(text, _SEGMENT_SENTENCE)
    if by_sentence is not None:
        return by_sentence
    return _parts(text, _SEGMENT_JOIN)


def translate(text):
    """The line in the chosen language, or the line itself when there is no translation for it."""
    if not isinstance(text, str) or not text:
        return text
    if _language is None:
        follow()
    if not _table:
        return text                                      # English, or no language file
    exact = _table.get(text)
    if exact:
        if '{' in exact and _SPEC.search(text):
            # A template asked for with its gaps still empty, to be filled in by whoever asked: there is no
            # number yet to choose a form by, so each word takes its "however many" form, and no brace is
            # ever read out.
            return _FORMS.sub(lambda m: m.group(1).split('|')[-1], exact)
        return exact
    if '\n' in text:
        # Multi-line text: the whole thing first (the port glues paragraphs and captions), then line by
        # line, which is how the credits - a role or a name on each line - are translated.
        flat_lines = ' '.join(text.split())
        found = _table.get(flat_lines)
        if found:
            return found
        lines = text.split('\n')
        translated = [translate(line) for line in lines]
        if translated != lines:
            return '\n'.join(translated)
    flat = ' '.join(text.split())                        # line breaks are for the label, not for speech
    if flat != text:
        found = _table.get(flat)
        if found:
            return found
    replaced = _apply_rules(flat, _rules)
    if replaced is not None:
        return replaced
    by_parts = _translate_segments(flat)
    if by_parts is not None:
        return by_parts
    replaced = _apply_rules(flat, _weak_rules)
    if replaced is not None:
        return replaced
    # Last pass: a long line with an English phrase somewhere inside text that is already translated.
    if re.search(r'[A-Za-z]{4,}', flat):
        scanned = flat
        for pattern, value in _scan:
            scanned = pattern.sub(value.replace('\\', '\\\\'), scanned)
        if scanned != flat:
            return scanned
    # Labels the port writes in capitals, which the table holds in the ordinary case.
    upper = _lower.get(flat.lower())
    if upper:
        return upper
    return text
