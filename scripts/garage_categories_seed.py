# -*- coding: utf-8 -*-
"""Rejestr kategorii wyprawowych w garage.db (zrodlo prawdy dla zakladki i Plannera)."""
import sqlite3

DB = "/opt/qbot/app/data/garage.db"

# (nazwa, sekcja, kolejnosc)
CATS = [
    # --- Po rowerze / oboz ---
    ("Koszulka na wieczór",        "Po rowerze / obóz", 10),
    ("Spodnie długie / dresowe",   "Po rowerze / obóz", 20),
    ("Bluza / polar",              "Po rowerze / obóz", 30),
    ("Warstwa ciepła (puchówka)",  "Po rowerze / obóz", 40),
    ("Bielizna (nierowerowa)",     "Po rowerze / obóz", 50),
    ("Skarpety zwykłe",            "Po rowerze / obóz", 60),
    ("Obuwie zapasowe / klapki",   "Po rowerze / obóz", 70),
    ("Czapka ciepła",              "Po rowerze / obóz", 80),
    ("Strój do spania",            "Po rowerze / obóz", 90),
    ("Ręcznik / strój kąpielowy",  "Po rowerze / obóz", 100),
    # --- Sprzet wyprawowy ---
    ("Naprawa i narzędzia",        "Sprzęt wyprawowy", 200),
    ("Apteczka",                   "Sprzęt wyprawowy", 210),
    ("Higiena i kosmetyki",        "Sprzęt wyprawowy", 220),
    ("Nocleg / biwak",             "Sprzęt wyprawowy", 230),
    ("Gotowanie",                  "Sprzęt wyprawowy", 240),
    ("Woda",                       "Sprzęt wyprawowy", 250),
    ("Zasilanie i ładowanie",      "Sprzęt wyprawowy", 260),
    ("Oświetlenie osobiste",       "Sprzęt wyprawowy", 270),
    ("Zabezpieczenia",             "Sprzęt wyprawowy", 280),
    ("Dokumenty i awaryjne",       "Sprzęt wyprawowy", 290),
    # --- kategoria historyczna: zostaje, zeby nic nie zniknelo ---
    ("Sprzęt wyprawowy",           "Sprzęt wyprawowy", 900),
]

c = sqlite3.connect(DB)
c.execute("""CREATE TABLE IF NOT EXISTS gear_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    section TEXT NOT NULL,
    sort INTEGER DEFAULT 100,
    active INTEGER DEFAULT 1
)""")
added, upd = 0, 0
for name, section, srt in CATS:
    row = c.execute("SELECT id FROM gear_categories WHERE name=?", (name,)).fetchone()
    if row:
        c.execute("UPDATE gear_categories SET section=?, sort=?, active=1 WHERE id=?",
                  (section, srt, row[0]))
        upd += 1
    else:
        c.execute("INSERT INTO gear_categories (name, section, sort, active) VALUES (?,?,?,1)",
                  (name, section, srt))
        added += 1
c.commit()
print("dodano:", added, "| zaktualizowano:", upd)
print("\n== rejestr ==")
for r in c.execute("SELECT section, name, sort FROM gear_categories WHERE active=1 ORDER BY sort"):
    print("  [%s] %s" % (r[0], r[1]))
c.close()
