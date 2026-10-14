# POGODA — sprawdzalność modeli (etap 1)

> Stan: 2026-10-14. Logika: `qbot_pogoda_verif.py`. Decyzja Michała 14.10: liczymy **całą Polskę** (62 stacje synoptyczne IMGW),
> na stronie dwa widoki: **u Ciebie** (stacje ≤ 100 km od punktu, waga 1/(1+d/50 km)) i **Polska**. Wynik ma docelowo sterować
> automatycznym przydziałem modeli (parametr × horyzont).

## Źródła
- **Pomiary (prawda):** IMGW synop.
  - Archiwum miesięczne `terminowe/synop/RRRR/RRRR_MM_s.zip` (`s_t_MM_RRRR.csv`, cp1250, co godzinę UTC). Kolumny wg
    `s_t_format.txt` (indeksy od 0): 1 nazwa, 2–5 data/godz., 25 FWR wiatr m/s, 27 PORW poryw, 29 TEMP, 37 WLGW wilg.,
    39 TPTR punkt rosy, 48 WO6G opad 6 h (00/06/12/18 UTC), 17/19 widzialność operator/automat [m].
  - Bieżące API `/api/data/synop` — tylko **ostatnia godzina** (temp, wiatr, wilg.; bez porywów i widzialności),
    `godzina_pomiaru` = UTC. Zapis co godzinę, nie nadpisuje archiwum.
  - Współrzędne: `/api/data/meteo` po nazwie; synop → stacja lotniskowa przez `ALIAS` (np. Warszawa → Okęcie), Koło ręcznie,
    Platforma (Bałtyk) pominięta → 61 stacji.
- **Prognozy:** Open-Meteo **Previous Runs API** — dla każdej godziny prognoza wydana 1/2/3 doby wcześniej
  (`*_previous_dayN`). Modele: HARMONIE DMI 2 km, HARMONIE KNMI 5,5 km, ICON-EU 7 km, ECMWF IFS 0,25°, GFS.
  Jedno zapytanie = wszystkie stacje naraz (lista współrzędnych).

## Tabele (`qbot_v2`)
`pogoda_stacja(klucz, nazwa, wmo, lat, lon)`, `pogoda_obs(stacja, ts, temp, wiatr, poryw, rh, rosa, opad6, widz, zrodlo)`,
`pogoda_prog(stacja, model, wyprz[doby], ts, temp, wiatr, poryw, opad)`. Klucz stacji = znormalizowana nazwa (łączy archiwum
z kodami 9-cyfrowymi i API z kodami WMO).

## Miary (`score`)
- temperatura, wiatr, poryw: **MAE** (średni błąd) i **bias** (+ = model zawyża), ważone odległością stacji;
- opad 6 h (próg 0,5 mm): **trafione / fałszywy alarm / przegapione**, trafność = trafione / (trafione+fałszywe+przegapione);
- osobno model × wyprzedzenie (1/2/3 doby).

## Uczciwe granice
- Archiwum IMGW pojawia się z opóźnieniem ok. miesiąca → bieżący miesiąc liczony z API (bez porywów/opadu).
- Wiatr ze stacji to średnia 10-min na 10 m; modele podają godzinowo — porównanie przybliżone.
- Radar (nowcast) — etap 2 (porównanie z mapą opadu OPERA).
