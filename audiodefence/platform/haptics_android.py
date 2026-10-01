"""PORT ADDITION (Android build): haptics on the phone - none yet.  Every call the game makes is accepted
and does nothing.  On the phone this module is `platform.haptics` (see platform/__init__.py)."""
from __future__ import annotations


class Haptics:
    _shared = None
    #: FIX: read from the class by the Minigun (powerups.MinigunPowerUp.update), where __getattr__ below
    #: does not reach.  Without it the Minigun's update failed on every tick once it had spun up: it never
    #: fired a bullet, never ran out, and took the melee weapon's updates down with it while it lasted.
    SUSTAIN = 0.12

    @classmethod
    def shared(cls) -> 'Haptics':
        if cls._shared is None:
            cls._shared = Haptics()
        return cls._shared

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        return lambda *a, **k: None
