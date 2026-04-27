import aiohttp
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Notifier:
    """Sends Slack alerts via webhook."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def _send(self, message: str):
        if not self.webhook_url or self.webhook_url == "YOUR_SLACK_WEBHOOK_URL_HERE":
            logger.info(f"[SLACK MOCK] {message}")
            return
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    self.webhook_url,
                    json={"text": message},
                    timeout=aiohttp.ClientTimeout(total=5)
                )
        except Exception as e:
            logger.error(f"Slack notification failed: {e}")

    async def send_ban_alert(self, ip: str, condition: str,
                              rate: float, baseline: float, duration: str):
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        msg = (
            f":rotating_light: *IP BANNED*\n"
            f"IP: `{ip}`\n"
            f"Condition: {condition}\n"
            f"Rate: {rate:.2f} req/s\n"
            f"Baseline: {baseline:.2f} req/s\n"
            f"Ban duration: {duration}\n"
            f"Time: {ts}"
        )
        await self._send(msg)

    async def send_unban_alert(self, ip: str, duration: str):
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        msg = (
            f":white_check_mark: *IP UNBANNED*\n"
            f"IP: `{ip}`\n"
            f"Was banned for: {duration}\n"
            f"Time: {ts}"
        )
        await self._send(msg)

    async def send_global_alert(self, condition: str, rate: float, baseline: float):
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        msg = (
            f":warning: *GLOBAL TRAFFIC ANOMALY*\n"
            f"Condition: {condition}\n"
            f"Global rate: {rate:.2f} req/s\n"
            f"Baseline: {baseline:.2f} req/s\n"
            f"Time: {ts}"
        )
        await self._send(msg)
