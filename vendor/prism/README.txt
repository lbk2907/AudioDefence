Prism 0.18.3, the library Audio Defence speaks to NVDA and every other screen reader through on Windows.

prism.dll is the 64-bit release build, unchanged, and the same file the maintainer's AccessDBT carries.
The game calls it directly (audiodefence/platform/prismdll.py), so it needs no Python package.

Prism is free software under the Mozilla Public License 2.0.  Its source code is at
https://github.com/ethindp/prism, where you may obtain a copy of it.  Its licence, and the licences of the
libraries built into it, are in LICENSES.

To update it: replace prism.dll and LICENSES with the new release's, then read the new include/prism.h
against the declarations in audiodefence/platform/prismdll.py before building.
