import subprocess
import logging

logger = logging.getLogger(__name__)


class Blocker:
    """Manages iptables DROP rules for banned IPs."""

    def __init__(self):
        self.blocked: set[str] = set()

    def ban(self, ip: str):
        """Add iptables DROP rule for this IP."""
        if ip in self.blocked:
            return
        try:
            subprocess.run(
                ["iptables", "-I", "INPUT", "-s", ip, "-j", "DROP"],
                check=True, capture_output=True
            )
            self.blocked.add(ip)
            logger.info(f"Banned IP: {ip}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to ban {ip}: {e.stderr.decode()}")

    def unban(self, ip: str):
        """Remove iptables DROP rule for this IP."""
        if ip not in self.blocked:
            return
        try:
            subprocess.run(
                ["iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"],
                check=True, capture_output=True
            )
            self.blocked.discard(ip)
            logger.info(f"Unbanned IP: {ip}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to unban {ip}: {e.stderr.decode()}")

    def is_banned(self, ip: str) -> bool:
        return ip in self.blocked

    def get_banned(self) -> list[str]:
        return list(self.blocked)
