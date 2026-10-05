makemhr, from OpenAL Soft 1.25.2

makemhr turns a set of recordings of how a head hears sound from every
direction - a .sofa file, or makemhr's own .def definition file - into an .mhr
file, which OpenAL Soft and Audio Defence's 3D sound use. "Your own 3D sound"
in the game's README says how, step by step.

Keep makemhr.exe and zlib1.dll together: makemhr needs the DLL beside it.

Where these files come from

They are copied unchanged from OpenAL Soft's Windows download,
openal-soft-1.25.2-bin.zip, its makemhr folder. The original, and newer
versions, are at:

- OpenAL Soft's website: https://openal-soft.org/
- OpenAL Soft's releases on GitHub: https://github.com/kcat/openal-soft/releases

makemhr's source code, the version these files were built from, is OpenAL
Soft 1.25.2, in its utils/makemhr folder:
https://github.com/kcat/openal-soft/tree/1.25.2/utils/makemhr

Licences

- makemhr.exe: the GNU General Public License, version 2 or, at your option,
  any later version. Copyright (C) 2011-2019 Christopher Fitzgerald. The
  licence is in COPYING.GPLv2, beside this file.
- zlib1.dll: zlib, the compression library, under the zlib licence:
  https://zlib.net/zlib_license.html

They are not part of the game and are not built into it: they are here so that
anyone with this repository can make an .mhr without downloading anything.
