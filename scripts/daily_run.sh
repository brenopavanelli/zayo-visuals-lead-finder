#!/bin/bash
# Daily autonomous outreach run — prints ONLY the JSON summary at the end.
# Used by the Hermes cron job; output is delivered to Telegram as the daily report.
cd /home/ubuntu/zayo-visuals-lead-finder || exit 1
python3 scripts/run_pipeline.py 2>&1 | sed -n '/===== RESUMO (JSON) =====/,$p'
