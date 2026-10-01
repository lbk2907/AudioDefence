"""PORT ADDITION (Android build): the door to the Java half of the app.

Everything the phone has to do that Python cannot - sound output, decoding the .m4a files, speech, the
touch screen - is done by ``com.audiodefence.Bridge``.  ``bridge()`` returns it.  With
AUDIODEFENCE_FAKE_ANDROID=1 (a PC, for testing) a stand-in from fakebridge.py answers instead.
"""
from __future__ import annotations

import os

_bridge = None


def bridge():
    global _bridge
    if _bridge is None:
        if os.environ.get('AUDIODEFENCE_FAKE_ANDROID') == '1':
            from .fakebridge import FakeBridge
            _bridge = FakeBridge()
        else:
            from java import jclass                      # Chaquopy
            _bridge = jclass('com.audiodefence.Bridge').get()
    return _bridge
