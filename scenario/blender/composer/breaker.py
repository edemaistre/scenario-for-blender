# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Circuit breaker for main-thread UI surfaces: a draw handler that keeps failing or stalls is removed, never left to freeze Blender."""
import time


class Breaker:
    def __init__(self, label, failures=5, stall=2.0, on_trip=None, clock=time.perf_counter):
        self.label, self.failures, self.stall, self.on_trip, self.clock = label, failures, stall, on_trip, clock
        self.consecutive = 0
        self.tripped = False
        self.reason = ""
        self.first_call = True

    def guard(self, fn, *args):
        if self.tripped:
            return None
        start = self.clock()
        try:
            result = fn(*args)
        except Exception as err:
            self.consecutive += 1
            if self.consecutive >= self.failures:
                self._trip(f"{self.failures} consecutive errors, last: {type(err).__name__}: {err}")
            return None
        self.consecutive = 0
        elapsed = self.clock() - start
        if elapsed > self.stall and not self.first_call:
            self._trip(f"one call took {elapsed:.1f} s")
        self.first_call = False
        return result

    def _trip(self, reason):
        self.tripped, self.reason = True, reason
        if self.on_trip:
            self.on_trip(reason)

    def reset(self):
        self.tripped, self.reason, self.consecutive, self.first_call = False, "", 0, True
