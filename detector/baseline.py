import asyncio
import math
import time
from collections import deque, defaultdict


class BaselineTracker:
    """
    Maintains a rolling 30-minute window of per-second request counts.
    Recalculates mean and stddev every 60 seconds.
    Also tracks per-hour slots to prefer current hour's baseline.
    """

    def __init__(self, config: dict):
        self.window_minutes = config["baseline_window_minutes"]
        self.recalc_interval = config["baseline_recalc_interval_seconds"]
        self.min_samples = config["min_baseline_samples"]
        self.floor = config["baseline_floor_rps"]
        self.per_hour_min = config["per_hour_min_samples"]

        # rolling window: stores (timestamp, count) per second bucket
        self.window = deque()

        # per-hour slots: hour (0-23) -> list of per-second counts
        self.hourly_slots = defaultdict(list)

        # current baseline values
        self.effective_mean = self.floor
        self.effective_stddev = 0.1

        # error rate baseline
        self.error_mean = self.floor
        self.error_stddev = 0.1

        # per-second counters (current second bucket)
        self._current_second = int(time.time())
        self._current_count = 0
        self._current_errors = 0

        self.last_recalc = time.time()

    def record_request(self, status: int):
        """Call this for every incoming request."""
        now = int(time.time())

        if now != self._current_second:
            # new second — flush the old bucket into the window
            self.window.append((self._current_second, self._current_count, self._current_errors))
            hour = int(time.strftime("%H", time.localtime(self._current_second)))
            self.hourly_slots[hour].append(self._current_count)

            self._current_second = now
            self._current_count = 0
            self._current_errors = 0

            # evict buckets older than the window
            cutoff = now - (self.window_minutes * 60)
            while self.window and self.window[0][0] < cutoff:
                self.window.popleft()

        self._current_count += 1
        if status >= 400:
            self._current_errors += 1

    async def recalc_loop(self, audit_log_func):
        """Runs forever, recalculating baseline every recalc_interval seconds."""
        while True:
            await asyncio.sleep(self.recalc_interval)
            self._recalculate()
            await audit_log_func(
                "BASELINE_RECALC",
                ip="-",
                condition=f"mean={self.effective_mean:.4f} stddev={self.effective_stddev:.4f}",
                rate=self.effective_mean,
                baseline=self.effective_mean,
                duration="-"
            )

    def _recalculate(self):
        """Compute mean and stddev from the rolling window."""
        current_hour = int(time.strftime("%H"))

        # prefer current hour's data if enough samples
        hourly = self.hourly_slots.get(current_hour, [])
        if len(hourly) >= self.per_hour_min:
            counts = hourly[-self.per_hour_min:]
        else:
            # fall back to full rolling window
            counts = [c for (_, c, _) in self.window]

        if len(counts) < self.min_samples:
            return  # not enough data yet

        mean = sum(counts) / len(counts)
        variance = sum((x - mean) ** 2 for x in counts) / len(counts)
        stddev = math.sqrt(variance)

        self.effective_mean = max(mean, self.floor)
        self.effective_stddev = max(stddev, 0.1)

        # recalc error baseline
        errors = [e for (_, _, e) in self.window]
        if errors:
            emean = sum(errors) / len(errors)
            evar = sum((x - emean) ** 2 for x in errors) / len(errors)
            self.error_mean = max(emean, self.floor)
            self.error_stddev = max(math.sqrt(evar), 0.1)

    def get_baseline(self) -> tuple[float, float]:
        return self.effective_mean, self.effective_stddev

    def get_error_baseline(self) -> tuple[float, float]:
        return self.error_mean, self.error_stddev
