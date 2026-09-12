#!/usr/bin/env python3
"""Pytanie na Telegramie o raport z jazdy, 10 min po jej koncu. Wolane z telegram_reply_processor (co 2 min)."""
import sys; sys.path.insert(0, "/opt/qbot/app")
from qbot3.rides.ride_report_notify import run_ask
if __name__ == "__main__":
    print("asked:", run_ask())
