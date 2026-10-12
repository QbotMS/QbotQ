"""Forma -> Trendy: analiza AI zaznaczonych serii w zaznaczonym okresie (2026-10-12).

POST /api/trendy/ai  {from, to, series:[{name, unit?, values:[...]}], corr:[{a,b,r,lag,n}], ill:[...], rides:[...]}
Korelacje i statystyki LICZY PRZEGLADARKA (forma2-data.js); AI tylko je interpretuje. Wynik NIE jest zapisywany
(kazdy zestaw serii/okres to inna analiza) - panel boczny w Trendach.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

PROMPT = (
    "Jesteś trenerem kolarskim i analitykiem danych (kolarz gravel ~104 kg, redukcja wagi, trening z planem). "
    "Dostajesz POLICZONE dane z wykresów QBot: okres, dzienne wartości wybranych serii, korelacje Pearsona (także z opóźnieniem 0–3 dni), "
    "infekcje i dni z jazdą. NIE licz własnych liczb, nie wymyślaj danych, opieraj się wyłącznie na tym, co dostałeś. "
    "Korelacja |r| < 0,3 = brak sensownego związku; 0,3–0,5 umiarkowana; > 0,5 silna; przy n < 15 zaznacz niską pewność. "
    "Korelacja to nie przyczyna – mów ostrożnie. Prosty polski, bez żargonu. "
    "Zwróć WYŁĄCZNIE JSON: {\"podsumowanie\": \"2-3 zdania\", \"zaleznosci\": [\"...\"], \"trendy\": [\"...\"], "
    "\"wnioski\": [\"...\"], \"uwagi\": [\"...\"]} – listy maks. 4 krótkie punkty; uwagi = ograniczenia danych.")


def build_router(current_user, owner_user):
    r = APIRouter(prefix="/api/trendy")

    @r.post("/ai")
    async def trend_ai(request: Request):
        if not current_user(request):
            raise HTTPException(status_code=401, detail="unauthorized")
        if not owner_user(request):
            raise HTTPException(status_code=403, detail="tylko odczyt (sesja demo)")
        try:
            b = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="zły JSON")
        ser = b.get("series") or []
        if not ser:
            raise HTTPException(status_code=400, detail="brak zaznaczonych serii")
        if len(ser) > 24 or any(len(s.get("values") or []) > 800 for s in ser):
            raise HTTPException(status_code=400, detail="za dużo danych (maks. 24 serie × 800 dni)")
        payload = {"okres": [b.get("from"), b.get("to")], "dni": b.get("days"), "serie": ser[:24],
                   "korelacje": (b.get("corr") or [])[:30], "korelacje_opis": b.get("corr_note"), "infekcje": b.get("ill") or [], "dni_z_jazda": (b.get("rides") or [])[:400]}
        import qbot_food_log as F   # wspolne wywolanie Claude -> JSON (jak w Jedzeniu)
        try:
            j = F._ai_json(PROMPT, [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}])
        except Exception as ex:
            raise HTTPException(status_code=502, detail="AI niedostępne: %s" % type(ex).__name__)
        out = {"podsumowanie": str(j.get("podsumowanie") or "")[:800]}
        for k in ("zaleznosci", "trendy", "wnioski", "uwagi"):
            out[k] = [str(x)[:400] for x in (j.get(k) or [])][:4]
        return out

    return r
