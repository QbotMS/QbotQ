#!/usr/bin/env python3
"""Diagnostyka: czy menu i harmonogram nowego zamowienia Brokula sa dostepne pod bezposrednim adresem."""
import sys
sys.path.insert(0, "/opt/qbot/app")
import qbot_brokul as B
import qbot_brokul_meals as M

oid = sys.argv[1] if len(sys.argv) > 1 else "20163272"
try:
    meals = M.parse_menu(B.fetch("/customer/diets/menu/item/%s/" % oid), oid)
    print("menu: posilkow", len(meals), "dni", sorted({m["day"] for m in meals}))
except Exception as e:
    print("menu: blad", repr(e))
try:
    print("dostawy:", M.parse_delivery_days(B.fetch("/customer/diets/day/order_item_id/%s/" % oid)))
except Exception as e:
    print("dostawy: blad", repr(e))
