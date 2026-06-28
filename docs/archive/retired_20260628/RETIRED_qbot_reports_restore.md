# QBot Reports — Restore Plan

**Date**: 2026-05-26

## Purpose
Restore daily and ride report generation and delivery as in legacy Qbot.

## Tools
| Tool | Safety | Description |
|------|--------|-------------|
| `qbot_daily_report_status` | READ_ONLY | Check last sent date, channels, cache |
| `qbot_daily_report_preview` | READ_ONLY | Preview report contents without sending |
| `qbot_daily_report_send` | WRITE_SAFE | Send report (dry_run=true default) |
| `qbot_ride_report_status` | READ_ONLY | Check reported activities |
| `qbot_ride_report_latest` | READ_ONLY | Show latest ride report preview |
| `qbot_ride_report_preview` | READ_ONLY | Preview next ride report |
| `qbot_ride_report_send` | WRITE_SAFE | Send ride report (dry_run=true default) |
| `qbot_reports_schedule_status` | READ_ONLY | Show cron/timer schedule |
| `qbot_reports_restore_plan` | READ_ONLY | Full restore plan |

## MCP Exposure
- `qbot.daily_report_status` → daily_report_status
- `qbot.daily_report_preview` → daily_report_preview
- `qbot.ride_report_status` → ride_report_status
- `qbot.ride_report_latest` → ride_report_latest
- `qbot.ride_report_preview` → ride_report_preview

## Telegram
- `/daily_report` or `/daily` — status
- `/ride_report` or `/reports` — status

## Security
- All send operations default dry_run=true
- Max 1 test message
- No email without confirmed SMTP
- Telegram delivery uses existing client
