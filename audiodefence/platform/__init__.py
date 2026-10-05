"""PORT ADDITION (Android build): two modules of this package have a stand-in on the phone.

``speech`` and ``updater`` speak to NVDA and SAPI 5 and to GitHub's releases.  The Android app has neither,
so each has an ``_android`` module beside it - the phone's text-to-speech through the Java bridge, and the
phone's own updating - and on the phone that module is the one every ``from ..platform.speech import ...``
gets.  The desktop modules are not imported there at all, and on Windows and the Mac nothing here runs.
``haptics`` and ``pad`` had one each until 2026-10-05, which did nothing: the phone uses the desktop's now,
which vibrate the phone as well (``Haptics._phone``) and take Android's controllers (pad.py).
"""
from . import host as _host

if _host.ANDROID:
    import importlib as _importlib
    import sys as _sys

    for _name in ('speech', 'updater'):
        _module = _importlib.import_module('%s.%s_android' % (__name__, _name))
        _sys.modules['%s.%s' % (__name__, _name)] = _module
        globals()[_name] = _module
