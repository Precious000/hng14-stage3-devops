import asyncio
import time
import logging

logger = logging.getLogger(__name__)


class Unbanner:
    """
    Manages the backoff unban schedule.
    Schedule: 10 min, 30 min, 2 hours, then permanent.
    """

    # schedule in seconds
    SCHEDULE = [10 * 60, 30 * 60, 2 * 60 * 60]

    def __init__(self, blocker, notifier):
        self.blocker = blocker
        self.notifier = notifier

        # ip -> number of times banned
        self.ban_count: dict[str, int] = {}

        # ip -> scheduled unban time
        self.unban_times: dict[str, float] = {}

    def schedule_unban(self, ip: str):
        """Called when an IP is banned. Schedules its unban unless permanent."""
        count = self.ban_count.get(ip, 0)
        self.ban_count[ip] = count + 1

        if count >= len(self.SCHEDULE):
            logger.info(f"{ip} is permanently banned (offence {count + 1})")
            return  # permanent — never unban

        duration = self.SCHEDULE[count]
        unban_at = time.time() + duration
        self.unban_times[ip] = unban_at
        logger.info(f"Scheduled unban for {ip} in {duration // 60} minutes")

    async def unban_loop(self, audit_log_func):
        """Runs forever, checking every 30 seconds for IPs to unban."""
        while True:
            await asyncio.sleep(30)
            now = time.time()
            to_unban = [ip for ip, t in self.unban_times.items() if now >= t]

            for ip in to_unban:
                del self.unban_times[ip]
                self.blocker.unban(ip)
                count = self.ban_count.get(ip, 1)
                duration_label = self._duration_label(count - 1)

                await self.notifier.send_unban_alert(ip, duration_label)
                await audit_log_func(
                    "UNBAN", ip=ip,
                    condition="scheduled unban",
                    rate=0, baseline=0,
                    duration=duration_label
                )

    def _duration_label(self, index: int) -> str:
        if index == 0:
            return "10 minutes"
        elif index == 1:
            return "30 minutes"
        elif index == 2:
            return "2 hours"
        return "permanent"

    def is_permanent(self, ip: str) -> bool:
        count = self.ban_count.get(ip, 0)
        return count > len(self.SCHEDULE)

    def get_unban_times(self) -> dict:
        return {ip: t for ip, t in self.unban_times.items()}
