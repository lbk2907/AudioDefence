"""PORT ADDITION (user request, 2026-10-05): pygame._sdl2.controller on the phone.

The desktop's platform/pad.py opens the controllers through this module and reads their buttons, sticks and
triggers from SDL's controller events.  On the phone the controllers are Android's: com.audiodefence.Bridge
lists them (padIds, padName), sends their input as events in SDL's own numbering, which android_main turns
into the events pad.py reads, and rumbles them (rumblePad).  This is the rest of it - the controllers as
pygame's Controller objects - so pad.py runs on the phone as it is.
"""


def _bridge():
    from audiodefence.platform.jbridge import bridge
    return bridge()


def _ids() -> list:
    return [int(i) for i in _bridge().padIds()]


def init() -> None:
    pass


def quit() -> None:
    pass


def get_count() -> int:
    return len(_ids())


def is_controller(index: int) -> bool:
    return 0 <= index < len(_ids())


class _Joystick:
    def __init__(self, instance_id: int):
        self._instance_id = instance_id

    def get_instance_id(self) -> int:
        return self._instance_id


class Controller:
    """The controller `index`th in the phone's list, by its Android device id."""

    def __init__(self, index: int):
        ids = _ids()
        if not 0 <= index < len(ids):
            raise RuntimeError('there is no controller %d' % index)
        self._instance_id = ids[index]
        self.name = str(_bridge().padName(self._instance_id))

    def as_joystick(self) -> _Joystick:
        return _Joystick(self._instance_id)

    def rumble(self, low_frequency: float, high_frequency: float, duration: int) -> bool:
        return bool(_bridge().rumblePad(self._instance_id, float(low_frequency), float(high_frequency),
                                        int(duration)))

    def stop_rumble(self) -> None:
        pass

    def quit(self) -> None:
        pass
