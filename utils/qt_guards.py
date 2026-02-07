"""Qt safety helpers for worker -> UI signal delivery.

Use these helpers to avoid:
1) Use-after-free crashes when a widget gets destroyed while a worker signal is in flight.
2) Stale worker signals being applied to a new UI instance after restart/relaunch.

How to use
----------
- On the UI owner (MainWindow, Dialog), define an integer attribute ``_ui_generation``.
  Increment it when you logically restart/reload the UI.
- When starting a worker, capture ``gen = owner._ui_generation``.
- Connect worker signals using ``connect_guarded(signal, owner, slot, generation=gen)``.

The wrapper will:
- check ``shiboken6.isValid(owner)``
- check ``owner._ui_generation == gen`` (if gen is not None)
- optionally check other widgets passed via ``extra_valid=[...]``

Note: This module is intentionally dependency-light and safe to import from anywhere.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional
import weakref

from PySide6.QtCore import Qt

try:
    import shiboken6
except Exception:  # pragma: no cover
    shiboken6 = None  # type: ignore


def _is_valid(obj: Any) -> bool:
    """Return True if *obj* is a live Qt object (or None).

    shiboken6.isValid expects a Qt wrapper.  For non-Qt objects, treat as valid.
    """
    if obj is None:
        return True
    if shiboken6 is None:
        return True
    try:
        return bool(shiboken6.isValid(obj))
    except Exception:
        return True


def _generation_matches(owner: Any, expected: Optional[int]) -> bool:
    if expected is None:
        return True
    current = getattr(owner, "_ui_generation", None)
    return current == expected


def make_guarded_slot(
    owner: Any,
    slot: Callable[..., Any],
    *,
    generation: Optional[int] = None,
    extra_valid: Optional[Iterable[Any]] = None,
) -> Callable[..., Any]:
    """Wrap *slot* with validity and generation checks."""

    owner_ref = weakref.ref(owner)
    extra = list(extra_valid or [])

    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        o = owner_ref()
        if o is None:
            return None
        if not _is_valid(o):
            return None
        for w in extra:
            if w is not None and not _is_valid(w):
                return None
        if not _generation_matches(o, generation):
            return None
        try:
            return slot(*args, **kwargs)
        except RuntimeError:
            # Common Qt teardown race: "Internal C++ object already deleted".
            return None

    return _wrapped


def connect_guarded(
    signal: Any,
    owner: Any,
    slot: Callable[..., Any],
    *,
    generation: Optional[int] = None,
    extra_valid: Optional[Iterable[Any]] = None,
    also_check: Optional[Iterable[Any]] = None,
    connection_type: Qt.ConnectionType = Qt.QueuedConnection,
) -> None:
    """Connect *signal* to *slot* using a guarded wrapper.

    Parameters
    ----------
    signal : PySide6 Signal
    owner : QObject whose lifetime gates delivery
    slot : callable to invoke when the signal fires
    generation : expected ``owner._ui_generation`` value (None = skip check)
    extra_valid / also_check : additional QObjects that must still be valid
    connection_type : defaults to ``Qt.QueuedConnection``
    """
    merged = list(extra_valid or []) + list(also_check or [])
    wrapped = make_guarded_slot(
        owner, slot, generation=generation, extra_valid=merged or None,
    )
    signal.connect(wrapped, connection_type)
