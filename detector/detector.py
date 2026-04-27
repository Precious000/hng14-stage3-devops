import time
from collections import deque, defaultdict


class AnomalyDetector:
    """
    Sliding window anomaly detector.
    One deque per IP, one global deque.
    Evicts entries older than 60 seconds on every check.
    """

    def __init__(self, config: dict, baseline):
        self.window_seconds = config["sliding_window_seconds"]
        self.zscore_threshold = config["zscore_threshold"]
        self.rate_multiplier = config["rate_multiplier_threshold"]
        self.error_multiplier = config["error_rate_multiplier"]
        self.baseline = baseline

        # deque per IP: stores timestamps of requests
        self.ip_windows: dict[str, deque] = defaultdict(deque)

        # deque per IP for errors
        self.ip_error_windows: dict[str, deque] = defaultdict(deque)

        # global window
        self.global_window: deque = deque()

        # track tightened IPs (those with high error rates)
        self.tightened_ips: set[str] = set()

    def record(self, ip: str, status: int) -> tuple[bool, bool, str]:
        """
        Record a request. Returns (ip_anomaly, global_anomaly, reason).
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # add to IP window
        self.ip_windows[ip].append(now)
        self.global_window.append(now)

        if status >= 400:
            self.ip_error_windows[ip].append(now)

        # evict old entries
        self._evict(self.ip_windows[ip], cutoff)
        self._evict(self.global_window, cutoff)
        self._evict(self.ip_error_windows[ip], cutoff)

        # check error surge — tighten threshold if needed
        self._check_error_surge(ip)

        # current rates (requests per second)
        ip_rate = len(self.ip_windows[ip]) / self.window_seconds
        global_rate = len(self.global_window) / self.window_seconds

        mean, stddev = self.baseline.get_baseline()

        # tightened IPs get a lower multiplier threshold
        multiplier = self.rate_multiplier
        zscore_thresh = self.zscore_threshold
        if ip in self.tightened_ips:
            multiplier = max(1.5, multiplier / 2)
            zscore_thresh = max(1.5, zscore_thresh / 2)

        # check IP anomaly
        ip_anomaly, ip_reason = self._check(ip_rate, mean, stddev, multiplier, zscore_thresh)

        # check global anomaly
        global_anomaly, global_reason = self._check(
            global_rate, mean, stddev,
            self.rate_multiplier, self.zscore_threshold
        )

        return ip_anomaly, global_anomaly, ip_reason or global_reason

    def _evict(self, window: deque, cutoff: float):
        while window and window[0] < cutoff:
            window.popleft()

    def _check(self, rate: float, mean: float, stddev: float,
               multiplier: float, zscore_thresh: float) -> tuple[bool, str]:
        if stddev > 0:
            zscore = (rate - mean) / stddev
            if zscore > zscore_thresh:
                return True, f"zscore={zscore:.2f}"

        if mean > 0 and rate > multiplier * mean:
            return True, f"rate={rate:.2f} > {multiplier}x mean={mean:.2f}"

        return False, ""

    def _check_error_surge(self, ip: str):
        error_mean, _ = self.baseline.get_error_baseline()
        error_rate = len(self.ip_error_windows[ip]) / self.window_seconds
        if error_mean > 0 and error_rate >= self.error_multiplier * error_mean:
            self.tightened_ips.add(ip)
        else:
            self.tightened_ips.discard(ip)

    def get_top_ips(self, n: int = 10) -> list[tuple[str, int]]:
        counts = [(ip, len(w)) for ip, w in self.ip_windows.items()]
        return sorted(counts, key=lambda x: x[1], reverse=True)[:n]

    def get_global_rps(self) -> float:
        return len(self.global_window) / self.window_seconds
