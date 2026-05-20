#!/usr/bin/env python3
"""Decision support rules shared by QBot reports."""
from __future__ import annotations

from datetime import date, timedelta

from qbot_readiness import evaluate_readiness


def _num(value, default=None):
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _avg(values):
    vals = [_num(v) for v in values if _num(v) is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _date_dmy(value):
    if not value:
        return None
    parts = str(value).split("-")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}"
    return str(value)


def _event_text(event):
    return " ".join(str(event.get(k) or "") for k in ("name", "category", "description")).lower()


def _planned_training(events):
    for event in events or []:
        text = _event_text(event)
        if any(x in text for x in ("trening", "workout", "z2", "z3", "z4", "interval", "ride", "jazd")):
            return event
    return (events or [None])[0]


def build_daily_coach(data, future_events=None):
    """Build morning decision, plan adjustment, risk alerts, fuel guidance and event prep."""
    s = data.get("sen", {}) or {}
    r = data.get("regeneracja", {}) or {}
    f = data.get("forma", {}) or {}
    b = data.get("bilans", {}) or {}
    trips = data.get("wyjazdy", []) or []
    future_events = future_events or []

    readiness = evaluate_readiness(
        hrv=r.get("hrv"),
        hrv_norm=r.get("hrv_norma"),
        body_battery=r.get("body_battery_rano"),
        sleep_hours=None if data.get("brak_danych_snu") else s.get("czas_h"),
        form=f.get("swiezosc"),
        illness_context=bool(r.get("choroba") or r.get("injury")),
        resting_hr=r.get("tetno_spoczynkowe"),
    )

    planned = _planned_training(future_events)
    planned_name = planned.get("name") if planned else None
    avg_balance = b.get("srednia_7d_kcal")
    yesterday_balance = b.get("wczoraj_kcal")
    body_battery = _num(r.get("body_battery_rano"))
    hrv_delta = readiness.hrv_delta
    sleep_h = _num(s.get("czas_h"))
    freshness = _num(f.get("swiezosc"))

    if readiness.verdict == "TAK":
        action = "jedź zgodnie z planem"
        duration = "60-90 min"
        intensity = "Z2 albo plan dnia"
    elif readiness.verdict == "OGRANICZ":
        action = "skróć trening o 30-40%"
        duration = "30-60 min"
        intensity = "Z1-Z2, bez akcentu"
    else:
        action = "zamień trening na regenerację"
        duration = "20-40 min"
        intensity = "spacer, mobilność albo bardzo lekka Z1"

    reasons = []
    if hrv_delta is not None:
        reasons.append(f"HRV {hrv_delta:+.1f} ms względem normy")
    if body_battery is not None:
        reasons.append(f"Body Battery rano {int(body_battery)}")
    if sleep_h is not None:
        reasons.append(f"sen {sleep_h:.1f} h")
    if freshness is not None:
        reasons.append(f"świeżość {freshness:.1f}")

    decision = {
        "verdict": readiness.verdict,
        "color": readiness.color,
        "action": action,
        "duration": duration,
        "intensity": intensity,
        "planned": planned_name,
        "why": reasons[:4],
        "note": readiness.note,
    }

    alerts = []
    if hrv_delta is not None and hrv_delta < -5:
        alerts.append("HRV jest wyraźnie pod normą: nie rób dziś mocnego akcentu.")
    if body_battery is not None and body_battery < 45:
        alerts.append("Body Battery rano jest niskie: skróć trening albo przełóż jakość.")
    if sleep_h is not None and sleep_h < 6:
        alerts.append("Sen poniżej 6 h: utrzymaj tylko niską intensywność.")
    if avg_balance is not None and avg_balance < -500:
        alerts.append("Średni deficyt 7 dni jest zbyt duży jak na regularny trening.")
    if yesterday_balance is not None and yesterday_balance < -800:
        alerts.append("Wczorajszy deficyt jest głęboki: uzupełnij paliwo przed jazdą.")

    plan = []
    for offset in range(1, 4):
        d = date.today() + timedelta(days=offset)
        event = next((e for e in future_events if e.get("date") == d.isoformat()), None)
        label = event.get("name") if event else "brak wpisu w kalendarzu"
        if readiness.verdict == "ODPUSC" and offset == 1:
            suggestion = "Zostaw rest day lub 30-45 min Z1, jeśli HRV odbije."
        elif readiness.verdict == "OGRANICZ" and offset == 1:
            suggestion = "Przenieś mocny akcent, zrób 45-60 min Z2."
        elif avg_balance is not None and avg_balance < -500:
            suggestion = "Nie dokładaj objętości bez poprawy jedzenia."
        else:
            suggestion = "Możesz trzymać plan, jeśli poranne HRV i sen będą stabilne."
        plan.append({"date": d.isoformat(), "event": label, "suggestion": suggestion})

    weight_text = "brak świeżej wagi"
    if b.get("waga_dzis_kg") is not None:
        if b.get("waga_dzis_fallback") and b.get("waga_dzis_date"):
            weight_text = f"{b.get('waga_dzis_kg')} kg, ostatni pomiar z {_date_dmy(b.get('waga_dzis_date'))}"
        else:
            weight_text = f"{b.get('waga_dzis_kg')} kg"

    fuel = {
        "weight": weight_text,
        "daily": "Dołóż węgle przed treningiem i po nim." if readiness.verdict != "ODPUSC" else "Nie tnij kalorii agresywnie w dzień regeneracji.",
        "carbs": "60-90 g/h na dłuższej jeździe; 30-45 g/h wystarczy przy krótkiej Z2.",
        "warning": "Deficyt jest za głęboki." if avg_balance is not None and avg_balance < -500 else None,
    }

    trip = trips[0] if trips else None
    event = None
    if trip:
        days_to = trip.get("days_to")
        if days_to is not None and days_to <= 14:
            focus = "taper, sen, paliwo i sprawdzenie listy pakowania"
        elif days_to is not None and days_to <= 35:
            focus = "ostatnie długie jazdy i test żywienia"
        else:
            focus = "regularny blok bez nadrabiania na siłę"
        event = {
            "name": trip.get("name"),
            "days_to": days_to,
            "focus": focus,
            "checklist": [
                "potwierdź opony, torby, światła i ładowanie",
                "zrób jedną jazdę testową z pełnym zestawem",
                "utrzymaj sen i jedzenie jako priorytet w ostatnim tygodniu",
            ],
        }

    return {
        "decision": decision,
        "plan_adjustment": plan,
        "risk_alerts": alerts[:5],
        "fuel": fuel,
        "event": event,
    }


def build_ride_lesson(protocol, data=None):
    """Return one concrete lesson after a ride, without gear diagnostics."""
    data = data or {}
    coach = protocol.get("coach", {}) or {}
    health = protocol.get("health", {}) or {}
    split = (protocol.get("long_rides", {}) or {}).get("split", {}) or {}
    act = data.get("aktywnosc", {}) or {}

    if coach.get("decoupling_bad"):
        return {
            "title": "Kontroluj narastanie tętna",
            "text": "Najważniejsza lekcja: tempo było zbyt kosztowne metabolicznie. Następnym razem zacznij pierwsze 20-30 minut spokojniej i pilnuj jedzenia od początku.",
        }
    if split.get("available") and _num(split.get("power_fade_pct")) is not None and _num(split.get("power_fade_pct")) < -8:
        return {
            "title": "Utrzymaj moc w drugiej połowie",
            "text": "Moc w drugiej połowie wyraźnie spadła. Następnym razem zacznij bardziej zachowawczo i zaplanuj węgle zanim pojawi się spadek energii.",
        }
    if health.get("verdict") == "ODPUSC":
        return {
            "title": "Nie przykrywaj zmęczenia ambicją",
            "text": "Kontekst zdrowotny był słaby. Najlepsza poprawka na kolejny raz to skrócić jazdę albo zamienić ją na Z1, zanim regeneracja zacznie hamować cały tydzień.",
        }
    moving_h = (_num(act.get("moving_time"), 0) or 0) / 3600
    kcal = _num(act.get("calories") or act.get("icu_total_work"))
    if moving_h >= 2 and not kcal:
        return {
            "title": "Zapisz paliwo z trasy",
            "text": "Jazda była na tyle długa, że warto dopisać w notatce ilość węgli i płynów. Bez tego trudniej ocenić, czy końcówka wynikała z tempa czy z paliwa.",
        }
    return {
        "title": "Jedna rzecz na następną jazdę",
        "text": "Powtórz podobny trening z jednym kontrolowanym celem: równe tempo przez pierwszą połowę i bez dokładania intensywności, jeśli HR rośnie szybciej niż moc.",
    }


def build_weekly_review(wellness, activities, trips=None):
    wellness = wellness or []
    activities = activities or []
    trips = trips or []
    balances = []
    hrv_values = []
    sleep_hours = []
    weights = []
    for w in wellness:
        if _num(w.get("hrv")) is not None:
            hrv_values.append(w.get("hrv"))
        if _num(w.get("sleepSecs")) is not None:
            sleep_hours.append(_num(w.get("sleepSecs")) / 3600)
        if _num(w.get("weight")) is not None:
            weights.append((w.get("id"), _num(w.get("weight"))))
        comments = str(w.get("comments") or "")
        eaten = burned = None
        for line in comments.splitlines():
            if "Zjedzone:" in line:
                eaten = _num(line.split("Zjedzone:", 1)[1].split("kcal", 1)[0].strip())
            if "Spalone:" in line:
                burned = _num(line.split("Spalone:", 1)[1].split("kcal", 1)[0].strip())
        if eaten is not None and burned is not None:
            balances.append(eaten - burned)

    total_hours = round(sum((_num(a.get("moving_time"), 0) or 0) for a in activities) / 3600, 1)
    total_tss = round(sum((_num(a.get("icu_training_load"), 0) or 0) for a in activities))
    long_rides = [
        a for a in activities
        if (_num(a.get("moving_time"), 0) or 0) >= 3 * 3600 or (_num(a.get("distance"), 0) or 0) >= 80000
    ]
    avg_balance = round(sum(balances) / len(balances)) if balances else None
    avg_hrv = _avg(hrv_values)
    avg_sleep = _avg(sleep_hours)
    weight_trend = None
    if len(weights) >= 2:
        weight_trend = round(weights[-1][1] - weights[0][1], 1)

    blockers = []
    if avg_sleep is not None and avg_sleep < 6.5:
        blockers.append("sen był za krótki")
    if avg_balance is not None and avg_balance < -500:
        blockers.append("deficyt kalorii był za głęboki")
    if not long_rides:
        blockers.append("brak długiej jazdy")
    if total_hours < 4:
        blockers.append("niska objętość tygodnia")

    next_focus = "utrzymaj plan i pilnuj regeneracji"
    if blockers:
        next_focus = f"najpierw popraw: {', '.join(blockers[:2])}"
    if trips:
        trip = trips[0]
        if trip.get("days_to") is not None and trip.get("days_to") <= 21:
            next_focus = "priorytet: event, taper, paliwo i sen"

    return {
        "summary": {
            "hours": total_hours,
            "tss": total_tss,
            "activities": len(activities),
            "long_rides": len(long_rides),
            "avg_hrv": avg_hrv,
            "avg_sleep": avg_sleep,
            "avg_balance": avg_balance,
            "weight_trend": weight_trend,
        },
        "what_worked": [
            "regularność aktywności" if activities else "brak aktywności do oceny",
            "dane regeneracji są dostępne" if hrv_values or sleep_hours else "uzupełnij dane snu i HRV",
        ],
        "blockers": blockers or ["brak dużej czerwonej flagi w danych"],
        "next_week_focus": next_focus,
    }
