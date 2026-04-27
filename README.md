# HNG Stage 3 — Anomaly Detection Engine

## Live Server
- Server IP: 100.27.233.159
- Metrics Dashboard: http://pabbyhng.duckdns.org:8080

## Language Choice
Python. Chosen because:
- asyncio makes it easy to run multiple tasks concurrently (log tailing, detection, dashboard, unbanning) in a single thread without complexity of threads
- collections.deque gives O(1) append and popleft which is critical for high-throughput sliding windows
- Rich ecosystem: FastAPI for dashboard, aiohttp for Slack, psutil for system metrics
- Readable code makes the detection logic easy to audit and verify

## How the Sliding Window Works
Each IP has its own deque storing the Unix timestamps of its recent requests. The global traffic also has one deque.

Every time a request arrives:
1. The current timestamp is appended to the right of the deque
2. The cutoff time is calculated as: now - 60 seconds
3. Any timestamps older than the cutoff are removed from the left using popleft()
4. The length of the deque at any moment = number of requests in the last 60 seconds
5. Rate = len(deque) / 60 = requests per second

Eviction example:
- Time 100: deque = [100]
- Time 110: deque = [100, 110]
- Time 161: cutoff = 101, so 100 is evicted → deque = [110, 161]

This gives a true rolling window — not a per-minute counter that resets on the clock.

## How the Baseline Works
- Window size: 30 minutes of per-second request counts stored in a rolling deque
- Recalculation interval**: Every 60 seconds, mean and standard deviation are recomputed
- Per-hour slots: Counts are also stored by hour (0-23). If the current hour has 30+ samples, its data is preferred over the full 30-minute window — because 3am traffic is naturally different from 3pm traffic
- Floor values: mean floor = 0.1 req/s, stddev floor = 0.1 — prevents division by zero and false alarms during zero-traffic periods
- Anomaly triggers: z-score > 3.0 OR rate > 5x baseline mean, whichever fires first

## Architecture
Internet Traffic
↓
Nginx (port 80)

Reverse proxy to Nextcloud
Writes JSON access logs to HNG-nginx-logs volume
↓
Nextcloud (internal only)

Detector (port 8080)

Tails Nginx logs from shared volume
Sliding window anomaly detection
iptables blocking
Slack alerts
Live dashboard


## Setup Instructions — Fresh VPS to Running Stack

### Prerequisites
- Ubuntu 24.04 VPS with 2 vCPU, 2GB RAM minimum
- Ports 80, 8080, 22 open in firewall

### Step 1: Install dependencies
```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo apt install -y docker-compose-plugin
newgrp docker
```

### Step 2: Clone the repo
```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
```

### Step 3: Configure Slack webhook
```bash
nano detector/config.yaml
# replace YOUR_SLACK_WEBHOOK_URL_HERE with your real webhook URL
```

### Step 4: Start the stack
```bash
docker compose up -d --build
```

### Step 5: Verify
```bash
docker compose ps
# all three containers should show Up

curl http://localhost:8080
# dashboard should return HTML
```

### What a successful startup looks like
NAME                      STATUS
hng-stage3-nginx-1        Up
hng-stage3-detector-1     Up
hng-stage3-nextcloud-1    Up

Dashboard accessible at http://YOUR_IP:8080 showing:
- Global req/s
- Banned IPs (empty on fresh start)
- Baseline mean and stddev
- CPU and memory usage
- Uptime

## GitHub Repository
https://github.com/Precious000/hng14-stage3-devops.git
