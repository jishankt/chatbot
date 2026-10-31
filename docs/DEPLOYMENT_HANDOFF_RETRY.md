# Production Deployment Guide: Handoff Retry Sweep & Multi-Channel Escalation

**System**: Kepler Tech Sales AI Commercial Assistant  
**Process**: `scripts/retry_handoffs.py` (via systemd timer or cron)  

---

## 1. Overview
When a business customer requests human sales assistance or generates a quotation requiring specialist follow-up, the system dispatches an alert to the sales desk (`sales@keplertechllc.com`). If all primary notification channels fail (e.g. SMTP server timeout or network issue), the handoff record is preserved in the database with status `failed_all_channels`.

The background retry sweep regularly inspects failed handoffs, increments `retry_count`, and re-attempts dispatch. If a handoff reaches `MAX_HANDOFF_RETRY_ATTEMPTS` (3), it is marked as `permanent_failure` and immediately escalated to a **secondary emergency channel** (`ops-emergency@keplertechllc.com`).

---

## 2. Installation Options

### Option A: Systemd Timer (Recommended for Production Ubuntu/Debian)

1. **Copy unit files to systemd directory**:
```bash
sudo cp /opt/basics/config/systemd/sales-handoff-retry.service /etc/systemd/system/
sudo cp /opt/basics/config/systemd/sales-handoff-retry.timer /etc/systemd/system/
```

2. **Reload systemd daemon and enable timer**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sales-handoff-retry.timer
```

3. **Verify status**:
```bash
systemctl list-timers --all | grep sales-handoff
sudo journalctl -u sales-handoff-retry.service -n 50 --no-pager
```

---

### Option B: Cron (Alternative for Container Host or Minimal Linux)

1. **Link cron configuration**:
```bash
sudo cp /opt/basics/config/cron.d/sales_handoff_retry /etc/cron.d/sales_handoff_retry
sudo chmod 0644 /etc/cron.d/sales_handoff_retry
sudo chown root:root /etc/cron.d/sales_handoff_retry
```

2. **Monitor execution logs**:
```bash
sudo tail -f /var/log/sales_handoff_retry.log
```

---

## 3. Escalation Channel Verification Drill

To verify the end-to-end escalation path without waiting for timer triggers:
```bash
# Run manual dry-run sweep
/opt/basics/venv/bin/python /opt/basics/scripts/retry_handoffs.py
```
If any handoffs have exceeded max retries, check journal logs for the critical alert:
```text
CRITICAL FINAL ALERT: Handoff #... reached max retries (3/3). Marked as permanent_failure.
🚨 SECONDARY CHANNEL EMERGENCY ALERT: Handoff #... has PERMANENTLY FAILED all notification channels.
```
