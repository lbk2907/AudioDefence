"""Ready this computer to build the Android app: the part of "Building the app", under On Android in the
README, that a script can do.

    py tools\\android_setup.py           check the tools, set ANDROID_HOME, fetch the SDK's parts, first build
    py tools\\android_setup.py --phone   put the newest APK in dist onto a phone on a USB cable

Installing Python 3.13, Java, the Android command-line tools and Gradle stays by hand - the README says where
each comes from - and this names whichever is missing, with compiler.py's own checks.  The rest it does once;
run again, it skips what is done and says so:

1. checks the tools that are installed by hand;
2. sets ANDROID_HOME, when it is not set and the command-line tools are unzipped in C:\\Android;
3. accepts the SDK's licences and fetches the parts the app is built with, the ones that are not there;
4. runs a first build, which fetches Gradle's plugins, Chaquopy, Python for Android and numpy.

The signing key is tools/android_keys.py's.  A variable is set with setx, for this user alone - never the
system's, nor the Path - and a command prompt opened after that sees it.  On the Mac it says the line to add
to ~/.zprofile instead.
"""
from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import compiler                                         # noqa: E402  the Android build's own checks
from audiodefence.platform import host                  # noqa: E402

say = compiler.say
#: where the README has the command-line tools unzipped, and so what ANDROID_HOME names
DEFAULT_SDK = compiler.ANDROID_TOOLS
#: what the SDK needs beyond its command-line tools, each as the folder it makes there; joined with ';' it
#: is sdkmanager's name for it
SDK_PARTS = (('platforms', compiler.ANDROID_PLATFORM), ('build-tools', '35.0.0'), ('platform-tools',))
EXE = '.exe' if host.WINDOWS else ''
README = 'Building the app, under On Android in the README'


def saved(name: str) -> str:
    """A variable as this user has it.  One set with setx since this command prompt opened is not in its
    environment yet, and is still the one to go by: so it is read from the user's settings too, and taken
    into this run's environment, where compiler.py's checks look."""
    value = os.environ.get(name, '').strip()
    if value or not host.WINDOWS:
        return value
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
            value = winreg.ExpandEnvironmentStrings(str(winreg.QueryValueEx(key, name)[0])).strip()
    except OSError:
        return ''
    if value:
        os.environ[name] = value
    return value


def remember(name: str, value: str) -> None:
    """Set a variable for this user for good, and for the rest of this run."""
    os.environ[name] = value
    if not host.WINDOWS:
        say('  Add this line to the file .zprofile in your home folder, then open a new Terminal:')
        say('  export %s="%s"' % (name, value))
        return
    try:
        done = subprocess.run(['setx', name, value], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL).returncode == 0
    except OSError:
        done = False
    if done:
        say('  %s is now %s, for your Windows user. A command prompt opened from now on sees it.' % (name, value))
    else:
        say('  Windows would not save %s. Type this yourself, then open a new command prompt:' % name)
        say('  setx %s "%s"' % (name, value))


def sdkmanager_path() -> str:
    """sdkmanager, in the SDK ANDROID_HOME names, or where the README unzips it."""
    return os.path.join(saved('ANDROID_HOME') or DEFAULT_SDK, 'cmdline-tools', 'latest', 'bin',
                        'sdkmanager' + ('.bat' if host.WINDOWS else ''))


def run_sdkmanager(sdkmanager: str, args: list, answers: str | None = None) -> int:
    """Run sdkmanager with its output on the screen.  "platforms;android-35" needs no quotes: sdkmanager.bat
    hands its whole command line (%*) to Java as it is, and only a space would split it."""
    try:
        return subprocess.run([sdkmanager] + args, input=answers, text=True,
                              stdin=None if answers else subprocess.DEVNULL).returncode
    except OSError as error:
        say('  sdkmanager would not start: %s' % error)
        return 1


# --- the steps -------------------------------------------------------------------------------------------

def check_tools(ready: list, left: list) -> tuple[str, str]:
    """Step 1.  Returns the java found and sdkmanager, or '' for each that is not there."""
    say('Step 1: the tools that are installed by hand.')

    def missing(what: str, step: int, why: str = '') -> None:
        say('  %s: %s. Install it as step %d of %s says.' % (what, why or 'not found', step, README))
        left.append('install %s, step %d in the README' % (what, step))

    python = 'Python %s' % compiler.ANDROID_PYTHON
    found = compiler.android_python()
    if found:
        say('  %s: found, at %s.' % (python, found))
        ready.append(python)
    else:
        missing(python, 1)
    java = compiler.find_java()
    major = compiler.java_major(java) if java else 0
    low, high = compiler.JAVA_RANGE
    if not java:
        home = os.environ.get('JAVA_HOME', '').strip()
        missing('Java 21', 2, 'JAVA_HOME names %s, which has no Java in it' % home if home else '')
    elif major and not low <= major <= high:
        missing('Java 21', 2, 'Java %d is there, and the build needs %d to %d' % (major, low, high))
    else:
        say('  Java %s: found, at %s.' % (major or 'of a version it would not say', java))
        ready.append('Java')
    sdkmanager = sdkmanager_path()
    if os.path.isfile(sdkmanager):
        say('  The Android command-line tools: found, at %s.' % os.path.dirname(sdkmanager))
        ready.append('the Android command-line tools')
    else:
        missing('the Android command-line tools', 3, 'not found at %s' % sdkmanager)
        sdkmanager = ''
    gradle = compiler.find_gradle()
    if gradle:
        say('  Gradle: found, at %s.' % gradle)
        ready.append('Gradle')
    else:
        missing('Gradle 8.13', 4)
    return java, sdkmanager


def set_android_home(sdkmanager: str, ready: list, left: list) -> str:
    """Step 2.  Returns the SDK's folder, or '' while there is none."""
    say('Step 2: ANDROID_HOME, which tells the build where the Android SDK is.')
    sdk = saved('ANDROID_HOME')
    if sdk:
        say('  Already set, to %s. Nothing to do.' % sdk)
    elif not sdkmanager:
        say('  Not set yet: that waits for the command-line tools, above.')
        left.append('set ANDROID_HOME, by running this again once the command-line tools are unzipped')
        return ''
    else:
        sdk = DEFAULT_SDK
        remember('ANDROID_HOME', sdk)
    ready.append('ANDROID_HOME')
    return sdk


def fetch_sdk_parts(sdk: str, sdkmanager: str, java: str, ready: list, left: list) -> None:
    """Step 3."""
    say('Step 3: the parts of the Android SDK the app is built with.')
    absent = [';'.join(part) for part in SDK_PARTS if not (sdk and os.path.isdir(os.path.join(sdk, *part)))]
    if not absent:
        say('  All there: %s. Nothing to do.' % ', '.join(';'.join(part) for part in SDK_PARTS))
        ready.append('the SDK parts')
        return
    if not (sdk and sdkmanager and java):
        say('  Not fetched yet: that waits for %s, above.'
            % ('Java' if sdk and sdkmanager else 'the command-line tools'))
        left.append('fetch the SDK parts, by running this again once the tools above are in')
        return
    say('  Accepting the licences, then fetching %s. What follows is sdkmanager speaking.' % ', '.join(absent))
    run_sdkmanager(sdkmanager, ['--licenses'], answers='y\n' * 50)
    run_sdkmanager(sdkmanager, absent)
    still = [';'.join(part) for part in SDK_PARTS if not os.path.isdir(os.path.join(sdk, *part))]
    if still:
        say('  Still missing: %s. sdkmanager says why, above.' % ', '.join(still))
        left.append('fetch %s: sdkmanager failed, run this again' % ', '.join(still))
    else:
        say('  Fetched.')
        ready.append('the SDK parts')


def first_build(ready: list, left: list) -> None:
    """Step 4: a test build, for what the first build fetches, so that the compiler's builds take minutes."""
    say("Step 4: the first build, which fetches Gradle's plugins, Chaquopy, Python for Android and numpy.")
    if compiler.android_fetched():
        say('  Already fetched. Nothing to do.')
        ready.append('the first build')
        return
    if left:
        say('  Not run yet: that waits for what is missing above.')
        left.append('the first build, by running this again once the rest is ready')
        return
    say('  Building. It takes ten to twenty minutes the first time. What follows is Gradle speaking.')
    try:
        status = subprocess.run(compiler.gradle_command('assembleDebug'), cwd=compiler.ANDROID,
                                stdin=subprocess.DEVNULL).returncode
    except OSError as error:
        say('  Gradle would not start: %s' % error)
        status = 1
    if status:
        say('  The build failed; what Gradle said is above.')
        left.append('the first build: it failed, see what Gradle said, then run this again')
    else:
        say('  Built. From now on a build takes a minute or two.')
        ready.append('the first build')


def install_on_phone() -> int:
    """--phone: put the newest APK in dist onto the phone on the USB cable, a release before a test build."""
    say('Putting the app on the phone.')
    adb = os.path.join(saved('ANDROID_HOME') or DEFAULT_SDK, 'platform-tools', 'adb' + EXE)
    if not os.path.isfile(adb):
        say('  adb is not there. Run %s on its own first: it fetches it.' % compiler.SETUP)
        return 1
    apks = glob.glob(os.path.join(ROOT, 'dist', 'AudioDefence-Android-*.apk'))
    if not apks:
        say('  There is no app in dist to install. Build it first: py compiler.py --android.')
        return 1
    releases = [apk for apk in apks if not apk.endswith('-TEST.apk')]
    apk = max(releases or apks, key=os.path.getmtime)
    try:
        listing = subprocess.run([adb, 'devices'], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                 timeout=60).stdout
    except (OSError, subprocess.SubprocessError) as error:
        say('  adb would not start: %s' % error)
        return 1
    states = [line.split('\t')[1].strip() for line in listing.splitlines() if '\t' in line]
    phones = states.count('device')
    if phones > 1:
        say('  %d phones are connected. Unplug all but one, and run this again.' % phones)
        return 1
    if not phones:
        if 'unauthorized' in states:
            say('  The phone is connected, but has not allowed this computer yet. Unlock it, allow USB '
                'debugging for this computer when it asks, and run this again.')
        else:
            say('  No phone can be seen. On the phone, once:')
            say('  In Settings, open About phone, and tap Build number seven times. That turns on Developer '
                'options.')
            say('  In Developer options, which are in Settings, often under System, turn on USB debugging.')
            say('  Then connect the phone to this computer with a USB cable, allow this computer when the '
                'phone asks, and run this again.')
        return 1
    say('  Installing %s. What follows is adb speaking.' % os.path.basename(apk))
    if subprocess.run([adb, 'install', '-r', apk], stdin=subprocess.DEVNULL).returncode == 0:
        say('  Installed, keeping any progress the app had.')
        return 0
    say('  adb could not install it; what it said is above. If it says the signatures do not match, the app '
        'on the phone was signed with another key: uninstall it there first, which loses its progress.')
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='android_setup.py',
                                     description='ready this computer to build the Android app')
    parser.add_argument('--phone', action='store_true',
                        help='put the newest APK in dist onto a phone on a USB cable, and nothing else')
    args = parser.parse_args(argv)
    if args.phone:
        return install_on_phone()
    ready, left = [], []
    java, sdkmanager = check_tools(ready, left)
    sdk = set_android_home(sdkmanager, ready, left)
    fetch_sdk_parts(sdk, sdkmanager, java, ready, left)
    first_build(ready, left)
    saved('AD_KEYSTORE')                                # one chosen since this prompt opened counts
    key, _why = compiler.remembered_key()
    say()
    say('Summary.')
    say('Ready: %s.' % (', '.join(ready) or 'nothing yet'))
    for line in left:
        say('Left to do: %s.' % line)
    if not key:
        say('Left to do: your signing key. Make it with %s.' % compiler.KEY_TOOL)
    if not left:
        say('Everything the build needs is here. Open a new command prompt, then build with the compiler.')
    return 1 if left else 0


if __name__ == '__main__':
    status = main()
    if len(sys.argv) == 1 and sys.stdin.isatty():       # double-clicked: wait, so the summary can be heard
        try:
            input('Finished. Press Enter to close this window.')
        except EOFError:
            pass
    sys.exit(status)
