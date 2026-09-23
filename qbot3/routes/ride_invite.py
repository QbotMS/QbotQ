"""[G1] Zaproszenia gosci na jazde: osobny token na osobe + widok danych z BIALEJ LISTY.

Token (secrets.token_urlsafe(24) = 32 znaki) otwiera JEDNA trase + JEDEN dzien z planem
organizatora (godzina startu + przerwy zapisane przy zaproszeniu). Waznosc: do konca dnia
po jezdzie (Europe/Warsaw). Uniewaznienie = revoked_at. Licznik otwarc + ostatnie otwarcie.
Widok gosciem liczony warstwa planu BEZ AI (qbot_web._build_report_data ai=False, day_table=True);
komentarze odcinkow ryzyka z pakietu dnia, jesli jest. Zadne pole spoza guest_view() nie wychodzi.
"""
from __future__ import annotations

import datetime as _dt
import re
import secrets
import time
import threading

STATUSY = ("czeka", "tak", "nie")
_RL: dict = {}
_RL_LOCK = threading.Lock()
RL_MAX, RL_WIN_S = 120, 600          # max zapytan na token w oknie 10 min


def ensure(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS qbot_v2.ride_invite ("
                 "token text PRIMARY KEY, route_id text NOT NULL, ride_date date NOT NULL, "
                 "start_time text NOT NULL, long_stops int NOT NULL DEFAULT 0, long_stop_min int NOT NULL DEFAULT 0, "
                 "email text NOT NULL, status text NOT NULL DEFAULT 'czeka', "
                 "created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL, "
                 "revoked_at timestamptz, responded_at timestamptz, "
                 "open_count int NOT NULL DEFAULT 0, last_opened_at timestamptz)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ride_invite_uq ON qbot_v2.ride_invite (route_id, ride_date, lower(email))")
    conn.execute("ALTER TABLE qbot_v2.ride_invite ADD COLUMN IF NOT EXISTS sent_at timestamptz")
    conn.execute("ALTER TABLE qbot_v2.ride_invite ADD COLUMN IF NOT EXISTS sent_count int NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE qbot_v2.ride_invite ADD COLUMN IF NOT EXISTS fc_baseline jsonb")
    conn.execute("ALTER TABLE qbot_v2.ride_invite ADD COLUMN IF NOT EXISTS fc_baseline_at timestamptz")
    conn.execute("ALTER TABLE qbot_v2.ride_invite ADD COLUMN IF NOT EXISTS fc_notified_at timestamptz")


def _row(r):
    return dict(r) if isinstance(r, dict) else r


def rate_ok(token: str) -> bool:
    now = time.time()
    with _RL_LOCK:
        q = [t for t in _RL.get(token, []) if now - t < RL_WIN_S]
        if len(q) >= RL_MAX:
            _RL[token] = q
            return False
        q.append(now)
        _RL[token] = q
        return True


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def create_invites(conn, route_id: str, ride_date: str, start_time: str, long_stops: int,
                   long_stop_min: int, emails: list) -> list:
    """Jedno zaproszenie na adres. Istniejace (ta sama trasa+dzien+email) - aktualizuje plan,
    przywraca waznosc (zdejmuje uniewaznienie), TOKEN ZOSTAJE (wyslany link dalej dziala)."""
    ensure(conn)
    out = []
    for e in emails or []:
        e = str(e or "").strip()
        if not _EMAIL.match(e):
            out.append({"email": e, "ok": False, "blad": "zly adres"})
            continue
        tok = secrets.token_urlsafe(24)
        r = conn.execute(
            "INSERT INTO qbot_v2.ride_invite (token, route_id, ride_date, start_time, long_stops, long_stop_min, email, expires_at) "
            "VALUES (%s, %s, %s::date, %s, %s, %s, %s, "
            "  ((%s::date + 2)::timestamp AT TIME ZONE 'Europe/Warsaw') - interval '1 second') "
            "ON CONFLICT (route_id, ride_date, (lower(email))) DO UPDATE SET start_time=EXCLUDED.start_time, "
            "  long_stops=EXCLUDED.long_stops, long_stop_min=EXCLUDED.long_stop_min, "
            "  expires_at=EXCLUDED.expires_at, revoked_at=NULL "
            "RETURNING token, email, status, expires_at",
            (tok, route_id, ride_date, start_time, int(long_stops or 0), int(long_stop_min or 0), e, ride_date)).fetchone()
        r = _row(r)
        out.append({"email": r["email"], "ok": True, "token": r["token"], "status": r["status"],
                    "wazny_do": r["expires_at"].isoformat(timespec="minutes") if r["expires_at"] else None})
    conn.commit()
    return out


def get_valid(conn, token: str):
    """(zaproszenie, None) albo (None, powod). Nie zdradza, czy token w ogole istnial (ten sam komunikat)."""
    ensure(conn)
    if not token or len(token) < 20:
        return None, "nieprawidlowy link"
    r = conn.execute("SELECT *, (expires_at < now()) AS wygasl FROM qbot_v2.ride_invite WHERE token=%s", (token,)).fetchone()
    conn.commit()
    if not r:
        return None, "nieprawidlowy link"
    r = _row(r)
    if r.get("revoked_at"):
        return None, "link zostal wylaczony przez organizatora"
    if r.get("wygasl"):
        return None, "link wygasl"
    return r, None


def touch(conn, token: str):
    conn.execute("UPDATE qbot_v2.ride_invite SET open_count=open_count+1, last_opened_at=now() WHERE token=%s", (token,))
    conn.commit()


def set_rsvp(conn, token: str, status: str) -> bool:
    if status not in ("tak", "nie"):
        return False
    conn.execute("UPDATE qbot_v2.ride_invite SET status=%s, responded_at=now() WHERE token=%s", (status, token))
    conn.commit()
    return True


def revoke(conn, token: str) -> bool:
    ensure(conn)
    r = conn.execute("UPDATE qbot_v2.ride_invite SET revoked_at=now() WHERE token=%s AND revoked_at IS NULL RETURNING token",
                     (token,)).fetchone()
    conn.commit()
    return bool(r)


def list_invites(conn, route_id: str, ride_date: str | None = None) -> list:
    ensure(conn)
    q = ("SELECT token, email, ride_date, start_time, long_stops, long_stop_min, status, created_at, expires_at, "
         "revoked_at, responded_at, open_count, last_opened_at, sent_at, sent_count FROM qbot_v2.ride_invite WHERE route_id=%s")
    args = [route_id]
    if ride_date:
        q += " AND ride_date=%s"
        args.append(ride_date)
    rows = conn.execute(q + " ORDER BY ride_date, lower(email)", args).fetchall()
    conn.commit()
    out = []
    for r in rows:
        r = _row(r)
        out.append({k: (v.isoformat(timespec="minutes") if isinstance(v, _dt.datetime)
                        else v.isoformat() if isinstance(v, _dt.date) else v)
                    for k, v in r.items()})
    return out


# ---------- BIALA LISTA ----------
def _pick(d: dict, keys) -> dict:
    return {k: d.get(k) for k in keys if isinstance(d, dict) and k in d}


def _clean_name(n: str) -> str:
    return str(n or "Trasa").split(" \u00b7 ")[0].strip()[:160]


def guest_view(data: dict, invite: dict, geometry: list | None, pack: dict | None) -> dict:
    det = data.get("details") or {}
    rt, st, tm = data.get("route") or {}, data.get("start") or {}, data.get("time") or {}
    total_h = tm.get("total_h")
    meta = None
    try:
        h, m = [int(x) for x in str(invite["start_time"]).split(":")]
        mm = h * 60 + m + int(round(float(total_h) * 60))
        meta = "%02d:%02d" % ((mm // 60) % 24, mm % 60)
    except Exception:
        pass
    by = {}
    for r in ((pack or {}).get("dzien") or {}).get("ryzyka") or []:
        by[r.get("id")] = r
    risks = []
    for i, r in enumerate(((det.get("surface") or {}).get("risk") or [])):
        p = by.get("r%d" % (i + 1)) or {}
        risks.append({"a": r.get("a"), "b": r.get("b"), "km": r.get("km"), "k": r.get("k"),
                      "komentarz": p.get("komentarz"), "piach": p.get("piach"), "po_opadach": p.get("po_opadach")})
    ch = data.get("chart") or {}
    chart = {k: ch.get(k) for k in ("km_total", "ele", "ele_min", "ele_max", "weather", "eta", "wind")}
    chart["surface_cat"] = [_pick(x, ("a", "b", "k", "label")) for x in (ch.get("surface_cat") or [])]
    w = det.get("weather") or {}
    poi = det.get("poi") or {}
    return {
        "typ": "gosc", "wersja": 1,
        "trasa": {"nazwa": _clean_name(rt.get("name")), "dystans_km": rt.get("distance_km"), "przewyzszenie_m": rt.get("ascent_m"),
                  "geometria": geometry or []},
        "plan": {"data": str(invite["ride_date"]), "start": invite["start_time"],
                 "przerwy": {"liczba": invite["long_stops"], "min": invite["long_stop_min"]},
                 "meta": meta, "miejsce_startu": _pick(st, ("miejscowosc", "gmina", "powiat", "wojewodztwo")),
                 "czas": _pick(tm, ("moving_h", "total_h", "speed_gross_kmh", "speed_net_kmh", "stops_count", "stops_auto_min", "long_stops_min")),
                 "uwaga": "Plan organizatora - czasy liczone z jego tempa."},
        "wykres": chart,
        "pogoda": {"naglowek": data.get("weather_head"), "okna": w.get("windows"), "szczyt": w.get("peak"),
                   "slonce": w.get("slonce"), "ogolne": w.get("ogolne"), "etapy": w.get("etapy"), "uwagi": w.get("caveats"),
                   "prognoza_z": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="minutes")},
        "alerty": data.get("alerts") or [],
        "nawierzchnia": {"total_km": (det.get("surface") or {}).get("total_km"),
                         "udzial": (det.get("surface") or {}).get("by_cat"), "ryzyka": risks},
        "podjazdy": {"suma_w_gore_m": (det.get("climbs") or {}).get("ascent_m"),
                     "lista": [_pick(c, ("i", "a_km", "b_km", "length_m", "gain_m", "avg_pct", "max_pct", "severity", "segments"))
                               for c in ((det.get("climbs") or {}).get("list") or [])]},
        "zaopatrzenie": [{"rejon": x.get("area"), "km": x.get("q_km"),
                          "punkty": [_pick(p, ("km", "name", "cat", "miejscowosc", "hours", "open_status", "lat", "lon", "dist_m"))
                                     for p in (x.get("picks") or [])]} for x in (poi.get("resupply") or [])],
        "atrakcje": [_pick(a, ("km", "name", "desc", "miejscowosc", "lat", "lon", "dist_m"))
                     for a in ((poi.get("attractions") or {}).get("items") or [])],
        "gosc": {"email": invite["email"], "rsvp": invite["status"],
                 "wazny_do": invite["expires_at"].isoformat(timespec="minutes") if hasattr(invite.get("expires_at"), "isoformat") else invite.get("expires_at")},
    }



def mark_sent(conn, token: str):
    conn.execute("UPDATE qbot_v2.ride_invite SET sent_at=now(), sent_count=sent_count+1 WHERE token=%s", (token,))
    conn.commit()


# ---------- [G3] mail z zaproszeniem ----------
_DNI = ["poniedzia\u0142ek", "wtorek", "\u015broda", "czwartek", "pi\u0105tek", "sobota", "niedziela"]
_MIES = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "wrze\u015bnia",
         "pa\u017adziernika", "listopada", "grudnia"]


def fmt_day(iso: str) -> str:
    d = _dt.date.fromisoformat(str(iso)[:10])
    return "%s, %d %s" % (_DNI[d.weekday()], d.day, _MIES[d.month - 1])


def email_html(*, route_name: str, intro: dict | None, plan: dict, link: str, note: str | None = None) -> str:
    """Mail do goscia (jedna jazda). plan: {data, start, miejsce, przerwy_n, przerwy_min, meta, km, w_gore_m}."""
    import html as _h
    e = _h.escape
    title = (intro or {}).get("tytul") or route_name
    km = ("%.1f" % float(plan.get("km") or 0)).replace(".", ",")
    btn = ("font-family:Georgia,serif;font-size:16px;font-weight:bold;text-decoration:none;"
           "display:inline-block;padding:13px 24px;border-radius:9px;letter-spacing:.03em")
    rows = [("Kiedy", fmt_day(plan["data"])),
            ("Start", "%s%s" % (e(plan.get("start") or ""), (" &middot; " + e(plan["miejsce"])) if plan.get("miejsce") else "")),
            ("Trasa", "%s km &middot; +%s m" % (km, int(round(float(plan.get("w_gore_m") or 0)))))]
    if plan.get("przerwy_n"):
        rows.append(("Przerwy", "%d &times; %d min" % (plan["przerwy_n"], plan.get("przerwy_min") or 0)))
    if plan.get("meta"):
        rows.append(("Meta", "ok. %s <span style=\"color:#8c8168\">(plan organizatora)</span>" % e(plan["meta"])))
    trs = "".join('<tr><td style="padding:5px 12px 5px 0;color:#8c8168;font-size:13px;letter-spacing:.08em;text-transform:uppercase;'
                  'white-space:nowrap;vertical-align:top">' + k + '</td><td style="padding:5px 0;font-size:15.5px;color:#201c14">' + v + '</td></tr>'
                  for k, v in rows)
    body = ""
    if note:
        body += ('<div style="background:#efe7d4;border-left:3px solid #7c2b22;padding:10px 14px;margin:14px 0;font-size:15px;'
                 'line-height:1.55;font-style:italic">' + e(note).replace("\n", "<br>") + '</div>')
    if intro and intro.get("wprowadzenie"):
        body += '<p style="font-size:15.5px;line-height:1.6;margin:14px 0">' + e(intro["wprowadzenie"]) + '</p>'
    if intro and intro.get("czego_sie_spodziewac"):
        body += ('<div style="font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:#7c2b22;margin:16px 0 6px">Czego si\u0119 spodziewa\u0107</div>'
                 '<ul style="margin:0 0 6px 18px;padding:0;font-size:14.5px;line-height:1.55">'
                 + "".join("<li>" + e(x) + "</li>" for x in intro["czego_sie_spodziewac"]) + "</ul>")
    if intro and intro.get("warto_zobaczyc"):
        body += ('<div style="font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:#7c2b22;margin:16px 0 6px">Warto zobaczy\u0107</div>'
                 '<ul style="margin:0 0 6px 18px;padding:0;font-size:14.5px;line-height:1.55">'
                 + "".join("<li><b>" + e(x.get("nazwa") or "") + "</b> <span style=\"color:#8c8168\">(km " + str(x.get("km")).replace(".", ",")
                           + ")</span> &mdash; " + e(x.get("dlaczego") or "") + "</li>" for x in intro["warto_zobaczyc"]) + "</ul>")
    yes = '<a href="' + link + '?rsvp=tak" style="' + btn + ';background:#2f5d3a;color:#f5efe0">\u2714 JAD\u0118</a>'
    no = '<a href="' + link + '?rsvp=nie" style="' + btn + ';background:#efe7d4;color:#7c2b22;border:1px solid #cdbb99">Nie dam rady</a>'
    view = ('<a href="' + link + '" style="' + btn + ';background:#201c14;color:#f5efe0">Zobacz tras\u0119, pogod\u0119 i map\u0119 \u2192</a>')
    return ('<div style="max-width:600px;margin:0 auto;background:#f7f1e3;padding:26px 28px;font-family:Georgia,serif;color:#201c14;border:1px solid #d8ceb6">'
            '<div style="text-align:center;color:#7c2b22;letter-spacing:.28em;font-size:12px;text-transform:uppercase">\u2726 Zaproszenie na jazd\u0119 \u2726</div>'
            '<h1 style="text-align:center;font-size:28px;line-height:1.2;margin:10px 0 6px">' + e(title) + '</h1>'
            + ('<div style="text-align:center;color:#5a5140;font-size:14px">' + e(route_name) + '</div>' if title != route_name else "")
            + '<hr style="border:none;border-top:2px solid #6b6446;margin:16px 0">'
            '<table style="border-collapse:collapse;margin:0 0 6px">' + trs + '</table>' + body
            + '<div style="text-align:center;margin:22px 0 12px">' + view + '</div>'
            '<div style="text-align:center;margin:10px 0">' + yes + '&nbsp;&nbsp;&nbsp;' + no + '</div>'
            '<p style="text-align:center;color:#8c8168;font-size:12.5px;line-height:1.5;margin-top:14px">'
            'Pod linkiem zawsze aktualna prognoza, wiatr i alerty dla planowanej godziny oraz mapa z punktami zaopatrzenia. '
            'W za\u0142\u0105czniku plik <b>GPX</b> do nawigacji. Link jest osobisty i dzia\u0142a do dnia po je\u017adzie.</p>'
            '<hr style="border:none;border-top:1px solid #d8ceb6;margin:16px 0 8px">'
            '<div style="text-align:center;color:#8c8168;font-size:11px;letter-spacing:.2em;text-transform:uppercase">QBot &middot; Zaproszenie na jazd\u0119</div></div>')



# ---------- [G4] skrot prognozy + wykrywanie istotnej zmiany ----------
def forecast_summary(d: dict, start: str) -> dict:
    """Skrot prognozy dla planu (dane z warstwy planu, bez AI)."""
    import math
    det = d.get("details") or {}
    w = det.get("weather") or {}
    win = w.get("windows") or []
    fe = [float(x["feels"]) for x in win if x.get("feels") is not None]
    pr = [(x.get("okno"), float(x.get("opad_prob") or 0), float(x.get("opad_mm") or 0)) for x in win]
    wind = [math.hypot(float(x.get("w_along") or 0), float(x.get("w_cross") or 0)) for x in ((d.get("chart") or {}).get("weather") or [])]
    wb = [float(x["wbgt"]) for x in win if x.get("wbgt") is not None]
    wet = [p[0] for p in pr if p[1] >= 40]
    tm = d.get("time") or {}
    meta = None
    try:
        h, m = [int(x) for x in str(start).split(":")]
        mm = h * 60 + m + int(round(float(tm.get("total_h")) * 60))
        meta = "%02d:%02d" % ((mm // 60) % 24, mm % 60)
    except Exception:
        pass
    return {"feels_min": min(fe) if fe else None, "feels_max": max(fe) if fe else None,
            "wiatr_max": round(max(wind), 1) if wind else None,
            "deszcz_max": max((p[1] for p in pr), default=0.0), "deszcz_mm": round(sum(p[2] for p in pr), 1),
            "deszcz_od": wet[0] if wet else None,
            "burza": any(str(a.get("typ") or "").startswith("burz") for a in (d.get("alerts") or [])),
            "wbgt_max": max(wb) if wb else None, "meta": meta}


def _fmt_c(x):
    return "%s\u00b0C" % ("%.0f" % x if x is not None else "?")


def significant_changes(old: dict, new: dict) -> list:
    """Lista zmian 'bylo -> jest' (pusta = brak istotnej zmiany). Progi: docs w module guest_forecast_watch."""
    if not old or not new:
        return []
    ch = []
    def dv(k):
        a, b = old.get(k), new.get(k)
        return (None if a is None or b is None else b - a)
    if (dv("feels_min") is not None and abs(dv("feels_min")) >= 3) or (dv("feels_max") is not None and abs(dv("feels_max")) >= 3):
        ch.append(("odczuwalna", "%s\u2013%s" % (_fmt_c(old.get("feels_min")), _fmt_c(old.get("feels_max"))),
                   "%s\u2013%s" % (_fmt_c(new.get("feels_min")), _fmt_c(new.get("feels_max")))))
    if dv("wiatr_max") is not None and abs(dv("wiatr_max")) >= 3:
        ch.append(("wiatr", "do %.0f m/s" % old["wiatr_max"], "do %.0f m/s" % new["wiatr_max"]))
    a, b = float(old.get("deszcz_max") or 0), float(new.get("deszcz_max") or 0)
    mm_a, mm_b = float(old.get("deszcz_mm") or 0), float(new.get("deszcz_mm") or 0)
    if (a < 40) != (b < 40) or abs(b - a) >= 30 or abs(mm_b - mm_a) >= 3:
        ch.append(("deszcz", "%.0f%%%s" % (a, (", %s mm" % ("%.1f" % mm_a).replace(".", ",")) if mm_a else ""),
                   "%.0f%%%s%s" % (b, (", %s mm" % ("%.1f" % mm_b).replace(".", ",")) if mm_b else "", (" (od ok. %s)" % new["deszcz_od"]) if new.get("deszcz_od") else "")))
    if bool(old.get("burza")) != bool(new.get("burza")):
        ch.append(("burza", "nie" if not old.get("burza") else "mo\u017cliwa", "mo\u017cliwa" if new.get("burza") else "ju\u017c nie"))
    wa, wbb = old.get("wbgt_max"), new.get("wbgt_max")
    if wa is not None and wbb is not None and any((wa < t) != (wbb < t) for t in (23, 26)):
        ch.append(("upa\u0142 (WBGT)", _fmt_c(wa), _fmt_c(wbb)))
    return ch


def set_baseline(conn, token: str, summ: dict, notified: bool = False):
    import json as _j
    conn.execute("UPDATE qbot_v2.ride_invite SET fc_baseline=%s::jsonb, fc_baseline_at=now()" + (", fc_notified_at=now()" if notified else "")
                 + " WHERE token=%s", (_j.dumps(summ, ensure_ascii=False), token))
    conn.commit()


def change_email_html(*, route_name: str, day: str, start: str, changes: list, link: str) -> str:
    import html as _h
    e = _h.escape
    rows = "".join('<tr><td style="padding:6px 12px 6px 0;color:#8c8168;font-size:13px;text-transform:uppercase;letter-spacing:.06em">'
                   + e(k) + '</td><td style="padding:6px 10px 6px 0;color:#8c8168;text-decoration:line-through">' + e(a)
                   + '</td><td style="padding:6px 0;font-weight:bold;color:#201c14">\u2192 ' + e(b) + '</td></tr>' for k, a, b in changes)
    btn = "font-family:Georgia,serif;font-size:16px;font-weight:bold;text-decoration:none;display:inline-block;padding:12px 22px;border-radius:9px;background:#201c14;color:#f5efe0"
    return ('<div style="max-width:600px;margin:0 auto;background:#f7f1e3;padding:24px 26px;font-family:Georgia,serif;color:#201c14;border:1px solid #d8ceb6">'
            '<div style="text-align:center;color:#7c2b22;letter-spacing:.24em;font-size:12px;text-transform:uppercase">Zmiana prognozy</div>'
            '<h1 style="text-align:center;font-size:24px;margin:10px 0 4px">' + e(route_name) + '</h1>'
            '<div style="text-align:center;color:#5a5140;font-size:14.5px">' + e(fmt_day(day)) + ' &middot; start ' + e(start) + '</div>'
            '<hr style="border:none;border-top:2px solid #6b6446;margin:16px 0">'
            '<p style="font-size:15px;line-height:1.55;margin:0 0 8px">Prognoza na nasz\u0105 jazd\u0119 wyra\u017anie si\u0119 zmieni\u0142a:</p>'
            '<table style="border-collapse:collapse;font-size:15px;margin:0 0 14px">' + rows + '</table>'
            '<div style="text-align:center;margin:18px 0 8px"><a href="' + link + '" style="' + btn + '">Aktualna pogoda i trasa \u2192</a></div>'
            '<p style="text-align:center;color:#8c8168;font-size:12px;margin-top:12px">Wiadomo\u015b\u0107 automatyczna z QBota. Kolejna tylko przy nast\u0119pnej istotnej zmianie.</p></div>')
