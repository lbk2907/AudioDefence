"""PORT ADDITION (Android build): game controllers on the phone - not supported yet.  On the phone this
module is `platform.pad` (see platform/__init__.py), and keeps the names the rest of the game imports."""
from __future__ import annotations

PAD_DEFAULTS: dict = {}
PAD_LABELS: dict = {}
NAMES: dict = {}


def set_hints() -> None:
    pass


def family(model) -> str:
    return 'generic'


def button_words(action, mode=None):
    return None


#: PORT ADDITION (user request, 2026-10-05): a keyboard plugged into the phone is being used - its last input
#: was a key, not a touch (android_main.TouchInput) - so the hints name its keys, as they are written
keyboard_in_use = False

#: the desktop's key names, as the phone's gestures that do the same in a menu (android_main.TouchInput)
_TOUCH_WORDS = (
    (r'Shift plus Enter|Shift\+Enter|Shift Enter', 'touch and hold'),
    (r'\bPress Enter\b', 'Double tap'),
    (r'\bpress Enter\b', 'double tap'),
    (r'\bEnter\b', 'double tap'),
    (r'\bEscape\b', 'two-finger tap'),
)


def menu_words(text, *a, **k):
    """A label or hint as it should be spoken on the phone.

    FIX: this used to answer None for everything.  Every row marked `label_key_words` (the challenge list,
    the tarot cards, the armory) then lost its whole label, and every hint was read as "None".  The text is
    now given back, with the keyboard's keys named as the gestures that do the same on a touch screen."""
    if not text or keyboard_in_use:
        return text
    import re
    text = str(text)
    for pattern, words in _TOUCH_WORDS:
        text = re.sub(pattern, words, text)
    return text


def input_name(name, kind=None) -> str:
    return str(name)


class PadMap:
    @classmethod
    def for_model(cls, model):
        return cls()

    def names(self, action):
        return ()

    def text(self, action):
        return ''

    def action_for(self, name):
        return None


class Pads:
    _shared = None

    @classmethod
    def shared(cls) -> 'Pads':
        if cls._shared is None:
            cls._shared = Pads()
        return cls._shared

    def __init__(self):
        self.pads: dict = {}
        self.dualsenses: dict = {}
        self.changed = None
        self.speak = None

    def start(self):
        pass

    def stop(self):
        pass

    def handle(self, event):
        return None

    def connected_models(self):
        return []

    def editing_model(self):
        return None

    def padmap_for(self, source):
        return PadMap()

    def turn(self):
        return 0

    def shaken(self):
        return False

    def can_shake(self, model):
        return False

    def set_triggers(self, *a, **k):
        pass
