"""Zima 2025 (listopad-grudzien) - uzupelnienie wiedzy o odziezy z raportu GPT Michala. Decyzja Michala 2026-10-13:
TO JEST UZUPELNIENIE, NIE PRIORYTET i NIE DETERMINANT doboru ubioru.

Robi (idempotentnie, znacznik ZNACZNIK):
1) kopia data/garage.db -> data/garage.db.bak-20261013 (tylko gdy jej nie ma),
2) dodaje do Garazu Castelli Cold Days 2nd Layer Shirt (z maila BIKE24 18.10.2025) - jesli jeszcze nie ma,
3) dopisuje krotkie obserwacje na KONIEC pola notes wybranych rzeczy (widoczne w Garazu; doradca czyta notatke
   obcieta do 220 znakow, wiec pelna wiedza jest w rozdziale 11 docs/OUTFIT_ADVISOR_RULES.md),
4) dopisuje rozdzial 11 do docs/OUTFIT_ADVISOR_RULES.md,
5) FIX: Rapha Peaked Merino Hat (65) - usuwa stare 'GLOWNA zimowa czapka' (regex _PLUS2 dawal +2), bo Michal nie przepada
   (daszek opada na oczy).
W dopiskach NIE ma zakresow 'a...b °C' (regex _TEMP doradcy) ani slow-kluczy statusu (GLOWNY, ULUBIONY, RZADKO...).
Mapowanie nazw z raportu potwierdzone przez Michala 2026-10-13: Assos kominiarka = Winter Face Mask EVO (79),
PEdALED Winter/Winter Alpha = Element Alpha Gloves (82), Odyssey Insulated Jacket = Odyssey Winter Jacket (30),
AmCycling Winter = Ultra Cargo Pants (53). Buff Windstopper - oddany, pominiety.
Uzycie: .venv/bin/python3 scripts/garage_winter2025_20261013.py [--dry]
"""
import os
import shutil
import sqlite3
import sys

DB = "/opt/qbot/app/data/garage.db"
BAK = DB + ".bak-20261013"
RULES = "/opt/qbot/app/docs/OUTFIT_ADVISOR_RULES.md"
ZNACZNIK = "Zima 2025:"
DRY = "--dry" in sys.argv

NOTES = {
    23: "Zima 2025: na Brynje+PowerDry pod Trail Hoodie przy Z2-Z3 za cieplo i mokro (27.11 odczuwalna -4 st., 03.12 +2 st.).",
    3: "Zima 2025: Brynje + PowerDry byly baza najlepszych zestawow (29.11 5/5 przy -1,6 st.); problemem byla suma warstw nad nia.",
    6: "Zima 2025: baza najlepszych zimowych zestawow (z PowerDry); sama nie zapewnia suchosci, gdy nad nia 2-3 warstwy.",
    1: "Zima 2025: tylko z Trail Hoodie przy -1,8 st. tulow 2/5 - za slabo (20.11).",
    39: "Zima 2025: shell w wiekszosci zimowych zestawow; gdy pod spodem 2-3 warstwy, zatrzymuje wilgoc; rozpiecie pomaga.",
    30: "Zima 2025: z Odyssey Insulated Pants 5/5 przy -5 st. w sniegu (rozpieta); przy -1 st. za cieplo (28.11).",
    46: "Zima 2025: 5/5 przy -5 st. (23.11); przy -1 st. chwilami za cieplo (28.11).",
    16: "Zima 2025: Brynje+PowerDry+Coefficient+Trail Hoodie 5/5 przy -1,6 st., spokojnie, bez wiatru (29.11); przy +3/+4 st. i 2:39 h po cieplej stronie, mokry brzuch (06.12).",
    28: "Zima 2025: liner + Coefficient Pants + Fernflow 5/5 przy -1,6 st. (29.11); 4/5 przy +2 st. w Z3 (03.12).",
    235: "Zima 2025: z Brubeck DRY Leggings i linerem przy -4 st. chlodno w udach, 3/5 (27.11).",
    53: "Zima 2025: same, bez drugiej warstwy, przy +1 st. 3/5 - wychlodzone uda, mokra wkladka (18.11).",
    44: "Zima 2025: z Dynatec 3/4 pod spodem 4/5 przy -1,8 st. (20.11).",
    56: "Zima 2025: liner + Core Winter + Trail Lightweight przy +3/+4 st., 2:39 h: 4/5, wszystko mokrawe - podwojne szelki zatrzymuja pot (06.12).",
    99: "Zima 2025: z Assos Ultraz P1 5/5 (-1,6 st.); z PEdALED Primaloft od 2/5 do 5/5 (gorzej przy mokrej skarpecie); z Thermolite 2/5.",
    96: "Zima 2025: z MW701 5/5 przy -1,6 st. (29.11) - najlepiej udokumentowany zestaw na stopy.",
    97: "Zima 2025: z MW701 wyniki od 2/5 do 5/5 - zalezne od wilgoci skarpety, tempa i warunkow; marzly palce i przod stopy.",
    94: "Zima 2025: z MW701 przy +1 st. zimne palce od polowy jazdy, 2/5 (18.11).",
    105: "Zima 2025: z Rapha Pro Merino bardzo cieplo przy -1 st.; ucisk z przodu przy kostkach (28.11).",
    82: "Zima 2025: 5/5 w kolejnych jazdach (27-29.11, 06.12) - najbardziej przewidywalny element zimowy.",
    88: "Zima 2025: przy +2 st. 4/5 - na starcie chlodno, potem dobrze (03.12).",
    79: "Zima 2025: 5/5 przy -5 st. w sniegu (23.11) i przy -1,6 st. (29.11).",
    65: "Michal 2026-10-13: nie przepada - daszek opada na oczy; przy rownych szansach wybierz inna czapke. Zima 2025 termicznie 4-5/5.",
}
# (id, stary tekst, nowy tekst) - jednorazowe poprawki starych notatek
FIX = [(65, "G\u0141\u00d3WNA zimowa czapka", "zimowa czapka z daszkiem")]

NEW = {
    "category": "Termika", "brand": "Castelli", "model": "Cold Days 2nd Layer Shirt", "size": "XXL",
    "color": "rock blue 405", "purchase_date": "2025-10-18", "purchase_price": 70.28, "condition": "Good",
    "notes": "Polartec Alpha (wg Michala) | warstwa posrednia, dlugi rekaw | BIKE24 18.10.2025, 70,28 EUR | "
             "Zima 2025: na Core Seamless pod Trail Hoodie przy +1 st., RPE 5-6 - za cieplo, mokre plecy; rozpiecie pomagalo (18.11).",
    "season": "zima,przejsciowy", "fabric": "techniczna", "g_body": "gora", "g_len": "dlugi",
}

RULES_ADD = """

## 11. Uzupelnienie: zima 2025 (NISKI PRIORYTET)
Dodane 2026-10-13 z raportu Michala (jazdy 18.11-06.12.2025, oceny 1-5 na strefe). To UZUPELNIENIE wiedzy, NIE
determinant: przegrywa ze swiezymi jazdami, audytem i notatkami Garazu; uzywaj, gdy brak nowszych danych w podobnych
warunkach albo do uzasadnienia przy rownych szansach. Temperatury = odczuwalna z Karoo/pogody (orientacyjnie
jak temperatura do ubioru). Przewaznie jazdy ~1 h, RPE 4-6, Z2-Z3.
- Glowny wzorzec: czesciej za cieplo i MOKRO na tulowiu niz za zimno. Przy Z2-Z3 ogranicz liczbe warstw izolacyjnych
  na tulowiu: lekka baza + JEDNA izolacja + shell z mozliwoscia rozpiecia.
- Brynje Mesh + PowerDry (6, 3) - dobra baza; problemem byla suma warstw nad nia, nie baza.
- Albion Primaloft Active Hoodie (23) jako dodatkowa warstwa pod Trail Hoodie (39) przy Z2-Z3: za cieplo i mokro
  (-4 i +2 st.). Castelli 2nd Layer (nowa) na Core Seamless pod Trail Hoodie przy +1 st.: za cieplo, mokre plecy.
- Brubeck Active Wool LS (1) + sam Trail Hoodie przy -1,8 st.: tulow 2/5 - za slabo.
- Najlepszy zestaw serii (5/5 wszystkie strefy, -1,6 st., wiatr 1 m/s, SPOKOJNIE): Brynje + PowerDry + Coefficient LT (16)
  + Trail Hoodie; liner + Coefficient Pants (28) + Fernflow (235); MW701 (99) + Assos Ultraz P1 (96); Element Alpha (82);
  Assos Face Mask (79). Przy wyzszym tempie lub wietrze mniej izolacji.
- Komplet Odyssey Winter Jacket (30) + Odyssey Insulated Pants (46): 5/5 przy -5 st. w sniegu; przy -1 st. za cieplo.
  Pelna izolacja nog ma sens od ok. -4 st. w dol.
- Nogi: przy ok. 0 st. sama AM Cycling Ultra Cargo (53) za malo (uda); Fernflow + Brubeck DRY przy -4 st. chlodno w udach.
  Uda wymagaja izolacji, nie tylko oslony od wiatru. Podwojne szelki (liner + Core Winter 56) przy +3/+4 st. zatrzymuja pot.
- Stopy - najbardziej zmienna strefa: MW701 + PEdALED Primaloft (97) od 2/5 do 5/5 (gorzej przy mokrej skarpecie i ok. 0 st.),
  MW701 + Thermolite (94) 2/5 przy +1 st. Najpewniejsze: MW701 + Assos Ultraz P1. Lake (105) bardzo cieple, ucisk przy kostkach.
- Dlonie: Element Alpha (82) powtarzalnie 5/5. Sportful NoRain (88) przy +2 st. chlodno na starcie.
- Glowa: czapka/kominiarka/komin dzialaja; zabudowany komin na twarz utrudnia picie i jedzenie.
- Preferencja Michala: Rapha Peaked Merino Hat (65) - nie przepada, daszek opada na oczy; przy rownych szansach inna czapka.
"""


def main():
    if not DRY and not os.path.exists(BAK):
        shutil.copy2(DB, BAK)
        print("backup:", BAK)
    g = sqlite3.connect(DB, timeout=5)
    try:
        ex = g.execute("SELECT id FROM gear WHERE brand='Castelli' AND model=?", (NEW["model"],)).fetchone()
        if ex:
            print("Castelli 2nd Layer juz jest: id", ex[0])
        else:
            keys = list(NEW)
            if not DRY:
                cur = g.execute("INSERT INTO gear (%s, active) VALUES (%s, 1)" % (", ".join(keys), ",".join("?" * len(keys))),
                                [NEW[k] for k in keys])
                print("dodano Castelli 2nd Layer: id", cur.lastrowid)
            else:
                print("[dry] dodalbym Castelli 2nd Layer")
        for gid, add in NOTES.items():
            r = g.execute("SELECT brand, model, notes FROM gear WHERE id=?", (gid,)).fetchone()
            if not r:
                print("BRAK id", gid)
                continue
            old = r[2] or ""
            if ZNACZNIK in old or add[:20] in old:
                print("pomijam (juz jest)", gid, r[0], r[1])
                continue
            new = (old.rstrip() + " | " + add) if old.strip() else add
            if not DRY:
                g.execute("UPDATE gear SET notes=? WHERE id=?", (new, gid))
            print("notatka", gid, r[0], r[1])
        for gid, a, b in FIX:
            r = g.execute("SELECT notes FROM gear WHERE id=?", (gid,)).fetchone()
            if r and r[0] and a in r[0]:
                if not DRY:
                    g.execute("UPDATE gear SET notes=? WHERE id=?", (r[0].replace(a, b), gid))
                print("poprawka", gid, repr(a), "->", repr(b))
            else:
                print("poprawka pominieta (brak tekstu)", gid)
        if not DRY:
            g.commit()
    finally:
        g.close()
    txt = open(RULES, encoding="utf-8").read()
    if "## 11. Uzupelnienie: zima 2025" in txt:
        print("rozdzial 11 juz jest")
    elif not DRY:
        with open(RULES, "w", encoding="utf-8") as f:
            f.write(txt.rstrip("\n") + RULES_ADD)
        print("dopisano rozdzial 11")
    else:
        print("[dry] dopisalbym rozdzial 11")


if __name__ == "__main__":
    main()
