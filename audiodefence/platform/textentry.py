"""PORT ADDITION (user request): the system's own box for typing a line of text.

A phone has a keyboard the system draws and the original never asks for a word, so there is no method in
the binary this departs from.  The port needs typing for the Challenge maker - a challenge somebody made
should be called what they want it called - and `ui.host.TextEntryScreen` was the first answer: a screen of
the game's own that reads every character back as it is typed.  It works, but it is a text field the port
drew itself, so none of what a keyboard can actually do is in it.  There is no caret, no selection, no
Control plus A, no Control plus C or V, no word at a time with Control plus the arrows, and the only way to
take back a word is one Backspace at a time.

So the typing is handed to the system, the way choosing a sound file already is (`filedialog.py`).  Windows
gets a real `EDIT` control in a window of its own, which is the same control Explorer renames a file in:
every editing key a player already knows works because the system implements it, and a screen reader reads
it as an edit field rather than as a line of speech the game decided to say.  The Mac gets AppleScript's
`display dialog` with a `default answer`, which is Finder's own text field for the same reasons.

Two of the keys are taken before the control sees them, because the control does not do them:

* **Control plus A** selects everything.  The `EDIT` control has done this itself since Windows 2000, but
  only as a courtesy a dialog manager is free to swallow first, and "select it all and type over it" is the
  one thing this box is most often opened to do.  Doing it here means it is never the dialog's to lose.
* **Control plus Backspace** takes back a word.  The control's own answer is to insert character 0x7F - a
  box in the middle of your title - which is a thirty-year-old loose end in `user32` and not something to
  pass on to a player.

Enter and Escape are taken in the same place and for a plainer reason: they have to mean here what they
mean on every other screen in the game.

The box is modal: the game's window is disabled while it is open and the game carries on when it closes,
as it does for the file dialog.  Nothing here raises.  A box that cannot be shown at all is remembered
(`_broken`), `available()` answers False from then on, and the caller falls back to the game's own typing
screen - so a Windows that refuses to make the window is a port that types the old way, not one that
cannot name a challenge.
"""
from __future__ import annotations

import ctypes
import logging
import subprocess

from . import host

log = logging.getLogger('textentry')

#: Set when a box could not be shown.  One failure is enough: whatever stopped the window being made will
#: stop the next one too, and a player who has to watch it fail before every name is worse off than one
#: typing on the game's own screen.
_broken = False


def available() -> bool:
    """Whether there is a system box to type in.  False on anything but Windows and the Mac, and False
    once one has failed - `ui.host.ask_for_text` reads this and falls back to `TextEntryScreen`."""
    return bool(host.WINDOWS or host.MAC) and not _broken


def ask_for_text(title: str, prompt: str, value: str = '', max_length: int = 48):
    """What was typed, or None if it was cancelled.

    `title` is the window's own title, `prompt` the line above the field, and `value` what the field starts
    with - selected, so the first key typed replaces it, which is what a rename box does everywhere else.
    An empty answer comes back as an empty string: whether a name may be empty is the caller's to say, not
    this module's.

    The answer is cut to `max_length` here rather than left to the field.  `EM_LIMITTEXT` stops a player
    typing or pasting past it, which is what it is for, but it is not a promise about the string - and
    AppleScript's field has no limit to set at all - so the length the caller asked for is kept here, where
    both platforms pass through.
    """
    global _broken
    if not available():
        return None
    try:
        typed = _mac_ask(title, prompt, value) if host.MAC else \
            _windows_ask(title, prompt, value, max_length)
        return None if typed is None else typed[:max(1, int(max_length))]
    except Exception:
        log.exception("the typing box could not be shown; typing goes back to the game's own screen")
        _broken = True
        return None


# ================================================================================= the Mac: display dialog
def _mac_ask(title: str, prompt: str, value: str):
    """Finder's own text field, through AppleScript.  `display dialog` raises when it is cancelled, which
    osascript reports as a non-zero exit - read here as "nothing was typed", exactly as `choose file` is.

    AppleScript has no length limit to set on the field, so the Mac is the one place where too long a name
    is cut afterwards rather than refused as it is typed.  `ask_for_text` is where the cut happens.
    """
    script = ('display dialog "%s" with title "%s" default answer "%s" '
              'buttons {"Cancel", "OK"} default button "OK" cancel button "Cancel"\n'
              'text returned of result'
              % (_applescript(prompt), _applescript(title), _applescript(value)))
    try:
        done = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=1800)
    except (OSError, subprocess.SubprocessError):
        log.exception('the typing box could not be shown')
        return None
    if done.returncode != 0:
        return None                                       # Cancel, or Escape
    return (done.stdout or '').rstrip('\n')


def _applescript(text: str) -> str:
    """A Python string as an AppleScript one: the backslash first, then the quote it would end early."""
    return str(text).replace('\\', '\\\\').replace('"', '\\"')


# ====================================================================== Windows: a window with an EDIT in
_WS_CHILD = 0x40000000
_WS_VISIBLE = 0x10000000
_WS_TABSTOP = 0x00010000
_WS_BORDER = 0x00800000
_WS_CAPTION = 0x00C00000
_WS_SYSMENU = 0x00080000
_WS_EX_DLGMODALFRAME = 0x00000001
_WS_EX_CONTROLPARENT = 0x00010000
_ES_AUTOHSCROLL = 0x0080
_BS_DEFPUSHBUTTON = 0x0001

_WM_DESTROY = 0x0002
_WM_CLOSE = 0x0010
_WM_SETFOCUS = 0x0007
_WM_SETFONT = 0x0030
_WM_COMMAND = 0x0111
_WM_KEYDOWN = 0x0100
_WM_CLEAR = 0x0303
_EM_GETSEL = 0x00B0
_EM_SETSEL = 0x00B1
_EM_LIMITTEXT = 0x00C5

_IDOK = 1
_IDCANCEL = 2
_SW_SHOW = 5
_VK_BACK = 0x08
_VK_RETURN = 0x0D
_VK_ESCAPE = 0x1B
_VK_CONTROL = 0x11
_VK_A = 0x41
_IDC_ARROW = 32512
_COLOR_3DFACE = 15
_SPI_GETWORKAREA = 0x0030

#: The window, in the units it is laid out in before Windows scales it for the screen.  Wide enough for a
#: name that is going to be read out rather than looked at, and no taller than the three rows in it.
_WIDTH, _HEIGHT = 480, 134

if host.WINDOWS:
    _LRESULT = ctypes.c_ssize_t
    _WPARAM = ctypes.c_size_t
    _LPARAM = ctypes.c_ssize_t
    _HANDLE = ctypes.c_void_p
    _WNDPROC = ctypes.WINFUNCTYPE(_LRESULT, _HANDLE, ctypes.c_uint, _WPARAM, _LPARAM)

    class _WndClass(ctypes.Structure):
        """WNDCLASSW (winuser.h)."""
        _fields_ = [
            ('style', ctypes.c_uint),
            ('lpfnWndProc', _WNDPROC),
            ('cbClsExtra', ctypes.c_int),
            ('cbWndExtra', ctypes.c_int),
            ('hInstance', _HANDLE),
            ('hIcon', _HANDLE),
            ('hCursor', _HANDLE),
            ('hbrBackground', _HANDLE),
            ('lpszMenuName', ctypes.c_wchar_p),
            ('lpszClassName', ctypes.c_wchar_p),
        ]

    class _Msg(ctypes.Structure):
        """MSG.  `private` is the `lPrivate` the Windows 10 SDK added: the field is never read here, but
        `GetMessageW` fills the struct to the size the system knows, and a short one would be written
        past the end of."""
        _fields_ = [
            ('hwnd', _HANDLE),
            ('message', ctypes.c_uint),
            ('wParam', _WPARAM),
            ('lParam', _LPARAM),
            ('time', ctypes.c_uint32),
            ('pt_x', ctypes.c_long),
            ('pt_y', ctypes.c_long),
            ('private', ctypes.c_uint32),
        ]

    class _Rect(ctypes.Structure):
        _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                    ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

    _user32 = ctypes.WinDLL('user32', use_last_error=True)
    _gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
    _kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    # The return types matter on 64-bit: a handle read as the default `int` loses the top half of itself,
    # and an LRESULT read as one turns a window procedure's answer into a different answer.
    _user32.DefWindowProcW.restype = _LRESULT
    _user32.DefWindowProcW.argtypes = [_HANDLE, ctypes.c_uint, _WPARAM, _LPARAM]
    _user32.SendMessageW.restype = _LRESULT
    _user32.SendMessageW.argtypes = [_HANDLE, ctypes.c_uint, _WPARAM, _LPARAM]
    _user32.CreateWindowExW.restype = _HANDLE
    _user32.CreateWindowExW.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p, ctypes.c_wchar_p,
                                        ctypes.c_uint32, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, _HANDLE, _HANDLE, _HANDLE, _HANDLE]
    _user32.GetForegroundWindow.restype = _HANDLE
    _user32.GetFocus.restype = _HANDLE
    _user32.SetFocus.restype = _HANDLE
    _user32.SetFocus.argtypes = [_HANDLE]
    _user32.LoadCursorW.restype = _HANDLE
    _user32.LoadCursorW.argtypes = [_HANDLE, _HANDLE]
    _user32.GetSysColorBrush.restype = _HANDLE
    _user32.GetSysColorBrush.argtypes = [ctypes.c_int]
    _user32.GetWindowTextLengthW.argtypes = [_HANDLE]
    _user32.GetWindowTextW.argtypes = [_HANDLE, ctypes.c_wchar_p, ctypes.c_int]
    _user32.DestroyWindow.argtypes = [_HANDLE]
    _user32.EnableWindow.argtypes = [_HANDLE, ctypes.c_int]
    _user32.SetForegroundWindow.argtypes = [_HANDLE]
    _user32.IsChild.argtypes = [_HANDLE, _HANDLE]
    _user32.GetWindowRect.argtypes = [_HANDLE, ctypes.POINTER(_Rect)]
    _user32.AdjustWindowRect.argtypes = [ctypes.POINTER(_Rect), ctypes.c_uint32, ctypes.c_int]
    _user32.IsDialogMessageW.argtypes = [_HANDLE, ctypes.POINTER(_Msg)]
    _user32.ShowWindow.argtypes = [_HANDLE, ctypes.c_int]
    _user32.GetKeyState.argtypes = [ctypes.c_int]
    _user32.GetKeyState.restype = ctypes.c_short
    _gdi32.CreateFontW.restype = _HANDLE
    _gdi32.DeleteObject.argtypes = [_HANDLE]
    _kernel32.GetModuleHandleW.restype = _HANDLE
    _kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]

    #: hwnd -> the `_Box` that window belongs to.  The class is registered with one window procedure, so
    #: the procedure cannot be a closure over the box and looks it up here instead.
    _boxes: dict = {}

    _CLASS_NAME = 'AudioDefenceTextEntry'
    _registered = False


def _on_window_message(hwnd, message, wparam, lparam):
    """The box's window procedure.  Only the four messages a box has an opinion about; the keys are taken
    in `_Box.pump` instead, where they can be taken before the control turns them into characters."""
    box = _boxes.get(int(hwnd or 0))
    if box is not None:
        if message == _WM_COMMAND:
            pressed = int(wparam) & 0xFFFF
            if pressed == _IDOK:
                box.accept()
                return 0
            if pressed == _IDCANCEL:
                box.cancel()
                return 0
        elif message == _WM_CLOSE:
            box.cancel()                                  # the title bar's X is Cancel
            return 0
        elif message == _WM_SETFOCUS:
            _user32.SetFocus(box.edit)                    # the window never holds the focus, the field does
            return 0
        elif message == _WM_DESTROY:
            # What ends `pump`.  Not `PostQuitMessage`: that puts a WM_QUIT on the *thread's* queue, which
            # is the queue the game's own window shares - the next box read it and closed before it had
            # been seen, and SDL reads a WM_QUIT as the program being asked to quit.
            box.finished = True
            return 0
    return _user32.DefWindowProcW(hwnd, message, wparam, lparam)


if host.WINDOWS:
    #: kept in a module name of its own: a window procedure the garbage collector has taken is a crash the
    #: next time the window is sent a message
    _window_proc = _WNDPROC(_on_window_message)


def _windows_ask(title: str, prompt: str, value: str, max_length: int):
    """The box, as a window of our own with an `EDIT` in it.

    Not a dialog resource: a `DLGTEMPLATE` has to be packed byte by byte in memory and buys only what
    `IsDialogMessageW` already gives a plain window - Tab between the controls, Space on a button - which
    the message loop below asks for directly.
    """
    _register_class()
    box = _Box(title, prompt, value, max_length, _user32.GetForegroundWindow())
    try:
        box.show()
        box.pump()
    finally:
        box.close()
    return box.answer


def _register_class() -> None:
    """The window class, once.  Registering it twice fails, and the class a run has already made a box with
    is still registered for the next one."""
    global _registered
    if _registered:
        return
    wc = _WndClass()
    wc.style = 0
    wc.lpfnWndProc = _window_proc
    wc.cbClsExtra = wc.cbWndExtra = 0
    wc.hInstance = _kernel32.GetModuleHandleW(None)
    wc.hIcon = None
    wc.hCursor = _user32.LoadCursorW(None, _HANDLE(_IDC_ARROW))
    wc.hbrBackground = _user32.GetSysColorBrush(_COLOR_3DFACE)
    wc.lpszMenuName = None
    wc.lpszClassName = _CLASS_NAME
    if not _user32.RegisterClassW(ctypes.byref(wc)):
        raise ctypes.WinError(ctypes.get_last_error())
    _registered = True
    log.debug("the typing box's window class was registered")


class _Box:
    """One box: the window, the field in it, and what was typed."""

    def __init__(self, title: str, prompt: str, value: str, max_length: int, owner):
        self.title = str(title or '')
        self.prompt = str(prompt or '')
        self.value = str(value or '')
        self.max_length = max(1, int(max_length))
        self.owner = owner
        self.hwnd = None
        self.edit = None
        self.cancel_button = None
        self.font = None
        #: set when the window has gone, however it went: what `pump` watches rather than a WM_QUIT
        self.finished = False
        #: None until OK is pressed, so cancelling and typing nothing are told apart by the caller
        self.answer = None

    # --- making it ---------------------------------------------------------------------------------
    def show(self) -> None:
        style = _WS_CAPTION | _WS_SYSMENU
        outer = _Rect(0, 0, _WIDTH, _HEIGHT)
        _user32.AdjustWindowRect(ctypes.byref(outer), style, 0)
        width, height = outer.right - outer.left, outer.bottom - outer.top
        left, top = self._where(width, height)
        instance = _kernel32.GetModuleHandleW(None)
        self.hwnd = _user32.CreateWindowExW(_WS_EX_DLGMODALFRAME | _WS_EX_CONTROLPARENT, _CLASS_NAME,
                                           self.title, style, left, top, width, height,
                                           self.owner, None, instance, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        _boxes[int(self.hwnd)] = self
        self.font = self._font()
        # The prompt is made first on purpose: a screen reader names an edit field after the static text in
        # front of it, so this label is what the field is read out as.
        self._child('STATIC', self.prompt, 0, 14, 12, _WIDTH - 28, 30)
        self.edit = self._child('EDIT', self.value, _WS_TABSTOP | _WS_BORDER | _ES_AUTOHSCROLL,
                                14, 48, _WIDTH - 28, 26)
        self._child('BUTTON', 'OK', _WS_TABSTOP | _BS_DEFPUSHBUTTON, _WIDTH - 196, 88, 88, 28, _IDOK)
        self.cancel_button = self._child('BUTTON', 'Cancel', _WS_TABSTOP,
                                         _WIDTH - 102, 88, 88, 28, _IDCANCEL)
        _user32.SendMessageW(self.edit, _EM_LIMITTEXT, self.max_length, 0)
        # The field starts selected, so the first key typed replaces the name rather than growing it.  It is
        # also what has a screen reader read the whole line out as the box opens.
        self.select_all()
        if self.owner:
            _user32.EnableWindow(self.owner, 0)           # modal: the game cannot be typed into meanwhile
        _user32.ShowWindow(self.hwnd, _SW_SHOW)
        _user32.SetForegroundWindow(self.hwnd)
        _user32.SetFocus(self.edit)

    def _where(self, width: int, height: int):
        """Over the game's window, or over the desktop when there is nothing to sit on.  A third of the way
        down rather than halfway, so a box does not cover what it is asking about."""
        area = _Rect()
        if not (self.owner and _user32.GetWindowRect(self.owner, ctypes.byref(area))):
            if not _user32.SystemParametersInfoW(_SPI_GETWORKAREA, 0, ctypes.byref(area), 0):
                return 100, 100
        return (area.left + (area.right - area.left - width) // 2,
                area.top + (area.bottom - area.top - height) // 3)

    @staticmethod
    def _font():
        """The interface font.  Segoe UI has been the system's since Vista, and `CreateFontW` falls back to
        whatever is nearest when a face is missing, so there is nothing here to check."""
        return _gdi32.CreateFontW(-15, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, 'Segoe UI')

    def _child(self, kind: str, text: str, style: int, x: int, y: int, width: int, height: int,
               identifier: int = 0):
        """One control.  `identifier` is what `WM_COMMAND` names it by - the buttons use the system's own
        IDOK and IDCANCEL, which is what makes OK the default button."""
        child = _user32.CreateWindowExW(0, kind, text, _WS_CHILD | _WS_VISIBLE | style,
                                        x, y, width, height, self.hwnd, _HANDLE(identifier),
                                        _kernel32.GetModuleHandleW(None), None)
        if not child:
            raise ctypes.WinError(ctypes.get_last_error())
        if self.font:
            _user32.SendMessageW(child, _WM_SETFONT, self.font, 1)
        return child

    # --- running it --------------------------------------------------------------------------------
    def pump(self) -> None:
        """The box's own message loop, which is what makes it modal: the game's main loop is not running
        while this one is, exactly as it is not while the file dialog is open.

        A key is read here, before `TranslateMessage` turns it into a character, so taking one is the whole
        of taking it - there is no character left over for the control to insert and no beep for a key it
        did not expect.  What is left goes to `IsDialogMessageW`, which is what a dialog gets for free: Tab
        and Shift Tab between the field and the buttons, and Space on a button.

        The loop ends on `finished`, which the window sets as it goes.  A WM_QUIT ends it as well, and is
        left where it was found: it is the thread's, and the thread's other window is the game's.
        """
        msg = _Msg()
        while not self.finished:
            if _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) <= 0:
                log.info('the typing box was asked to close by something other than itself')
                break
            if msg.message == _WM_KEYDOWN and self._mine(msg.hwnd) and self._key(int(msg.wParam)):
                continue
            if self.hwnd and _user32.IsDialogMessageW(self.hwnd, ctypes.byref(msg)):
                continue
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

    def _mine(self, hwnd) -> bool:
        """Whether a message is the box's.  The loop runs messages for the whole thread, the game's own
        window among them, and a key meant for something else is not the box's to take."""
        if not hwnd or not self.hwnd:
            return False
        return int(hwnd) == int(self.hwnd) or bool(_user32.IsChild(self.hwnd, hwnd))

    def _key(self, key: int) -> bool:
        """The keys the box answers itself, True when it has.  Enter and Escape mean what they mean on
        every other screen in the game; the two with Control are the ones the `EDIT` control does not do."""
        if key == _VK_ESCAPE:
            self.cancel()
            return True
        if key == _VK_RETURN:
            # Enter on Cancel is Cancel.  Anywhere else - the field, or OK - it is OK, which is what the
            # default button means.
            focus = _user32.GetFocus()
            if focus and self.cancel_button and int(focus) == int(self.cancel_button):
                self.cancel()
            else:
                self.accept()
            return True
        if not self._typing() or not _user32.GetKeyState(_VK_CONTROL) & 0x8000:
            return False
        if key == _VK_A:
            self.select_all()
            return True
        if key == _VK_BACK:
            self.delete_word_back()
            return True
        return False

    def _typing(self) -> bool:
        """Whether the focus is in the field, which is where Control plus A and Control plus Backspace mean
        anything at all."""
        focus = _user32.GetFocus()
        return bool(focus and self.edit and int(focus) == int(self.edit))

    def text(self) -> str:
        length = _user32.GetWindowTextLengthW(self.edit)
        buffer = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(self.edit, buffer, length + 1)
        return buffer.value

    def select_all(self) -> None:
        _user32.SendMessageW(self.edit, _EM_SETSEL, 0, -1)

    def delete_word_back(self) -> None:
        """What Control plus Backspace means: the selection if there is one, and otherwise back over the
        spaces behind the caret and then over the word behind those."""
        where = _user32.SendMessageW(self.edit, _EM_GETSEL, 0, 0)
        start, end = where & 0xFFFF, (where >> 16) & 0xFFFF
        if end > start:
            _user32.SendMessageW(self.edit, _WM_CLEAR, 0, 0)
            return
        text = self.text()
        at = min(start, len(text))
        while at > 0 and text[at - 1].isspace():
            at -= 1
        while at > 0 and not text[at - 1].isspace():
            at -= 1
        if at == start:
            return                                        # the caret is at the front: nothing behind it
        _user32.SendMessageW(self.edit, _EM_SETSEL, at, start)
        _user32.SendMessageW(self.edit, _WM_CLEAR, 0, 0)

    def accept(self) -> None:
        self.answer = self.text()
        self._destroy()

    def cancel(self) -> None:
        self.answer = None
        self._destroy()

    # --- taking it down ---------------------------------------------------------------------------
    def _destroy(self) -> None:
        if self.hwnd:
            _user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        self.finished = True

    def close(self) -> None:
        """Everything the box holds, whether it closed itself or the loop fell out from under it."""
        self._destroy()
        for hwnd, box in list(_boxes.items()):
            if box is self:
                _boxes.pop(hwnd, None)
        if self.font:
            _gdi32.DeleteObject(self.font)
            self.font = None
        if self.owner:
            # The game's window is enabled again before it is brought back: the other way round, Windows
            # hands the focus to whatever else is on the screen and the game is left running behind it.
            _user32.EnableWindow(self.owner, 1)
            _user32.SetForegroundWindow(self.owner)
            self.owner = None
