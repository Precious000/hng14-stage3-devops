import asyncio
import json
import os
import aiofiles


async def tail_log(log_file: str, queue: asyncio.Queue):
    """
    Continuously tail the nginx log file line by line.
    If the file doesn't exist yet, wait until it does.
    """
    # wait for log file to exist
    while not os.path.exists(log_file):
        await asyncio.sleep(1)

    async with aiofiles.open(log_file, mode='r') as f:
        # seek to end of file so we only process new lines
        await f.seek(0, 2)

        while True:
            line = await f.readline()
            if not line:
                await asyncio.sleep(0.1)
                continue

            line = line.strip()
            if not line:
                continue

            parsed = parse_line(line)
            if parsed:
                await queue.put(parsed)


def parse_line(line: str) -> dict | None:
    """
    Parse a single JSON log line from nginx.
    Returns a dict or None if the line is malformed.
    """
    try:
        data = json.loads(line)
        return {
            "source_ip": data.get("source_ip", "unknown"),
            "timestamp": data.get("timestamp", ""),
            "method": data.get("method", ""),
            "path": data.get("path", ""),
            "status": int(data.get("status", 0)),
            "response_size": int(data.get("response_size", 0)),
        }
    except (json.JSONDecodeError, ValueError):
        return None
