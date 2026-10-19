# Profile jazd w modelu czasu przejazdu (2026-10-19)

Decyzje Michała (czat 19.10.2026). Kod: `qbot3/routes/ride_profiles.py`, `qbot_route_time_tools.py`,
konfiguracja: sekcja `profiles` w `config/speed_model.json` (wersja 2026-10-19p), budowa: `scripts/ride_profiles_build.py`.

## Co się zmieniło i dlaczego
Analiza 311 PEŁNYCH jazd (czas ruchu = rekordy > 0,5 m/s, jak raport z jazdy), walidacja na 46 jazdach z ostatnich 120 dni
(każda przewidziana bez swojego udziału):

- **Tempo w ruchu NIE zależy od profilu** ponad to, co daje tabela (nachylenie × nawierzchnia). Profile tempa z historii
  (dowolne okno: 120/180/270/365 dni, cała historia) POGARSZAŁY wynik → tempo = tabela z 120 dni, jak wcześniej.
- **Brutto zależy od profilu przez postoje.** Stary wzór (pierwsza godzina bez postojów) zaniżał krótkie jazdy.
  Postoje liczone od 1. km wg profilu: brutto średnio −3,6% → +0,2%, typowy błąd 10,3% → 9,0%; trening −6,0% → 0,0%.
- **Miasto**: tempo ×0,925 i więcej mikro-postojów (światła) — tylko na odcinkach w zabudowie (ESA WorldCover klasa 50,
  `route_shade_layer.class_center`, pole `built_up` w `route_segments_50m`). Brak warstwy dla trasy → bez korekty miasta.
- **Temperatura**: efekt zimna nie potwierdził się na pełnych danych — brak korekty (do sprawdzenia zimą).

## Profile
| profil | kiedy (planowana trasa) | postoje |
|---|---|---|
| bikepacking | bagaż (`bikepacking=true`, Planer) | `stops.bikepacking` (bez zmian) + tempo ×bikepacking_speed_factor |
| miasto | ≥ 50% trasy w zabudowie | `profiles.stops.miasto` |
| dluga | czas ruchu ≥ p75 jazd z tego miesiąca (min. 2 h) | `profiles.stops.dluga` |
| krotka_weekend | wyjazd > 60 km od domu (liczy się tylko długość) albo sobota/niedziela | `profiles.stops.krotka_weekend` |
| trening | dzień roboczy | `profiles.stops.trening` |

Pozostałe profile dostają dodatkowo `city.extra_micro_min_per_km` × km w zabudowie. Długie postoje (≥ 20 min) nadal deklaruje
użytkownik. `profile` można podać ręcznie; `profile='off'` = stary wzór v3 (bez miasta i profili).
`ride_date` (albo data ze `start_time` ISO) decyduje o porze roku i dniu tygodnia; brak → dziś.

## Klasyfikacja historii (rekalibracja)
`classify_rides`: bikepacking = ciąg dni A→B (meta dnia N = start dnia N+1, poza domem; pętle z jednej bazy to NIE bikepacking);
miasto = dojazd dom↔centrum albo ≥ 40% jazdy w centrum Warszawy w dzień roboczy; długa = p75 czasu ruchu z ±30 dni roku
(min. 2 h); poza domem bez bagażu → tylko długość; reszta pn–pt trening, sb–nd krótka.
Tygodniowa rekalibracja (`speed_model_recalibrate.py`) liczy postoje profili z 365 dni (profil < 8 jazd → poprzednia wartość)
i pokazuje zmiany w raporcie kandydata; zatwierdza Michał (`--approve`).

## Gdzie działa
Analiza trasy (`route_report_canonical`, dzień z raportu), silnik pogody (dzień ze startu), PLAN CZASU QExt2
(`/api/plan/by-name`, dziś), Albert (`route_time_estimate`: `ride_date`, `profile`).
**Do zrobienia**: Planer wypraw (`/api/routes/{id}/spine` + `dayTime` w JS) — tempo w zabudowie i mikro-postoje miasta;
`qbot_web.py` był zajęty przez inną sesję 19.10.

## QExt2 / ETA (2026-10-19)
- PLAN CZASU (`/api/plan/by-name`) = model QBota z profilem (pole `profile`, `profile_reason`, `city_km`).
- ETA na Karoo, poziom 1: gdy QBot zna trasę, ETA liczy się z tego samego planu (ruch + postoje co 100 m), z korektą
  „jak jedziesz dziś”. Poziom 2 (trasa spoza QBota): tabela i postoje profilu z `/ride-readiness` → `etaModel`
  (`mcp_server._eta_model`: version, paved[11], unpaved[11], stops{profil:[mikro, krótkie]}, p75ByMonthH[12], minLongH);
  Karoo trzyma model i podmienia tylko przy nowej wersji (QExt2 `EtaSpeedTable.setModel`, `EtaModelJson`). Profil na Karoo:
  długa wg p75 miesiąca, dzień roboczy = trening, weekend = krótka (miasta i bikepackingu Karoo nie rozpozna).
  Wbudowana tabela v2 zostaje tylko jako zapas bez sieci przy pierwszym uruchomieniu.
