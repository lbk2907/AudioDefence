"""The keys the Android app's releases are signed with: make one, see which there are, choose the one the
compiler offers.

    py tools\\android_keys.py

It lists the keys in C:\\Android\\keys and says which is the default - the one AD_KEYSTORE names, which the
compiler offers when it asks where the key is - then offers:

1. Make a new key.  It asks for a name (Enter alone for "release") and makes C:\\Android\\keys\\<name>.p12
   with the JDK's keytool, with the store type, alias and passwords android/app/build.gradle signs with when
   nothing else is given (read from it).  It never overwrites a file.  With no default key, the new one
   becomes it.
2. Choose the default key: one of those, or a key file somewhere else, such as one you were given.

AD_KEYSTORE is set with setx, for this user alone; on the Mac it says the line to add to ~/.zprofile.
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import android_setup as setup                           # noqa: E402  saved, remember; and compiler with it

compiler = setup.compiler
say = compiler.say
DEFAULT_NAME = 'release'


def keys() -> list:
    return sorted(glob.glob(os.path.join(compiler.KEYS, '*.p12')), key=str.lower)


def signing() -> dict:
    """What android/app/build.gradle opens a key with when no AD_KEY_... variable says otherwise: its store
    type, and the defaults of AD_KEY_ALIAS, AD_KEYSTORE_PASSWORD and AD_KEY_PASSWORD.  Read from it, so a
    key made here is always one the build can open."""
    with open(os.path.join(compiler.ANDROID, 'app', 'build.gradle'), encoding='utf-8') as fh:
        text = fh.read()
    found = dict(re.findall(r"getenv\('(AD_KEY_ALIAS|AD_KEYSTORE_PASSWORD|AD_KEY_PASSWORD)'\)\s*\?:\s*'([^']*)'",
                            text))
    store = re.search(r"\bstoreType\s+'([^']*)'", text)
    if store:
        found['storeType'] = store.group(1)
    return found if len(found) == 4 else {}


def advice(path: str) -> None:
    say('The key is %s. Back it up somewhere safe and private, never in the repository, and hand it on with '
        'the project.' % path)
    say('Every release has to be signed with this same key, or phones will not install it over the one they '
        'have.')
    say("Phones that have Erick's earlier builds can only update with his key: ask him for it and choose it "
        'here, or install yours fresh on them.')


def make() -> int:
    try:
        name = input('Name for the new key, then Enter. Enter alone names it %s: ' % DEFAULT_NAME).strip()
    except EOFError:
        name = ''
    name = re.sub(r'\.p12$', '', name, flags=re.IGNORECASE).strip() or DEFAULT_NAME
    if re.search(r'[\\/:*?"<>|]', name):
        say('A name cannot have any of these in it: \\ / : * ? " < > |. Run this again with another.')
        return 1
    path = os.path.join(compiler.KEYS, name + '.p12')
    if os.path.exists(path):
        say('There is already a key called %s, and a key is never overwritten. Run this again and give '
            'another name.' % name)
        return 1
    java = compiler.find_java()
    keytool = os.path.join(os.path.dirname(java), 'keytool' + setup.EXE) if java else ''
    if not os.path.isfile(keytool):
        say('There is no keytool: it comes with Java, step 2 of %s.' % setup.README)
        return 1
    sign = signing()
    if not sign:
        say('android/app/build.gradle no longer says the store type, alias and passwords it signs with, in '
            'the form this reads, so no key was made.')
        return 1
    os.makedirs(compiler.KEYS, exist_ok=True)
    say('Making the key %s.' % path)
    try:
        status = subprocess.run(
            [keytool, '-genkeypair', '-keystore', path, '-storetype', sign['storeType'],
             '-alias', sign['AD_KEY_ALIAS'], '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000',
             '-storepass', sign['AD_KEYSTORE_PASSWORD'], '-keypass', sign['AD_KEY_PASSWORD'],
             '-dname', 'CN=Audio Defence'],
            stdin=subprocess.DEVNULL).returncode
    except OSError as error:
        say('keytool would not start: %s' % error)
        return 1
    if status or not os.path.isfile(path):
        say('keytool failed; what it said is above.')
        return 1
    say('Made.')
    current, _why = compiler.remembered_key()
    if os.environ.get('AD_KEYSTORE', '').strip() and current:
        say('The default is still %s. To use the new key instead, run this again and choose it.' % current)
    else:
        setup.remember('AD_KEYSTORE', path)
        say('It is the default key now.')
    advice(path)
    return 0


def choose(found: list) -> int:
    try:
        typed = input('Type the number of the key, or the path to a key file somewhere else, then Enter: ')
    except EOFError:
        typed = ''
    typed = typed.strip().strip('"')
    if typed.isdigit() and 1 <= int(typed) <= len(found):
        path = found[int(typed) - 1]
    elif typed and os.path.isfile(typed):
        path = os.path.abspath(typed)
    else:
        say('There is no key %s. Nothing was changed.' % (typed or 'chosen'))
        return 1
    setup.remember('AD_KEYSTORE', path)
    say('The default key is %s.' % path)
    if os.path.normcase(os.path.dirname(path)) != os.path.normcase(compiler.KEYS):
        say('If it was made with another alias or other passwords than the ones this tool uses, set them in '
            'AD_KEY_ALIAS, AD_KEYSTORE_PASSWORD and AD_KEY_PASSWORD too: see A release, in the README.')
    advice(path)
    return 0


def main() -> int:
    default = setup.saved('AD_KEYSTORE')
    found = keys()
    say('Signing keys, in %s.' % compiler.KEYS)
    if not found:
        say('There are none yet.')
    for number, path in enumerate(found, 1):
        same = default and os.path.normcase(path) == os.path.normcase(os.path.abspath(default))
        say('  %d. %s%s' % (number, os.path.basename(path), ', the default' if same else ''))
    if default and not any(os.path.normcase(p) == os.path.normcase(os.path.abspath(default)) for p in found):
        say('The default, AD_KEYSTORE, is %s%s.' % (default, '' if os.path.isfile(default) else
                                                    ', which is not there'))
    elif not default:
        say('None is the default: AD_KEYSTORE is not set.')
    say()
    say('  1. Make a new key')
    say('  2. Choose the default key')
    say('  0. Quit')
    try:
        choice = input('Type a number and press Enter: ').strip()
    except EOFError:
        choice = '0'
    if choice == '1':
        return make()
    if choice == '2':
        return choose(found)
    return 0


if __name__ == '__main__':
    status = main()
    if sys.stdin.isatty():                              # double-clicked: wait, so the end can be heard
        try:
            input('Finished. Press Enter to close this window.')
        except EOFError:
            pass
    sys.exit(status)
