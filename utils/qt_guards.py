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

GuardStats
----------
The module tracks how many callbacks were blocked vs passed, enabling
self-test harnesses to verify that generation guards are working:

    from utils.qt_guards import GUARD_STATS
    assert GUARD_STATS.blocked_generation >= 1  # after restart + stale emit

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


# ---------------------------------------------------------------------------
# Guard Statistics — enables self-test validation
# ---------------------------------------------------------------------------
class GuardStats:
    """Track how many callbacks were blocked vs passed through guards.

    Counters are incremented atomically (GIL protects simple int ops).
    Reset via ``GUARD_STATS.reset()`` at the start of a test.
    """
    __slots__ = ("blocked_generation", "blocked_invalid", "passed")

    def __init__(self):
        self.blocked_generation = 0
        self.blocked_invalid = 0
        self.passed = 0

    def reset(self):
        """Reset all counters to zero (for test isolation)."""
        self.blocked_generation = 0
        self.blocked_invalid = 0
        self.passed = 0

    def __repr__(self):
        return (
            f"GuardStats(blocked_generation={self.blocked_generation}, "
            f"blocked_invalid={self.blocked_invalid}, passed={self.passed})"
        )


GUARD_STATS = GuardStats()


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
            GUARD_STATS.blocked_invalid += 1
            return None
        if not _is_valid(o):
            GUARD_STATS.blocked_invalid += 1
            return None
        for w in extra:
            if w is not None and not _is_valid(w):
                GUARD_STATS.blocked_invalid += 1
                return None
        if not _generation_matches(o, generation):
            GUARD_STATS.blocked_generation += 1
            return None
        try:
            GUARD_STATS.passed += 1
            return slot(*args, **kwargs)
        except RuntimeError:
            # Common Qt teardown race: "Internal C++ object already deleted".
            GUARD_STATS.blocked_invalid += 1
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
