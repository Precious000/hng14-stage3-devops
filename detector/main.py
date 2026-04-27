import asyncio
import logging
import time
import os
import yaml
from datetime import datetime

from monitor import tail_log
from baseline import BaselineTracker
from detector import AnomalyDetector
from blocker import Blocker
from unbanner import Unbanner
from notifier import Notifier
import dashboard
from dashboard import run_dashboard, set_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

START_TIME = time.time()


def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


async def audit_log(action: str, ip: str, condition: str,
                    rate: float, baseline: float, duration: str):
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {action} {ip} | {condition} | rate={rate:.4f} | baseline={baseline:.4f} | duration={duration}\n"
    logger.info(line.strip())

    audit_path = config.get("audit_log", "/var/log/detector/audit.log")
    os.makedirs(os.path.dirname(audit_path), exist_ok=True)
    with open(audit_path, "a") as f:
        f.write(line)


async def process_requests(queue: asyncio.Queue, baseline_tracker: BaselineTracker,
                            detector: AnomalyDetector, blocker: Blocker,
                            unbanner: Unbanner, notifier: Notifier):
    # track which IPs we already alerted on to avoid alert spam
    alerted_ips: set[str] = set()
    global_alerted = False
    global_alert_cooldown = 0

    while True:
        entry = await queue.get()
        ip = entry["source_ip"]
        status = entry["status"]

        # skip private/unknown IPs
        if ip in ("unknown", "-", "", "127.0.0.1") or ip.startswith("172.") or ip.startswith("10."):
            continue

        # record in baseline
        baseline_tracker.record_request(status)

        # skip already banned IPs
        if blocker.is_banned(ip):
            continue

        # run anomaly detection
        ip_anomaly, global_anomaly, reason = detector.record(ip, status)

        mean, stddev = baseline_tracker.get_baseline()
        ip_rate = len(detector.ip_windows[ip]) / detector.window_seconds
        global_rate = detector.get_global_rps()

        # handle IP anomaly
        if ip_anomaly and ip not in alerted_ips:
            alerted_ips.add(ip)
            ban_count = unbanner.ban_count.get(ip, 0)
            schedule = Unbanner.SCHEDULE
            if ban_count < len(schedule):
                duration_label = unbanner._duration_label(ban_count)
            else:
                duration_label = "permanent"

            blocker.ban(ip)
            unbanner.schedule_unban(ip)

            await notifier.send_ban_alert(ip, reason, ip_rate, mean, duration_label)
            await audit_log("BAN", ip=ip, condition=reason,
                            rate=ip_rate, baseline=mean, duration=duration_label)

        # handle global anomaly (alert only, no block)
        now = time.time()
        if global_anomaly and not global_alerted and now > global_alert_cooldown:
            global_alerted = True
            global_alert_cooldown = now + 300  # 5 min cooldown between global alerts
            await notifier.send_global_alert(reason, global_rate, mean)
            await audit_log("GLOBAL_ALERT", ip="-", condition=reason,
                            rate=global_rate, baseline=mean, duration="-")
        elif not global_anomaly:
            global_alerted = False

        # remove from alerted set if rate drops back to normal
        if not ip_anomaly and ip in alerted_ips:
            alerted_ips.discard(ip)


async def update_dashboard_loop(detector: AnomalyDetector,
                                 blocker: Blocker,
                                 baseline_tracker: BaselineTracker):
    while True:
        mean, stddev = baseline_tracker.get_baseline()
        set_state({
            "banned_ips": blocker.get_banned(),
            "global_rps": detector.get_global_rps(),
            "top_ips": detector.get_top_ips(10),
            "mean": mean,
            "stddev": stddev,
            "uptime": time.time() - START_TIME,
        })
        await asyncio.sleep(3)


async def main():
    global config
    config = load_config()
    logger.info("Starting HNG Anomaly Detector")

    notifier = Notifier(os.getenv("SLACK_WEBHOOK_URL", ""))
    blocker = Blocker()
    unbanner = Unbanner(blocker, notifier)
    baseline_tracker = BaselineTracker(config)
    detector = AnomalyDetector(config, baseline_tracker)

    queue: asyncio.Queue = asyncio.Queue()

    await asyncio.gather(
        tail_log(config["log_file"], queue),
        process_requests(queue, baseline_tracker, detector, blocker, unbanner, notifier),
        baseline_tracker.recalc_loop(audit_log),
        unbanner.unban_loop(audit_log),
        update_dashboard_loop(detector, blocker, baseline_tracker),
        run_dashboard(config["dashboard_port"]),
    )


if __name__ == "__main__":
    asyncio.run(main())
