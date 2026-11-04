"""Sandbox-friendly mkdir per eseguire test e pip dentro la sandbox DSH.

Python 3.13+ applica davvero il mode POSIX di ``os.mkdir`` creando una DACL
"owner only". Il token ristretto usato dalla sandbox DSH non supera il
controllo di accesso su una DACL del genere, quindi ogni ``mkdtemp()`` /
``tmp_path`` fallisce con ``PermissionError``.

Su Windows i permessi POSIX non hanno significato: qui il mode viene forzato
a 0o777. Il confinamento reale resta garantito dal token ristretto e dal jail
del harness, non dai bit del mode.
"""

from __future__ import annotations

import os

_mkdir = os.mkdir


def _sandbox_safe_mkdir(path, mode=0o777, *, dir_fd=None):
    if dir_fd is not None:
        return _mkdir(path, mode, dir_fd=dir_fd)
    return _mkdir(path, 0o777)


os.mkdir = _sandbox_safe_mkdir


# tempfile cleanup tries to chmod temporary directories back to 0o700.
# Under the restricted Windows token that chmod is denied and build
# cleanup fails even though the build itself succeeded. Mode bits are
# meaningless for this token; skip the cosmetic reset.
try:
    import tempfile

    tempfile._resetperms = lambda path: None

except Exception:
    pass
