"""PORT ADDITION (Android build): four modules of this package have a stand-in on the phone.

``speech``, ``pad``, ``updater`` and ``haptics`` speak to NVDA and SAPI 5, SDL's controllers, GitHub's
releases and a controller's motors.  The Android app has none of those, so each has an ``_android`` module
beside it - the phone's text-to-speech through the Java bridge, and no controllers, no updating and no
vibration yet - and on the phone that module is the one every ``from ..platform.speech import ...`` gets.
The desktop modules are not imported there at all, and on Windows and the Mac nothing here runs.
"""
from . import host as _host

if _host.ANDROID:
    import importlib as _importlib
    import sys as _sys

    for _name in ('speech', 'pad', 'updater', 'haptics'):
        _module = _importlib.import_module('%s.%s_android' % (__name__, _name))
        _sys.modules['%s.%s' % (__name__, _name)] = _module
        globals()[_name] = _module
