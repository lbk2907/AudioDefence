"""A very small stand-in for pygame, for the Android build.

The game's screens are written against pygame's key codes and event objects.  Android has no pygame, and
the game does not draw anything, so this module supplies only what the screens read: the key and modifier
constants, the event types, ``event.Event``, and ``key.name`` / ``key.key_code`` (used to store and speak the
key bindings).  The values are SDL 2's, like real pygame's, so a saved key map means the same thing.
"""
import types

error = RuntimeError

KEYDOWN, KEYUP, MOUSEMOTION = 768, 769, 1024
QUIT, WINDOWFOCUSLOST = 256, 519
JOYAXISMOTION, JOYBALLMOTION, JOYHATMOTION, JOYBUTTONDOWN, JOYBUTTONUP = 1536, 1537, 1538, 1539, 1540
JOYDEVICEADDED, JOYDEVICEREMOVED = 1541, 1542
CONTROLLERAXISMOTION, CONTROLLERBUTTONDOWN, CONTROLLERBUTTONUP = 1616, 1617, 1618
CONTROLLERDEVICEADDED, CONTROLLERDEVICEREMOVED, CONTROLLERDEVICEREMAPPED = 1619, 1620, 1621

KMOD_SHIFT, KMOD_CTRL, KMOD_ALT, KMOD_GUI = 3, 192, 768, 3072
KMOD_LSHIFT, KMOD_RSHIFT, KMOD_LCTRL, KMOD_RCTRL = 1, 2, 64, 128
KMOD_LALT, KMOD_RALT, KMOD_LGUI, KMOD_RGUI = 256, 512, 1024, 2048

_SCANCODE_MASK = 1 << 30
_NAMES = {}


def _key(const, code, name):
    globals()[const] = code
    _NAMES[code] = name


for _i in range(26):
    _key('K_' + chr(97 + _i), 97 + _i, chr(97 + _i))
for _i in range(10):
    _key('K_%d' % _i, 48 + _i, str(_i))
_key('K_RETURN', 13, 'return')
_key('K_ESCAPE', 27, 'escape')
_key('K_BACKSPACE', 8, 'backspace')
_key('K_TAB', 9, 'tab')
_key('K_SPACE', 32, 'space')
_key('K_DELETE', 127, 'delete')
_key('K_RIGHT', _SCANCODE_MASK | 79, 'right')
_key('K_LEFT', _SCANCODE_MASK | 80, 'left')
_key('K_DOWN', _SCANCODE_MASK | 81, 'down')
_key('K_UP', _SCANCODE_MASK | 82, 'up')
_key('K_HOME', _SCANCODE_MASK | 74, 'home')
_key('K_PAGEUP', _SCANCODE_MASK | 75, 'page up')
_key('K_END', _SCANCODE_MASK | 77, 'end')
_key('K_PAGEDOWN', _SCANCODE_MASK | 78, 'page down')
_key('K_KP_ENTER', _SCANCODE_MASK | 88, 'enter')
_key('K_LCTRL', _SCANCODE_MASK | 224, 'left ctrl')
_key('K_LSHIFT', _SCANCODE_MASK | 225, 'left shift')
_key('K_LALT', _SCANCODE_MASK | 226, 'left alt')
_key('K_RCTRL', _SCANCODE_MASK | 228, 'right ctrl')
_key('K_RSHIFT', _SCANCODE_MASK | 229, 'right shift')
_key('K_RALT', _SCANCODE_MASK | 230, 'right alt')
_key('K_LGUI', _SCANCODE_MASK | 227, 'left meta')
_key('K_RGUI', _SCANCODE_MASK | 231, 'right meta')
_key('K_CAPSLOCK', _SCANCODE_MASK | 57, 'caps lock')
_key('K_NUMLOCK', _SCANCODE_MASK | 83, 'numlock')
_key('K_INSERT', _SCANCODE_MASK | 73, 'insert')
# PORT ADDITION (user request, 2026-10-05): the rest of a keyboard plugged into the phone, so that any of its
# keys can be bound in Settings > Keyboard and named as the desktop names it
for _i in range(1, 13):
    _key('K_F%d' % _i, _SCANCODE_MASK | (57 + _i), 'f%d' % _i)
for _const, _char in (('MINUS', '-'), ('EQUALS', '='), ('LEFTBRACKET', '['), ('RIGHTBRACKET', ']'),
                      ('BACKSLASH', '\\'), ('SEMICOLON', ';'), ('QUOTE', "'"), ('BACKQUOTE', '`'),
                      ('COMMA', ','), ('PERIOD', '.'), ('SLASH', '/')):
    _key('K_' + _const, ord(_char), _char)
for _i in range(1, 10):
    _key('K_KP%d' % _i, _SCANCODE_MASK | (88 + _i), '[%d]' % _i)
_key('K_KP0', _SCANCODE_MASK | 98, '[0]')
for _const, _scan, _name in (('DIVIDE', 84, '[/]'), ('MULTIPLY', 85, '[*]'), ('MINUS', 86, '[-]'),
                             ('PLUS', 87, '[+]'), ('PERIOD', 99, '[.]')):
    _key('K_KP_' + _const, _SCANCODE_MASK | _scan, _name)
_key('K_PRINTSCREEN', _SCANCODE_MASK | 70, 'print screen')
_key('K_SCROLLLOCK', _SCANCODE_MASK | 71, 'scroll lock')
_key('K_PAUSE', _SCANCODE_MASK | 72, 'pause')
_key('K_MENU', _SCANCODE_MASK | 118, 'menu')

# the controller buttons the desktop port's pad module names: SDL's numbers, which the phone's controllers are
# given in too (Bridge.padKeyEvent, _sdl2/controller.py)
for _n, _v in enumerate(('A', 'B', 'X', 'Y', 'BACK', 'GUIDE', 'START', 'LEFTSTICK', 'RIGHTSTICK',
                         'LEFTSHOULDER', 'RIGHTSHOULDER', 'DPAD_UP', 'DPAD_DOWN', 'DPAD_LEFT', 'DPAD_RIGHT')):
    globals()['CONTROLLER_BUTTON_' + _v] = _n


class _Event:
    def __init__(self, type, **attrs):
        self.type = type
        self.__dict__.update(attrs)

    def __repr__(self):
        return '<Event %r>' % self.__dict__


event = types.SimpleNamespace(Event=_Event, get=lambda: [])


def _name(code):
    return _NAMES.get(code, '')


def _code(name):
    for code, n in _NAMES.items():
        if n == name:
            return code
    raise ValueError('unknown key name %r' % name)


key = types.SimpleNamespace(name=_name, key_code=_code)
scrap = types.SimpleNamespace(put_text=lambda text: None)


def init():
    pass


def quit():
    pass
