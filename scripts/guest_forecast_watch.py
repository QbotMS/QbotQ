#!/usr/bin/env python3
"""[G4] Pilnowanie prognozy dla zaproszonych gosci - timer 07:00 i 18:00 (Europe/Warsaw).

Zakres: aktywne zaproszenia (bez uniewaznienia, bez odpowiedzi 'nie'), jazdy od dzis do +3 dni, przed startem jazdy.
Skrot prognozy liczony warstwa planu BEZ AI (qbot_web._build_report_data ai=False, day_table=True) raz na plan
(trasa+dzien+start+przerwy), porownanie z punktem odniesienia zaproszenia (fc_baseline z chwili wysylki).
Istotna zmiana (ride_invite.significant_changes): odczuwalna +/-3 C (min/max), wiatr +/-3 m/s, deszcz przekracza 40%
lub zmienia sie o 30 pkt lub suma +/-3 mm, burza pojawia sie/znika, WBGT przekracza 23/26 C.
Mail do goscia (maks. 1 na 18 h) + 1 zbiorczy do organizatora. Po wyslaniu nowy stan = punkt odniesienia.
Brak punktu odniesienia (zaproszenia sprzed G4) -> zapis cichy, bez maila.

Uzycie:  guest_forecast_watch.py            (wysyla)
         guest_forecast_watch.py --dry-run  (nic nie wysyla i nic nie zapisuje; pokazuje co by zrobil)
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, "/opt/qbot/app")
os.chdir("/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
try:
    from dotenv import load_dotenv
    load_dotenv("/opt/qbot/app/.env")
except Exception:
    pass

DRY = "--dry-run" in sys.argv
HORIZON_DAYS = 3
for _i, _a in enumerate(sys.argv):          # --days N (do testow; timer uzywa domyslnych 3)
    if _a == "--days" and _i + 1 < len(sys.argv):
        HORIZON_DAYS = int(sys.argv[_i + 1])
MIN_GAP_H = 18


def main():
    import smtplib
    from email.mime.text import MIMEText
    import qbot_web as W
    import qbot_config as C
    from qbot3.routes import ride_invite as RI
    now = dt.datetime.now().astimezone()
    today = now.date()
    conn = W._db_conn()
    RI.ensure(conn); conn.commit()
    rows = conn.execute(
        "SELECT token, route_id, ride_date, start_time, long_stops, long_stop_min, email, status, fc_baseline, fc_notified_at "
        "FROM qbot_v2.ride_invite WHERE revoked_at IS NULL AND status <> 'nie' AND expires_at > now() "
        "AND ride_date BETWEEN %s AND %s ORDER BY ride_date", (today, today + dt.timedelta(days=HORIZON_DAYS))).fetchall()
    conn.commit()
    plans, sent, org = {}, [], []
    base = W._WYPRAWA_PUBLIC_BASE.rstrip("/")
    for r in rows:
        r = dict(r)
        key = (r["route_id"], str(r["ride_date"]), r["start_time"], r["long_stops"], r["long_stop_min"])
        try:
            h, m = [int(x) for x in r["start_time"].split(":")]
            if r["ride_date"] == today and (now.hour * 60 + now.minute) >= h * 60 + m:
                continue                                    # jazda juz trwa / po starcie
        except Exception:
            pass
        if key not in plans:
            d = W._build_report_data(conn, key[0], key[1], key[2], key[3], key[4], ai=False, day_table=True)
            conn.commit()
            plans[key] = (RI.forecast_summary(d, key[2]), RI._clean_name((d.get("route") or {}).get("name")))
        summ, name = plans[key]
        old = r["fc_baseline"] if not isinstance(r["fc_baseline"], str) else json.loads(r["fc_baseline"])
        if not old:
            print("[bez punktu odniesienia -> zapis cichy]", r["email"], key[1])
            if not DRY:
                RI.set_baseline(conn, r["token"], summ)
            continue
        ch = RI.significant_changes(old, summ)
        if not ch:
            print("[bez istotnej zmiany]", r["email"], key[1])
            continue
        last = r["fc_notified_at"]
        if last and (now - last).total_seconds() < MIN_GAP_H * 3600:
            print("[zmiana, ale mail byl < %dh temu]" % MIN_GAP_H, r["email"], ch)
            continue
        print("[WYSLALBYM]" if DRY else "[WYSYLAM]", r["email"], key[1], ch)
        if DRY:
            continue
        html = RI.change_email_html(route_name=name, day=key[1], start=key[2], changes=ch, link=base + "/g/" + r["token"])
        msg = MIMEText(html, "html", "utf-8")
        msg["Subject"] = "Zmiana prognozy: %s \u2013 %s" % (name, RI.fmt_day(key[1]))
        msg["From"] = C.GMAIL_USER
        msg["To"] = r["email"]
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
                s.login(C.GMAIL_USER, C.GMAIL_APP_PASSWORD)
                s.send_message(msg)
            RI.set_baseline(conn, r["token"], summ, notified=True)
            sent.append(r["email"]); org.append((r["email"], key, ch))
        except Exception as e:  # noqa
            print("  blad wysylki:", e)
    if org and not DRY:
        lines = "".join("<li><b>%s</b> (%s, start %s): %s</li>" % (e_, k[1], k[2], "; ".join("%s: %s \u2192 %s" % c for c in ch_)) for e_, k, ch_ in org)
        msg = MIMEText("<p>QBot powiadomi\u0142 go\u015bci o zmianie prognozy:</p><ul>%s</ul>" % lines, "html", "utf-8")
        msg["Subject"] = "QBot: powiadomiono %d go\u015bci o zmianie prognozy" % len(org)
        msg["From"] = C.GMAIL_USER
        msg["To"] = C.GMAIL_USER
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
                s.login(C.GMAIL_USER, C.GMAIL_APP_PASSWORD)
                s.send_message(msg)
        except Exception as e:  # noqa
            print("blad podsumowania:", e)
    conn.close()
    print("zaproszen sprawdzonych: %d | planow policzonych: %d | wyslano: %d%s" % (len(rows), len(plans), len(sent), " (NA SUCHO)" if DRY else ""))


if __name__ == "__main__":
    main()
