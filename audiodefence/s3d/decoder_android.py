"""PORT ADDITION (Android build): decoding the bundle's .m4a/.mp3 with the phone's own decoder.

Java (SoundDecoder, MediaCodec) decodes a file once and keeps the samples; Python gets a small handle with
the length, channel count and rate - all the engine needs to know - and the mixer reads the samples itself.
"""
from __future__ import annotations

from ..platform.jbridge import bridge


class AndroidSound:
    """Stands where the decoded numpy array stood: `.shape` is (frames, channels), `len()` is frames."""
    __slots__ = ('handle', 'frames', 'channels', 'rate')

    def __init__(self, handle: int, frames: int, channels: int, rate: int):
        self.handle, self.frames, self.channels, self.rate = handle, frames, channels, rate

    @property
    def shape(self):
        return (self.frames, self.channels)

    def __len__(self):
        return self.frames


def decode_now(path: str):
    info = list(bridge().decode(path))
    if not info or info[0] < 0:
        raise RuntimeError('cannot decode %s' % path)
    handle, frames, channels, rate = (int(v) for v in info[:4])
    return AndroidSound(handle, frames, channels, rate), rate


def lead_in_of(sound: AndroidSound, floor: float, most: float) -> float:
    return float(bridge().leadIn(sound.handle, float(floor), float(most)))
