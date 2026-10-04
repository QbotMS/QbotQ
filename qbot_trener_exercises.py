"""TRENER - baza cwiczen (2026-10-02): katalog 100 cwiczen + ilustracje + prompty do generowania grafik.

Sprzet uzytkownika: JEDNA para hantli z wymiennym obciazeniem (maks. 12 kg / szt.), plaska lawka, mata, gumy oporowe
(dluga petla + mini band). Nic wiecej (brak miejsca). Klasa ciezaru (wcls) sluzy do ukladania treningu w BLOKI tak, zeby
zmieniac obciazenie 1-2 razy na trening: C = 10-12 kg, S = 6-8 kg, L = 2-4 kg, 0 = bez hantli (masa ciala / guma).

CATALOG = zrodlo do zasilenia tabeli qbot_v2.trainer_exercise (sql/trainer_v8.sql, seed(): nowe klucze dopisuje,
istniejacych nie nadpisuje bez force). Grafiki: /opt/qbot/web/public/cwiczenia/<key>.webp (+ _m.webp miniatura),
manifest.json (wersja, suma kontrolna). Paczki grafik: batch 1 = 12 gotowych, 2..9 = po 11 nowych.
prompt(batch) = gotowy tekst do ChatGPT (ten sam styl dla wszystkich paczek). Testy: tests/test_trener_exercises.py.
"""
from __future__ import annotations

import json
import os

IMG_DIR = "/opt/qbot/web/public/cwiczenia"
GROUPS = {"nogi": "Nogi", "tyl": "Tył ciała", "plecy": "Plecy", "klatka": "Klatka", "barki": "Barki",
          "ramiona": "Ramiona", "core": "Brzuch i tułów", "rozgrzewka": "Rozgrzewka i mobilność"}
WCLS = {"C": "ciężko 10–12 kg", "S": "średnio 6–8 kg", "L": "lekko 2–4 kg", "0": "bez hantli"}
EQUIP = {"h2": "dwa hantle", "h1": "jeden hantel", "lawka": "ławka", "mata": "mata", "guma": "guma (długa pętla)",
         "mini": "mini band", "sciana": "ściana"}

# (key, nazwa, grupa, poziom 1-3, klasa ciezaru, sprzet, jednostronne, dawka, miesnie, rozgrzewka, opis do grafiki: start -> koniec)
CATALOG = [
    # ---------------- NOGI (16) ----------------
    ("goblet_squat_db", "Przysiad goblet z hantlem", "nogi", 1, "C", "h1", False, "8–12", "czworogłowe uda, pośladki", False,
     "stanie w lekkim rozkroku, jeden hantel trzymany pionowo przy klatce → głęboki przysiad, biodra poniżej kolan, łokcie między kolanami, plecy proste"),
    ("split_squat_db", "Przysiad wykroczny w miejscu", "nogi", 1, "S", "h2", True, "8–10 / nogę", "czworogłowe uda, pośladki", False,
     "długi krok, hantle w dłoniach wzdłuż tułowia, tylna pięta uniesiona → opuszczenie w dół, tylne kolano tuż nad podłogą, tułów pionowo"),
    ("bulgarian_split_squat_db", "Przysiad bułgarski", "nogi", 3, "S", "h2 lawka", True, "8 / nogę", "czworogłowe uda, pośladki", False,
     "tylna stopa grzbietem na ławce, przednia noga daleko z przodu, hantle w dłoniach → przysiad na przedniej nodze, kolano nad stopą, tylne kolano nisko"),
    ("step_up_db", "Wejścia na ławkę z hantlami", "nogi", 2, "S", "h2 lawka", True, "8 / nogę", "czworogłowe uda, pośladki", False,
     "jedna stopa cała na ławce, hantle w dłoniach → wyprost na ławce, druga noga dostawiona, tułów prosto"),
    ("reverse_lunge_db", "Wykrok w tył z hantlami", "nogi", 2, "S", "h2", True, "8 / nogę", "czworogłowe uda, pośladki", False,
     "stanie prosto, hantle w dłoniach → krok w tył i opuszczenie, tylne kolano tuż nad podłogą, przednie kolano nad stopą"),
    ("walking_lunge_db", "Wykroki chodzone z hantlami", "nogi", 2, "S", "h2", True, "8 / nogę", "czworogłowe uda, pośladki", False,
     "wykrok w przód z hantlami w dłoniach → przejście do kolejnego wykroku drugą nogą, strzałka w przód pokazująca marsz"),
    ("lateral_lunge_db", "Wykrok w bok z hantlem", "nogi", 2, "S", "h1", True, "8 / stronę", "czworogłowe uda, przywodziciele, pośladki", False,
     "szeroki rozkrok, hantel przy klatce → przeniesienie ciężaru na jedną nogę, ugięte kolano, druga noga prosta, biodra w tył"),
    ("goblet_squat_pause_db", "Przysiad goblet z pauzą 3 s", "nogi", 2, "C", "h1", False, "6–8", "czworogłowe uda, pośladki", False,
     "jak przysiad goblet → dół przysiadu z zaznaczoną pauzą (symbol klepsydry), plecy proste, łokcie przy kolanach"),
    ("heel_elevated_squat_db", "Przysiad goblet z piętami na talerzach", "nogi", 2, "C", "h1", False, "10–12", "czworogłowe uda", False,
     "pięty oparte na dwóch talerzach od hantli, hantel przy klatce → głęboki przysiad z kolanami wysuniętymi nad palce, tułów pionowo"),
    ("cossack_squat", "Przysiad kozacki", "nogi", 3, "0", "", True, "6 / stronę", "przywodziciele, czworogłowe uda, pośladki", False,
     "bardzo szeroki rozkrok → głęboki przysiad na jednej nodze, druga noga wyprostowana w bok, palce tej stopy do góry, ręce przed sobą"),
    ("band_squat", "Przysiad z mini bandem", "nogi", 1, "0", "mini", False, "15", "pośladki (boczne), czworogłowe uda", False,
     "mini band nad kolanami, stanie w rozkroku → przysiad, kolana wypchnięte na zewnątrz napinają gumę"),
    ("wall_sit", "Krzesełko przy ścianie", "nogi", 1, "0", "sciana", False, "30–45 s", "czworogłowe uda", False,
     "JEDNA faza: plecy oparte o ścianę, uda równolegle do podłogi, kolana pod kątem 90°, ręce na udach"),
    ("calf_raise_db", "Wspięcia na palce z hantlami", "nogi", 1, "C", "h2", False, "15", "łydki", False,
     "stanie prosto, hantle w dłoniach → wspięcie wysoko na palce, kolana proste"),
    ("single_leg_calf_raise", "Wspięcia na palce jednonóż", "nogi", 2, "0", "sciana", True, "12 / nogę", "łydki", False,
     "stanie na jednej nodze, przednia część stopy na talerzu od hantla, pięta nisko, jedna ręka podparta o ścianę → wspięcie wysoko na palce"),
    ("skater_squat", "Przysiad łyżwiarza", "nogi", 3, "0", "mata", True, "6 / nogę", "czworogłowe uda, pośladki", False,
     "stanie na jednej nodze, druga zgięta w kolanie z tyłu, ręce w przód → przysiad na jednej nodze, tylne kolano dotyka maty"),
    ("band_lateral_walk", "Chodzenie bokiem z mini bandem", "nogi", 1, "0", "mini", False, "10 kroków / stronę", "pośladki (boczne)", True,
     "mini band nad kolanami, lekki półprzysiad → krok w bok z napiętą gumą, strzałka w bok"),
    # ---------------- TYL CIALA (14) ----------------
    ("rdl_db", "Martwy ciąg rumuński z hantlami", "tyl", 1, "C", "h2", False, "8–12", "tył uda, pośladki, prostowniki grzbietu", False,
     "stanie prosto, hantle przed udami → biodra w tył, tułów pochylony, hantle przy goleniach, plecy płaskie, kolana lekko ugięte"),
    ("single_leg_rdl_db", "Martwy ciąg na jednej nodze", "tyl", 3, "S", "h1", True, "8 / nogę", "tył uda, pośladki", False,
     "stanie na jednej nodze, hantel w przeciwnej ręce → tułów pochylony do poziomu, druga noga wyprostowana w tył w linii z plecami"),
    ("hip_thrust_db", "Hip thrust na ławce z hantlem", "tyl", 1, "C", "h1 lawka", False, "10–12", "pośladki, tył uda", False,
     "górna część pleców oparta o bok ławki, siad na macie, hantel na biodrach → biodra wypchnięte w górę, tułów i uda w jednej linii"),
    ("single_leg_hip_thrust", "Hip thrust na jednej nodze", "tyl", 3, "0", "lawka", True, "8 / nogę", "pośladki, tył uda", False,
     "plecy oparte o bok ławki, jedna noga uniesiona → biodra wypchnięte w górę na jednej nodze, miednica równo"),
    ("glute_bridge_db", "Most biodrowy z hantlem", "tyl", 1, "C", "h1 mata", False, "12", "pośladki", False,
     "leżenie na plecach na macie, kolana ugięte, hantel na biodrach → biodra uniesione, linia od barków do kolan"),
    ("single_leg_glute_bridge", "Most biodrowy na jednej nodze", "tyl", 2, "0", "mata", True, "10 / nogę", "pośladki, tył uda", False,
     "leżenie na plecach, jedna noga wyprostowana w górę → biodra uniesione na jednej nodze, miednica równo"),
    ("good_morning_db", "Good morning z hantlem", "tyl", 2, "S", "h1", False, "10", "tył uda, prostowniki grzbietu", False,
     "stanie, jeden hantel trzymany oburącz przy klatce → biodra w tył, tułów prawie równolegle do podłogi, plecy płaskie"),
    ("band_glute_kickback", "Wyprost nogi w tył z mini bandem", "tyl", 1, "0", "mini mata", True, "12 / nogę", "pośladki", False,
     "klęk podparty na macie, mini band na stopach → jedna noga wyprostowana w tył i w górę, plecy płaskie"),
    ("band_clamshell", "Muszelka z mini bandem", "tyl", 1, "0", "mini mata", True, "15 / stronę", "pośladki (boczne)", True,
     "leżenie bokiem, kolana ugięte, mini band nad kolanami → górne kolano uniesione jak otwierana muszla, stopy razem"),
    ("hamstring_walkout", "Most z wyprowadzaniem stóp", "tyl", 2, "0", "mata", False, "6", "tył uda, pośladki", False,
     "most biodrowy na macie → stopy odprowadzone małymi krokami daleko od bioder, biodra cały czas uniesione"),
    ("kickstand_rdl_db", "Martwy ciąg z podpórką (kickstand)", "tyl", 2, "C", "h2", True, "8 / nogę", "tył uda, pośladki", False,
     "stanie, tylna stopa na palcach jako podpórka, ciężar na przedniej nodze, hantle przed udami → biodra w tył, hantle przy goleni przedniej nogi"),
    ("sumo_deadlift_db", "Martwy ciąg sumo z hantlem", "tyl", 1, "C", "h1", False, "10–12", "pośladki, przywodziciele, tył uda", False,
     "szeroki rozkrok, palce na zewnątrz, jeden hantel pionowo między nogami przy podłodze → wyprost do stania, plecy proste"),
    ("band_good_morning", "Good morning z gumą", "tyl", 1, "0", "guma", False, "15", "tył uda, prostowniki grzbietu", False,
     "guma pod stopami i założona za kark, tułów pochylony, plecy płaskie → wyprost do stania, guma napięta"),
    ("side_lying_hip_abduction", "Odwodzenie nogi leżąc bokiem", "tyl", 1, "0", "mini mata", True, "15 / nogę", "pośladki (boczne)", False,
     "leżenie bokiem, nogi proste, mini band nad kostkami → górna noga uniesiona w bok, stopa lekko w dół"),
    # ---------------- PLECY (14) ----------------
    ("row_one_arm_db", "Wiosłowanie hantlem jednorącz", "plecy", 1, "C", "h1 lawka", True, "10 / stronę", "najszerszy grzbietu, mięśnie między łopatkami, tył barku", False,
     "kolano i dłoń na ławce, hantel w wyprostowanej ręce → hantel przyciągnięty do biodra, łokieć blisko tułowia"),
    ("bent_over_row_db", "Wiosłowanie oburącz w opadzie", "plecy", 2, "C", "h2", False, "10", "najszerszy grzbietu, mięśnie między łopatkami", False,
     "tułów pochylony 45°, plecy płaskie, hantle zwisają → oba hantle przyciągnięte do bioder, łopatki ściągnięte"),
    ("pullover_db", "Pullover z jednym hantlem", "plecy", 2, "C", "h1 lawka", False, "10", "najszerszy grzbietu, klatka piersiowa", False,
     "leżenie na ławce, hantel oburącz nad klatką → hantel opuszczony łukiem za głowę, ręce lekko ugięte"),
    ("ytw_prone", "Y-T-W leżąc na brzuchu", "plecy", 1, "0", "mata", False, "6 × każda litera", "tył barku, mięśnie między łopatkami", True,
     "trzy fazy z góry: ręce w kształt Y, T i W"),
    ("row_one_arm_pause_db", "Wiosłowanie jednorącz z pauzą", "plecy", 2, "C", "h1 lawka", True, "8 / stronę", "najszerszy grzbietu, mięśnie między łopatkami", False,
     "jak wiosłowanie jednorącz → hantel przy biodrze z zaznaczoną pauzą (symbol klepsydry), łopatka ściągnięta"),
    ("chest_supported_row_db", "Wiosłowanie leżąc przodem na ławce", "plecy", 1, "C", "h2 lawka", False, "10–12", "mięśnie między łopatkami, najszerszy grzbietu", False,
     "leżenie przodem na ławce, hantle zwisają pod ławką → hantle przyciągnięte do boków, łokcie w górę, klatka przy ławce"),
    ("renegade_row_db", "Wiosłowanie w podporze (renegade row)", "plecy", 3, "S", "h2 mata", True, "6 / stronę", "najszerszy grzbietu, mięśnie brzucha", False,
     "podpór przodem na wyprostowanych rękach, dłonie na hantlach, stopy szeroko → jeden hantel przyciągnięty do biodra, biodra równo"),
    ("superman", "Superman leżąc", "plecy", 1, "0", "mata", False, "10 × 2 s", "prostowniki grzbietu, pośladki", False,
     "leżenie na brzuchu, ręce wyprostowane w przód → ręce, klatka i nogi lekko uniesione nad matę"),
    ("reverse_fly_db", "Odwrotne rozpiętki w opadzie", "plecy", 1, "L", "h2", False, "12–15", "tył barku, mięśnie między łopatkami", False,
     "tułów pochylony prawie poziomo, lekkie hantle zwisają pod barkami → ręce uniesione szeroko na boki, łokcie lekko ugięte"),
    ("band_row_seated", "Wiosłowanie gumą w siadzie", "plecy", 1, "0", "guma mata", False, "15", "najszerszy grzbietu, mięśnie między łopatkami", False,
     "siad na macie, nogi proste, guma owinięta o stopy, ręce przed sobą → końce gumy przyciągnięte do brzucha, łokcie w tył, tułów prosto"),
    ("band_lat_pulldown", "Ściąganie gumy nad głową", "plecy", 1, "0", "guma", False, "15", "najszerszy grzbietu, mięśnie między łopatkami", True,
     "stanie lub klęk, guma trzymana w wyprostowanych rękach nad głową → guma rozciągnięta i ściągnięta za kark do wysokości barków"),
    ("prone_t_raise_db", "Unoszenie T leżąc przodem na ławce", "plecy", 1, "L", "h2 lawka", False, "12", "tył barku, mięśnie między łopatkami", False,
     "leżenie przodem na ławce, lekkie hantle zwisają → ręce proste uniesione w bok do kształtu litery T, kciuki w górę"),
    ("db_shrug", "Wzruszenia barków z hantlami", "plecy", 1, "C", "h2", False, "12–15", "czworoboczny górny", False,
     "stanie, hantle wzdłuż tułowia → barki uniesione prosto w górę do uszu, ręce proste"),
    ("band_row_one_arm", "Wiosłowanie gumą jednorącz w wykroku", "plecy", 1, "0", "guma", True, "12 / stronę", "najszerszy grzbietu", False,
     "wykrok, guma pod przednią stopą, ręka wyprostowana w dół w przód → guma przyciągnięta do biodra, łokieć w tył"),
    # ---------------- KLATKA (10) ----------------
    ("bench_press_db", "Wyciskanie hantli na ławce", "klatka", 1, "C", "h2 lawka", False, "10", "klatka piersiowa, triceps, przód barku", False,
     "leżenie na ławce, hantle nad klatką → hantle opuszczone do klatki, łokcie 45° od tułowia"),
    ("pushup", "Pompki klasyczne", "klatka", 2, "0", "", False, "8–12", "klatka piersiowa, triceps", False,
     "podpór na dłoniach, ciało w linii → klatka tuż nad podłogą"),
    ("pushup_knees", "Pompki na kolanach", "klatka", 1, "0", "mata", False, "10–12", "klatka piersiowa, triceps", True,
     "podpór na dłoniach i kolanach → klatka tuż nad podłogą"),
    ("bench_press_neutral_db", "Wyciskanie hantli chwytem neutralnym", "klatka", 1, "C", "h2 lawka", False, "10", "klatka piersiowa, triceps", False,
     "leżenie na ławce, hantle nad klatką, dłonie zwrócone do siebie → hantle opuszczone do boków klatki, łokcie blisko tułowia"),
    ("floor_press_db", "Wyciskanie hantli leżąc na podłodze", "klatka", 1, "C", "h2 mata", False, "10", "klatka piersiowa, triceps", False,
     "leżenie na macie, kolana ugięte, hantle nad klatką → łokcie opuszczone do maty, hantle nad klatką"),
    ("db_fly", "Rozpiętki z hantlami na ławce", "klatka", 2, "L", "h2 lawka", False, "12", "klatka piersiowa", False,
     "leżenie na ławce, hantle nad klatką, łokcie lekko ugięte → ręce opuszczone szeroko na boki łukiem do wysokości ławki"),
    ("pushup_wide", "Pompki szerokie", "klatka", 2, "0", "", False, "8–12", "klatka piersiowa", False,
     "podpór z dłońmi wyraźnie szerzej niż barki → klatka tuż nad podłogą"),
    ("pushup_feet_elevated", "Pompki ze stopami na ławce", "klatka", 3, "0", "lawka", False, "8–10", "klatka piersiowa (górna), barki, triceps", False,
     "stopy na ławce, dłonie na podłodze, ciało w linii → klatka tuż nad podłogą"),
    ("pushup_incline", "Pompki z rękami na ławce", "klatka", 1, "0", "lawka", False, "12", "klatka piersiowa, triceps", True,
     "dłonie na krawędzi ławki, ciało w linii skośnie → klatka przy krawędzi ławki"),
    ("band_chest_press", "Wypychanie gumy przed siebie", "klatka", 1, "0", "guma", False, "15", "klatka piersiowa, triceps", False,
     "stanie, guma przełożona za plecami na wysokości łopatek, dłonie przy klatce → ręce wypchnięte prosto przed siebie"),
    # ---------------- BARKI (10) ----------------
    ("shoulder_press_seated_db", "Wyciskanie hantli nad głowę siedząc", "barki", 1, "S", "h2 lawka", False, "10", "barki, triceps", False,
     "siad na ławce, hantle przy barkach → hantle wyciśnięte nad głowę"),
    ("shoulder_press_standing_db", "Wyciskanie hantli nad głowę stojąc", "barki", 2, "S", "h2", False, "8–10", "barki, triceps, mięśnie brzucha", False,
     "stanie, hantle przy barkach, brzuch napięty → hantle wyciśnięte nad głowę, tułów prosto"),
    ("arnold_press_db", "Wyciskanie Arnolda siedząc", "barki", 2, "S", "h2 lawka", False, "10", "barki (przód i środek)", False,
     "siad, hantle przed twarzą, dłonie zwrócone do siebie → hantle nad głową z obrotem dłoni na zewnątrz, strzałka obrotu"),
    ("lateral_raise_db", "Unoszenie hantli bokiem", "barki", 1, "L", "h2", False, "12–15", "barki (środek)", False,
     "stanie, lekkie hantle przy udach → ręce uniesione bokiem do wysokości barków, łokcie lekko ugięte"),
    ("front_raise_db", "Unoszenie hantli przodem", "barki", 1, "L", "h2", False, "12", "barki (przód)", False,
     "stanie, lekkie hantle przed udami → ręce uniesione prosto przed siebie do wysokości barków"),
    ("pike_pushup", "Pompka w pozycji V (pike)", "barki", 3, "0", "", False, "6–8", "barki, triceps", False,
     "pozycja odwróconego V, biodra wysoko, dłonie na podłodze → głowa opuszczona przed dłonie, łokcie zgięte"),
    ("band_pull_apart", "Rozciąganie gumy przed sobą", "barki", 1, "0", "guma", False, "15", "tył barku, mięśnie między łopatkami", True,
     "ręce z gumą przed sobą → guma rozciągnięta szeroko na boki"),
    ("band_dislocates", "Przekładanie gumy za plecy", "barki", 1, "0", "guma", False, "10", "barki (mobilność)", True,
     "guma trzymana szeroko oburącz przed biodrami, ręce proste → guma przeniesiona łukiem nad głową za plecy, ręce nadal proste"),
    ("cuban_rotation_db", "Rotacja zewnętrzna barku z hantlami", "barki", 2, "L", "h2", False, "10", "stożek rotatorów", False,
     "stanie, ramiona w bok na wysokości barków, łokcie zgięte 90°, przedramiona w dół → przedramiona obrócone w górę, łokcie w miejscu"),
    ("band_external_rotation", "Rotacja na zewnątrz z gumą", "barki", 1, "0", "guma", False, "15", "stożek rotatorów, tył barku", True,
     "stanie, łokcie przy bokach zgięte 90°, guma w dłoniach przed brzuchem → przedramiona obrócone na zewnątrz, guma napięta, łokcie przy ciele"),
    # ---------------- RAMIONA (8) ----------------
    ("bicep_curl_db", "Uginanie przedramion z hantlami", "ramiona", 1, "S", "h2", False, "10–12", "biceps", False,
     "stanie, hantle wzdłuż tułowia, dłonie w przód → hantle podniesione do barków, łokcie przy tułowiu"),
    ("hammer_curl_db", "Uginanie młotkowe", "ramiona", 1, "S", "h2", False, "10–12", "biceps, mięsień ramienny, przedramię", False,
     "stanie, hantle wzdłuż tułowia, dłonie zwrócone do siebie → hantle podniesione do barków chwytem młotkowym"),
    ("bench_dips", "Dipy na ławce", "ramiona", 2, "0", "lawka", False, "8–12", "triceps", False,
     "dłonie na krawędzi ławki za plecami, nogi ugięte, ręce proste → łokcie zgięte do ok. 90°, biodra blisko ławki"),
    ("overhead_triceps_ext_db", "Wyprost ramion nad głową z hantlem", "ramiona", 1, "S", "h1 lawka", False, "10–12", "triceps", False,
     "siad na ławce, jeden hantel oburącz za głową, łokcie w górę → ręce wyprostowane nad głową"),
    ("skull_crusher_db", "Wyprosty ramion leżąc z hantlami", "ramiona", 2, "L", "h2 lawka", False, "10–12", "triceps", False,
     "leżenie na ławce, hantle nad klatką, dłonie do siebie → łokcie zgięte, hantle przy skroniach, ramiona nieruchome"),
    ("diamond_pushup", "Pompki diamentowe", "ramiona", 3, "0", "", False, "6–10", "triceps, klatka piersiowa", False,
     "podpór, dłonie blisko siebie pod klatką (kciuki i palce wskazujące tworzą romb) → klatka tuż nad dłońmi"),
    ("band_curl", "Uginanie z gumą", "ramiona", 1, "0", "guma", False, "15", "biceps", False,
     "stanie, guma pod stopami, ręce proste w dół → dłonie podniesione do barków, łokcie przy tułowiu"),
    ("triceps_kickback_db", "Prostowanie ramienia w opadzie", "ramiona", 1, "L", "h1 lawka", True, "12 / stronę", "triceps", False,
     "kolano i dłoń na ławce, ramię wzdłuż tułowia, łokieć zgięty 90° → przedramię wyprostowane w tył"),
    # ---------------- CORE (18) ----------------
    ("plank_forearm", "Deska na przedramionach", "core", 1, "0", "mata", False, "30 s", "mięśnie brzucha, pośladki", False,
     "jedna faza: deska na przedramionach"),
    ("side_plank", "Deska boczna", "core", 2, "0", "mata", True, "20–30 s / stronę", "mięśnie skośne brzucha", False,
     "JEDNA faza: podpór bokiem na przedramieniu, ciało w prostej linii, biodra uniesione, druga ręka na biodrze"),
    ("dead_bug", "Dead bug", "core", 1, "0", "mata", False, "8 / stronę", "mięśnie brzucha (głębokie)", False,
     "leżenie na plecach, ręce w górę, kolana nad biodrami zgięte 90° → przeciwna ręka i noga opuszczone nisko nad matę, lędźwie przy macie"),
    ("hollow_hold", "Hollow hold", "core", 3, "0", "mata", False, "20–30 s", "mięśnie brzucha", False,
     "JEDNA faza: leżenie na plecach, łopatki i proste nogi uniesione nad matę, ręce wyprostowane za głową, lędźwie przyklejone do maty"),
    ("bird_dog", "Bird dog", "core", 1, "0", "mata", True, "8 / stronę", "prostowniki grzbietu, pośladki, mięśnie brzucha", True,
     "klęk podparty na macie → przeciwna ręka i noga wyprostowane w linii z plecami"),
    ("mountain_climbers", "Mountain climbers", "core", 2, "0", "", False, "30 s", "mięśnie brzucha, zginacze biodra", False,
     "podpór na dłoniach, ciało w linii → jedno kolano przyciągnięte do klatki, strzałki naprzemiennej pracy nóg"),
    ("lying_leg_raise_bench", "Unoszenie nóg leżąc na ławce", "core", 2, "0", "lawka", False, "10", "mięśnie brzucha (dolne)", False,
     "leżenie na ławce, dłonie trzymają ławkę za głową, nogi proste nisko → nogi uniesione do pionu"),
    ("plank_shoulder_tap", "Deska z dotykaniem barku", "core", 2, "0", "mata", False, "10 / stronę", "mięśnie brzucha, barki", False,
     "podpór na dłoniach, stopy szeroko → jedna dłoń dotyka przeciwnego barku, biodra nieruchome"),
    ("russian_twist_db", "Russian twist z hantlem", "core", 2, "L", "h1 mata", False, "10 / stronę", "mięśnie skośne brzucha", False,
     "siad na macie, tułów odchylony, stopy lekko nad matą, hantel przy brzuchu → tułów skręcony, hantel przy biodrze"),
    ("suitcase_carry_db", "Spacer z hantlem w jednej ręce", "core", 1, "C", "h1", True, "30 s / stronę", "mięśnie skośne brzucha, chwyt", False,
     "marsz z jednym ciężkim hantlem w jednej ręce, tułów pionowo, barki równo, strzałka marszu"),
    ("farmer_carry_db", "Spacer farmera", "core", 1, "C", "h2", False, "40 s", "mięśnie tułowia, chwyt, czworoboczny", False,
     "marsz z dwoma ciężkimi hantlami wzdłuż tułowia, wyprostowana postawa, strzałka marszu"),
    ("dead_bug_db", "Dead bug z hantlem", "core", 2, "L", "h1 mata", False, "8 / stronę", "mięśnie brzucha (głębokie)", False,
     "leżenie na plecach, hantel oburącz nad klatką, kolana nad biodrami → jedna noga wyprostowana nisko nad matą, hantel nieruchomo"),
    ("glute_bridge_march", "Most z marszem", "core", 2, "0", "mata", False, "8 / nogę", "pośladki, mięśnie brzucha", False,
     "most biodrowy → jedno kolano uniesione do biodra, biodra nadal wysoko i równo"),
    ("reverse_crunch", "Odwrotne brzuszki", "core", 1, "0", "mata", False, "12", "mięśnie brzucha (dolne)", False,
     "leżenie na plecach, kolana ugięte nad biodrami → biodra uniesione z maty, kolana do klatki"),
    ("copenhagen_plank_short", "Deska kopenhaska (kolano na ławce)", "core", 3, "0", "lawka", True, "15–20 s / stronę", "przywodziciele, mięśnie skośne brzucha", False,
     "JEDNA faza: deska boczna na przedramieniu, kolano górnej nogi oparte na ławce, dolna noga pod ławką, biodra uniesione"),
    ("bear_hold", "Niedźwiedź (podpór na palcach)", "core", 1, "0", "mata", False, "20–30 s", "mięśnie brzucha, barki", False,
     "klęk podparty → kolana uniesione kilka centymetrów nad matę, plecy płaskie"),
    ("db_woodchop", "Drwal z hantlem", "core", 2, "L", "h1", True, "10 / stronę", "mięśnie skośne brzucha, barki", False,
     "stanie w rozkroku, hantel oburącz przy jednym biodrze → hantel przeniesiony skosem nad przeciwny bark, tułów z rotacją"),
    ("side_plank_hip_dip", "Deska boczna z opuszczaniem biodra", "core", 2, "0", "mata", True, "10 / stronę", "mięśnie skośne brzucha", False,
     "deska boczna na przedramieniu → biodro opuszczone nad matę i z powrotem w górę"),
    # ---------------- ROZGRZEWKA I MOBILNOSC (10) ----------------
    ("arm_circles", "Krążenia ramion", "rozgrzewka", 1, "0", "", False, "10 + 10", "barki", True, "ręce w bok, krążenia"),
    ("torso_rotations", "Skręty tułowia", "rozgrzewka", 1, "0", "", False, "10 / stronę", "mięśnie skośne brzucha", True, "skręty z rękami na biodrach"),
    ("cat_cow", "Koci grzbiet", "rozgrzewka", 1, "0", "mata", False, "8", "kręgosłup (mobilność)", True,
     "klęk podparty, plecy wygięte w łuk w górę (koci grzbiet) → plecy wygięte w dół, głowa uniesiona"),
    ("worlds_greatest_stretch", "Wypad z rotacją", "rozgrzewka", 2, "0", "mata", True, "5 / stronę", "biodra, odcinek piersiowy", True,
     "głęboki wypad, dłoń przy wewnętrznej stronie przedniej stopy → tułów obrócony, druga ręka wyprostowana w górę"),
    ("hip_90_90", "Siad 90/90", "rozgrzewka", 1, "0", "mata", False, "6 / stronę", "biodra (rotacja)", True,
     "siad na macie, obie nogi zgięte 90° jedna przed, druga z boku → kolana przeniesione na drugą stronę, tułów prosto"),
    ("thoracic_open_book", "Otwieranie książki", "rozgrzewka", 1, "0", "mata", True, "8 / stronę", "odcinek piersiowy kręgosłupa", True,
     "leżenie bokiem, kolana ugięte, ręce razem przed sobą → górna ręka przeniesiona łukiem na drugą stronę, klatka otwarta"),
    ("leg_swings", "Wymachy nóg", "rozgrzewka", 1, "0", "sciana", True, "10 / nogę", "biodra (mobilność)", True,
     "stanie bokiem do ściany, dłoń na ścianie → noga wymachnięta w przód i w tył, strzałka łuku"),
    ("bodyweight_squat", "Przysiad bez obciążenia", "rozgrzewka", 1, "0", "", False, "10", "czworogłowe uda, pośladki", True,
     "stanie w rozkroku, ręce przed sobą → przysiad, biodra nisko, plecy proste"),
    ("hip_flexor_stretch", "Rozciąganie zginaczy biodra w klęku", "rozgrzewka", 1, "0", "mata", True, "30 s / stronę", "zginacze biodra", True,
     "JEDNA faza: klęk jednonóż na macie, biodra wypchnięte w przód, tułów prosto, ręce na biodrach"),
    ("inchworm", "Gąsienica", "rozgrzewka", 2, "0", "mata", False, "5", "tył uda, barki, mięśnie brzucha", True,
     "skłon z dłońmi przy stopach → dłonie przeprowadzone w przód do podporu przodem, ciało w linii"),
]

# kroki, dobrze / blad - dla gotowych grafik (paczka 1); kolejne dopisywane razem z ich grafikami
TEXTS = {
    "row_one_arm_db": (["Kolano i dłoń na ławce, plecy płasko.", "Przyciągnij hantel do biodra, łokieć blisko ciała.", "Opuść powoli do pełnego wyprostu."], "Ściągnij łopatkę na górze.", "Nie skręcaj tułowia."),
    "bent_over_row_db": (["Kolana lekko ugięte, tułów pochylony ok. 45°.", "Przyciągnij oba hantle do bioder.", "Pauza 1 s na górze, powoli w dół."], "Plecy proste przez cały ruch.", "Nie szarp tułowiem."),
    "pullover_db": (["Leżenie na ławce, hantel oburącz nad klatką.", "Opuść łukiem za głowę, ręce lekko ugięte.", "Wróć tym samym łukiem nad klatkę."], "Napięty brzuch, lędźwie przy ławce.", "Nie schodź nisko, gdy bark boli."),
    "ytw_prone": (["Połóż się na brzuchu, czoło tuż nad matą.", "Unieś ręce w kształt Y, potem T, potem W.", "Na górze 1 s pauzy, ściągnięte łopatki."], "Ruch z łopatek, kciuki w górę.", "Nie zadzieraj głowy."),
    "bench_press_db": (["Połóż się, stopy na podłodze, łopatki ściągnięte.", "Opuść hantle do klatki, łokcie ok. 45° od tułowia.", "Wyciśnij w górę, nie zderzaj hantli."], "Stabilne łopatki, pełny zakres.", "Nie rozstawiaj łokci na boki."),
    "pushup": (["Dłonie trochę szerzej niż barki.", "Ciało w jednej linii, napięty brzuch.", "Opuść klatkę, łokcie ok. 45° od tułowia."], "Pełny zakres ruchu.", "Nie opuszczaj bioder."),
    "pushup_knees": (["Oparcie na dłoniach i kolanach.", "Linia od głowy do kolan.", "Opuść klatkę tuż nad podłogę."], "Napięty brzuch.", "Nie wypychaj bioder w górę."),
    "shoulder_press_seated_db": (["Usiądź prosto, hantle na wysokości barków.", "Wyciśnij w górę, nie zderzaj hantli.", "Kontrolowanie wróć do barków."], "Napięty brzuch, plecy proste.", "Nie wyginaj lędźwi."),
    "band_pull_apart": (["Ręce proste przed sobą, guma na szerokość barków.", "Rozciągnij gumę szeroko na boki.", "Powoli wróć."], "Ściągnij łopatki.", "Nie unoś barków do uszu."),
    "plank_forearm": (["Łokcie pod barkami.", "Ciało w linii od głowy do pięt.", "Napnij brzuch i pośladki, oddychaj spokojnie."], "Prosta linia ciała.", "Nie zapadaj lędźwi."),
    "arm_circles": (["Ręce wyprostowane w bok.", "10 krążeń w przód, 10 w tył.", "Zacznij od małych kół, zwiększaj."], "Luźne barki.", "Nie garb się."),
    "torso_rotations": (["Lekki rozkrok, ręce na biodrach.", "Skręcaj tułów w obie strony.", "Biodra zostają w miejscu."], "Spokojny ruch.", "Nie szarp."),
}
# paczka 2 (2026-10-02)
TEXTS.update({
    "goblet_squat_db": (["Stopy na szerokość bioder, hantel pionowo przy klatce.", "Zejdź w dół, biodra w tył, łokcie między kolana.", "Wypchnij się z całych stóp do stania."], "Plecy proste, ciężar na całych stopach.", "Nie odrywaj pięt, nie zaokrąglaj pleców."),
    "split_squat_db": (["Długi krok, hantle wzdłuż tułowia, tylna pięta w górze.", "Opuść się pionowo, tylne kolano tuż nad podłogą.", "Wróć w górę, zostań w rozkroku."], "Tułów pionowo, przednie kolano nad stopą.", "Nie przenoś ciężaru na tylną nogę."),
    "bulgarian_split_squat_db": (["Tylna stopa grzbietem na ławce, przednia daleko z przodu.", "Opuść się na przedniej nodze, tylne kolano nisko.", "Wypchnij się z pięty przedniej nogi."], "Kolano w linii stopy, tułów lekko w przód.", "Nie odbijaj się tylną nogą."),
    "step_up_db": (["Cała stopa na ławce, hantle w dłoniach.", "Wejdź, prostując nogę na ławce.", "Zejdź powoli tą samą nogą w dół."], "Pracuje noga na ławce.", "Nie odbijaj się dolną nogą."),
    "reverse_lunge_db": (["Stanie prosto, hantle wzdłuż tułowia.", "Krok w tył, tylne kolano tuż nad podłogą.", "Wróć do stania, pchając przednią piętą."], "Przednie kolano nad stopą.", "Nie pochylaj się mocno w przód."),
    "walking_lunge_db": (["Krok w przód, opuść tylne kolano nad podłogę.", "Wstań i od razu krok drugą nogą.", "Idź równym tempem, krótkie stopy na boki."], "Tułów pionowo, stabilne kolana.", "Nie stawiaj stóp w jednej linii (chwiejnie)."),
    "lateral_lunge_db": (["Szeroki rozkrok, hantel przy klatce.", "Przenieś ciężar na jedną nogę, biodra w tył.", "Druga noga prosta, wróć do środka."], "Pięta ugiętej nogi na podłodze.", "Nie wypuszczaj kolana do środka."),
    "goblet_squat_pause_db": (["Jak przysiad goblet.", "Na dole zatrzymaj się na 3 s.", "Wstań płynnie, bez odbicia."], "Napięty brzuch w pauzie.", "Nie siadaj na łydkach, nie rozluźniaj się."),
    "heel_elevated_squat_db": (["Pięty na talerzach od hantla, hantel przy klatce.", "Zejdź głęboko, kolana nad palce.", "Wstań, tułów pionowo."], "Głęboki zakres, tułów pionowo.", "Nie zsuwaj pięt z talerzy."),
    "cossack_squat": (["Bardzo szeroki rozkrok, ręce przed sobą.", "Zejdź na jedną nogę, druga prosta, palce w górę.", "Przejdź nisko na drugą stronę albo wstań."], "Pięta ugiętej nogi na podłodze.", "Nie schodź głębiej, niż pozwala biodro."),
    "band_squat": (["Mini band nad kolanami, stopy na szerokość bioder.", "Zejdź do przysiadu, kolana na zewnątrz.", "Wstań, guma cały czas napięta."], "Kolana w linii stóp.", "Nie pozwól gumie ściągnąć kolan do środka."),
})
# paczka 3 (2026-10-02)
TEXTS.update({
    "wall_sit": (["Plecy płasko o ścianę, zejdź do kąta 90° w kolanach.", "Stopy przed kolanami, ręce na udach.", "Trzymaj, oddychaj spokojnie."], "Kolana nad kostkami.", "Nie podpieraj się rękami o uda."),
    "calf_raise_db": (["Stanie prosto, hantle wzdłuż tułowia.", "Wespnij się wysoko na palce.", "Opuść powoli, pięty do podłogi."], "Pełny zakres, pauza na górze.", "Nie bujaj się, kolana proste."),
    "single_leg_calf_raise": (["Stań na jednej nodze, przód stopy na talerzu.", "Dłoń o ścianę dla równowagi, opuść piętę nisko.", "Wespnij się wysoko na palce."], "Wolne opuszczanie (2–3 s).", "Nie odbijaj się. Trudniej: hantel w wolnej ręce."),
    "skater_squat": (["Stań na jednej nodze, druga zgięta z tyłu, ręce w przód.", "Zejdź, aż tylne kolano dotknie maty.", "Wstań na nodze podporowej."], "Kolano nad stopą, tułów lekko w przód.", "Nie uderzaj kolanem o matę."),
    "band_lateral_walk": (["Mini band nad kolanami, lekki półprzysiad.", "Krok w bok, guma cały czas napięta.", "10 kroków w jedną stronę, potem w drugą."], "Biodra nisko i równo.", "Nie stawiaj stóp razem."),
    "rdl_db": (["Stanie, hantle przed udami, kolana lekko ugięte.", "Biodra w tył, hantle zsuwają się wzdłuż nóg do goleni.", "Wróć, wypychając biodra w przód."], "Plecy płaskie, czujesz tył uda.", "Nie zaokrąglaj pleców, nie przysiadaj."),
    "single_leg_rdl_db": (["Stań na jednej nodze, hantel w ręce.", "Pochyl tułów, druga noga idzie w tył w linii z plecami.", "Wróć do stania na tej samej nodze."], "Biodra równo, kolano podporowe miękkie.", "Nie obracaj miednicy na bok."),
    "hip_thrust_db": (["Plecy na łopatkach oparte o ławkę, hantel na biodrach.", "Wypchnij biodra w górę, napnij pośladki (1 s).", "Opuść powoli."], "Na górze tułów i uda w linii.", "Nie wyginaj lędźwi, nie przeprostowuj."),
    "single_leg_hip_thrust": (["Plecy o ławkę, jedna noga uniesiona.", "Wypchnij biodra w górę na nodze podporowej.", "Opuść powoli."], "Miednica równo.", "Nie opadaj biodrem na stronę uniesionej nogi."),
    "glute_bridge_db": (["Leżenie na macie, kolana ugięte, hantel na biodrach.", "Unieś biodra, napnij pośladki.", "Opuść bez odpoczynku na macie."], "Linia od barków do kolan.", "Nie pchaj lędźwiami."),
    "single_leg_glute_bridge": (["Leżenie, jedna noga wyprostowana w górę.", "Unieś biodra na drugiej nodze.", "Opuść powoli."], "Biodra równo.", "Nie skręcaj miednicy."),
})
# paczka 4 (2026-10-02; good_morning_db i band_good_morning odrzucone - zaokraglone plecy na grafice)
TEXTS.update({
    "good_morning_db": (["Stanie, hantel oburącz przy klatce, kolana lekko ugięte.", "Biodra w tył, tułów pochylony prawie do poziomu.", "Wróć, wypychając biodra w przód."], "Plecy płaskie przez cały ruch.", "Nie zaokrąglaj pleców, nie opuszczaj głowy."),
    "band_good_morning": (["Guma pod stopami i za karkiem, kolana lekko ugięte.", "Pochyl tułów, biodra w tył.", "Wyprostuj się, guma napięta."], "Plecy płaskie, ruch z bioder.", "Nie garb się w skłonie."),
    "band_glute_kickback": (["Klęk podparty, mini band na stopach.", "Wypchnij jedną nogę w tył i w górę.", "Wróć powoli, kolano nie dotyka maty."], "Pracuje pośladek.", "Nie wyginaj lędźwi."),
    "band_clamshell": (["Leżenie bokiem, kolana ugięte, mini band nad kolanami.", "Unieś górne kolano, stopy razem.", "Opuść powoli."], "Miednica nieruchomo.", "Nie odchylaj tułowia w tył."),
    "hamstring_walkout": (["Most biodrowy na macie.", "Małymi krokami odsuń stopy od bioder.", "Wróć krokami pod biodra."], "Biodra wysoko cały czas.", "Nie opadaj biodrami przy dalekich stopach."),
    "kickstand_rdl_db": (["Ciężar na przedniej nodze, tylna stopa na palcach.", "Biodra w tył, hantle wzdłuż przedniej nogi.", "Wróć, wypychając biodra."], "Plecy płaskie, czujesz tył uda przedniej nogi.", "Nie przenoś ciężaru na tylną nogę."),
    "sumo_deadlift_db": (["Szeroki rozkrok, palce na zewnątrz, hantel między stopami.", "Zejdź biodrami w dół, plecy proste, chwyć hantel.", "Wstań, pchając kolana na zewnątrz."], "Kolana w linii stóp.", "Nie zaokrąglaj pleców przy podnoszeniu."),
    "side_lying_hip_abduction": (["Leżenie bokiem, nogi proste, mini band nad kostkami.", "Unieś górną nogę w bok, stopa lekko w dół.", "Opuść powoli."], "Noga lekko za linią ciała.", "Nie przetaczaj się w tył."),
    "row_one_arm_pause_db": (["Jak wiosłowanie jednorącz.", "Na górze zatrzymaj hantel przy biodrze na 1 s.", "Opuść powoli."], "Ściągnięta łopatka w pauzie.", "Nie skręcaj tułowia."),
    "chest_supported_row_db": (["Leżenie przodem na ławce, hantle zwisają.", "Przyciągnij hantle do boków, łokcie w górę.", "Opuść do pełnego wyprostu."], "Klatka przy ławce, łopatki ściągnięte.", "Nie odrywaj klatki od ławki."),
    "renegade_row_db": (["Podpór na hantlach, stopy szeroko.", "Przyciągnij jeden hantel do biodra.", "Odłóż i zmień rękę."], "Biodra równo, napięty brzuch.", "Nie obracaj bioder."),
})
# paczka 5 (2026-10-02; prone_t_raise_db odrzucone - na grafice nie wychodzi litera T)
TEXTS.update({
    "superman": (["Leżenie na brzuchu, ręce wyprostowane w przód.", "Unieś ręce, klatkę i nogi lekko nad matę.", "Przytrzymaj 2 s, opuść powoli."], "Ruch niewielki, napięte pośladki.", "Nie zadzieraj głowy, nie szarp."),
    "reverse_fly_db": (["Pochyl tułów, plecy płaskie, lekkie hantle pod barkami.", "Unieś ręce szeroko na boki, łokcie lekko ugięte.", "Opuść powoli."], "Ściągnij łopatki na górze.", "Nie wymachuj tułowiem, nie bierz za ciężko."),
    "band_row_seated": (["Siad, nogi proste, guma owinięta o stopy.", "Przyciągnij końce gumy do brzucha, łokcie w tył.", "Wróć powoli do wyprostu rąk."], "Tułów prosto, łopatki ściągnięte.", "Nie odchylaj się w tył."),
    "band_lat_pulldown": (["Guma w wyprostowanych rękach nad głową.", "Rozciągnij gumę i ściągnij ją za kark do barków.", "Wróć powoli w górę."], "Łokcie w dół do żeber.", "Nie wysuwaj głowy w przód."),
    "prone_t_raise_db": (["Leżenie przodem na ławce, lekkie hantle zwisają.", "Unieś proste ręce w bok do litery T, kciuki w górę.", "Opuść powoli."], "Ruch z łopatek.", "Nie unoś barków do uszu."),
    "db_shrug": (["Stanie, hantle wzdłuż tułowia.", "Unieś barki prosto w górę do uszu.", "Pauza 1 s, opuść powoli."], "Ręce proste, ruch tylko barkami.", "Nie kręć barkami w kółko."),
    "band_row_one_arm": (["Wykrok, guma pod przednią stopą, ręka wyprostowana.", "Przyciągnij gumę do biodra, łokieć w tył.", "Wróć powoli."], "Tułów nieruchomo, plecy proste.", "Nie skręcaj tułowia."),
    "bench_press_neutral_db": (["Leżenie, hantle nad klatką, dłonie do siebie.", "Opuść hantle do boków klatki, łokcie blisko tułowia.", "Wyciśnij w górę."], "Łopatki ściągnięte, stopy na podłodze.", "Nie odbijaj hantli od klatki."),
    "floor_press_db": (["Leżenie na macie, kolana ugięte, hantle nad klatką.", "Opuść, aż łokcie dotkną maty.", "Wyciśnij w górę."], "Łokcie ok. 45° od tułowia.", "Nie uderzaj łokciami o podłogę."),
    "db_fly": (["Leżenie na ławce, hantle nad klatką, łokcie lekko ugięte.", "Opuść ręce szeroko łukiem do wysokości ławki.", "Wróć tym samym łukiem."], "Lekki ciężar, stały kąt w łokciach.", "Nie schodź za nisko, nie prostuj łokci."),
    "pushup_wide": (["Dłonie wyraźnie szerzej niż barki.", "Ciało w jednej linii, opuść klatkę.", "Wypchnij się w górę."], "Napięty brzuch.", "Nie opuszczaj bioder."),
})
# paczka 6 (2026-10-03; band_dislocates odrzucone - obie fazy identyczne, nie widac przejscia gumy za plecy)
TEXTS.update({
    "pushup_feet_elevated": (["Stopy na ławce, dłonie na podłodze, ciało w linii.", "Opuść klatkę tuż nad podłogę.", "Wypchnij się w górę."], "Napięty brzuch i pośladki.", "Nie zapadaj bioder."),
    "pushup_incline": (["Dłonie na krawędzi ławki, ciało skośnie w linii.", "Opuść klatkę do krawędzi ławki.", "Wypchnij się w górę."], "Łokcie ok. 45° od tułowia.", "Nie wypinaj bioder."),
    "band_chest_press": (["Guma za plecami na wysokości łopatek, dłonie przy klatce.", "Wypchnij ręce prosto przed siebie.", "Wróć powoli."], "Stabilny wykrok, napięty brzuch.", "Nie unoś barków do uszu."),
    "shoulder_press_standing_db": (["Stanie, hantle przy barkach, brzuch i pośladki napięte.", "Wyciśnij hantle nad głowę.", "Opuść kontrolowanie do barków."], "Tułów nieruchomo.", "Nie odchylaj się w tył."),
    "arnold_press_db": (["Siad, hantle przed twarzą, dłonie do siebie.", "Wyciskaj w górę, obracając dłonie na zewnątrz.", "Wróć tym samym ruchem."], "Płynny obrót.", "Nie wyginaj lędźwi."),
    "lateral_raise_db": (["Stanie, lekkie hantle przy udach.", "Unieś ręce bokiem do wysokości barków.", "Opuść powoli."], "Łokcie lekko ugięte, prowadzą ruch.", "Nie bujaj tułowiem, nie unoś wyżej barków."),
    "front_raise_db": (["Stanie, lekkie hantle przed udami.", "Unieś ręce przed siebie do wysokości barków.", "Opuść powoli."], "Spokojne tempo.", "Nie odchylaj się w tył."),
    "pike_pushup": (["Odwrócone V, biodra wysoko, dłonie na podłodze.", "Zegnij łokcie, głowa schodzi przed dłonie.", "Wypchnij się do V."], "Ciężar na barkach.", "Nie opuszczaj bioder (to nie pompka)."),
    "band_dislocates": (["Guma szeroko oburącz przed biodrami, ręce proste.", "Przenieś gumę łukiem nad głową za plecy.", "Wróć tą samą drogą."], "Ręce proste, chwyt tak szeroki, jak trzeba.", "Nie zginaj łokci, nie forsuj barków."),
    "cuban_rotation_db": (["Ramiona w bok na wysokości barków, łokcie 90°, przedramiona w dół.", "Obróć przedramiona w górę.", "Opuść powoli."], "Łokcie w miejscu, bardzo lekki ciężar.", "Nie opuszczaj łokci."),
    "band_external_rotation": (["Łokcie przy bokach zgięte 90°, guma w dłoniach.", "Obróć przedramiona na zewnątrz.", "Wróć powoli."], "Łokcie przyklejone do ciała.", "Nie odchylaj tułowia."),
})
# paczka 7 (2026-10-03)
TEXTS.update({
    "bicep_curl_db": (["Stanie, hantle wzdłuż tułowia, dłonie w przód.", "Unieś hantle do barków, łokcie przy tułowiu.", "Opuść powoli do wyprostu."], "Pełny zakres, wolne opuszczanie.", "Nie bujaj tułowiem."),
    "hammer_curl_db": (["Stanie, hantle wzdłuż tułowia, dłonie do siebie.", "Unieś hantle do barków chwytem młotkowym.", "Opuść powoli."], "Łokcie nieruchomo.", "Nie wysuwaj łokci w przód."),
    "bench_dips": (["Dłonie na krawędzi ławki, biodra przed ławką, ręce proste.", "Zegnij łokcie do ok. 90°, biodra blisko ławki.", "Wypchnij się w górę."], "Łokcie w tył, barki nisko.", "Nie schodź za nisko, gdy bark ciągnie."),
    "overhead_triceps_ext_db": (["Siad, hantel oburącz za głową, łokcie w górę.", "Wyprostuj ręce nad głową.", "Opuść powoli za głowę."], "Łokcie blisko głowy.", "Nie wyginaj lędźwi."),
    "skull_crusher_db": (["Leżenie, hantle nad klatką, dłonie do siebie.", "Zegnij łokcie, hantle przy skroniach.", "Wyprostuj ręce."], "Ramiona nieruchomo.", "Nie rozchylaj łokci na boki."),
    "diamond_pushup": (["Dłonie blisko siebie pod klatką (romb).", "Opuść klatkę nad dłonie, łokcie przy tułowiu.", "Wypchnij się w górę."], "Ciało w jednej linii.", "Za trudno? Na kolanach."),
    "band_curl": (["Guma pod stopami, ręce proste w dół.", "Unieś dłonie do barków.", "Opuść powoli."], "Łokcie przy tułowiu.", "Nie odchylaj się w tył."),
    "triceps_kickback_db": (["Kolano i dłoń na ławce, ramię wzdłuż tułowia, łokieć 90°.", "Wyprostuj przedramię w tył.", "Wróć powoli do 90°."], "Ramię nieruchomo.", "Nie machaj całą ręką."),
    "side_plank": (["Podpór bokiem na przedramieniu, łokieć pod barkiem.", "Unieś biodra, ciało w linii.", "Trzymaj, oddychaj."], "Biodra wysoko.", "Nie opadaj biodrem do maty."),
    "dead_bug": (["Leżenie, ręce w górę, kolana nad biodrami zgięte 90°.", "Opuść przeciwną rękę i nogę nisko nad matę.", "Wróć i zmień stronę."], "Lędźwie przyklejone do maty.", "Nie odrywaj lędźwi, nie spiesz się."),
    "hollow_hold": (["Leżenie na plecach, lędźwie przy macie.", "Unieś łopatki i proste nogi, ręce za głowę.", "Trzymaj kształt łódki."], "Lędźwie dociśnięte.", "Za trudno? Ugnij kolana."),
})
# paczka 8 (2026-10-03; copenhagen_plank_short odrzucone - biodra opadaja, brak linii ciala)
TEXTS.update({
    "bird_dog": (["Klęk podparty, plecy płaskie.", "Wyprostuj przeciwną rękę i nogę w linii z plecami.", "Wróć i zmień stronę."], "Miednica równo, powoli.", "Nie wyginaj lędźwi, nie unoś nogi za wysoko."),
    "mountain_climbers": (["Podpór na dłoniach, ciało w linii.", "Przyciągaj kolana naprzemiennie do klatki.", "Równe tempo, oddychaj."], "Biodra nisko, barki nad dłońmi.", "Nie wypinaj bioder w górę."),
    "lying_leg_raise_bench": (["Leżenie na ławce, dłonie trzymają ławkę za głową.", "Unieś proste nogi do pionu.", "Opuść powoli nisko, bez dotykania."], "Lędźwie przy ławce.", "Nie rzucaj nogami w dół."),
    "plank_shoulder_tap": (["Podpór na dłoniach, stopy szeroko.", "Dotknij dłonią przeciwnego barku.", "Odstaw i zmień rękę."], "Biodra nieruchomo.", "Nie kołysz biodrami na boki."),
    "russian_twist_db": (["Siad, tułów odchylony, hantel przy brzuchu.", "Skręć tułów, hantel do biodra.", "Przejdź na drugą stronę."], "Ruch z tułowia, plecy proste.", "Nie garb się. Trudniej: stopy nad matą."),
    "suitcase_carry_db": (["Ciężki hantel w jednej ręce.", "Idź prosto, tułów pionowo, barki równo.", "Po czasie zmień rękę."], "Napięty brzuch.", "Nie przechylaj się w bok."),
    "farmer_carry_db": (["Dwa ciężkie hantle wzdłuż tułowia.", "Idź krótkimi krokami, wyprostowany.", "Odstaw, przerwa, powtórz."], "Barki w dół i w tył.", "Nie garb się, nie unoś barków."),
    "dead_bug_db": (["Leżenie, hantel oburącz nad klatką, kolana nad biodrami.", "Opuść jedną nogę prosto nisko nad matę.", "Wróć i zmień nogę."], "Lędźwie przy macie, hantel nieruchomo.", "Nie odrywaj lędźwi."),
    "glute_bridge_march": (["Most biodrowy.", "Unieś jedno kolano do biodra.", "Odstaw i zmień nogę."], "Biodra wysoko i równo.", "Nie opadaj biodrem."),
    "reverse_crunch": (["Leżenie, kolana ugięte nad biodrami.", "Unieś biodra z maty, kolana do klatki.", "Opuść powoli."], "Ruch z brzucha.", "Nie zarzucaj nogami."),
    "copenhagen_plank_short": (["Bokiem, przedramię pod barkiem, kolano górnej nogi na ławce.", "Unieś biodra, ciało w linii.", "Trzymaj, oddychaj."], "Biodra wysoko, linia od głowy do kolana.", "Nie opadaj biodrami. Przywodziciel boli = przerwij."),
})
# paczka 9 (2026-10-03; mobilnosc: GPT podswietlil stawy zamiast miesni - przyjete; copenhagen_plank_short 2x odrzucone - bez grafiki)
TEXTS.update({
    "bear_hold": (["Klęk podparty, dłonie pod barkami, kolana pod biodrami.", "Unieś kolana kilka centymetrów nad matę.", "Trzymaj, oddychaj spokojnie."], "Plecy płaskie jak stół.", "Nie wypychaj bioder w górę."),
    "db_woodchop": (["Rozkrok, hantel oburącz przy biodrze.", "Przenieś hantel skosem nad przeciwny bark.", "Wróć tym samym torem."], "Ruch z tułowia i bioder, stopy obracają się z nim.", "Nie szarp, lekki ciężar."),
    "side_plank_hip_dip": (["Deska boczna na przedramieniu.", "Opuść biodro nad matę.", "Unieś je wyżej niż w desce."], "Łokieć pod barkiem.", "Nie skręcaj tułowia w przód."),
    "cat_cow": (["Klęk podparty.", "Zaokrąglij plecy w górę, broda do klatki.", "Wygnij plecy w dół, wzrok w przód."], "Powoli, z oddechem.", "Nie forsuj zakresu."),
    "worlds_greatest_stretch": (["Głęboki wypad, dłoń przy wewnętrznej stronie przedniej stopy.", "Obróć tułów, druga ręka prosto w górę.", "Wróć i zmień stronę."], "Tylna noga prosta, biodro nisko.", "Nie opieraj kolana tylnej nogi."),
    "hip_90_90": (["Siad, obie nogi zgięte 90°: jedna przed, druga z boku.", "Przenieś kolana na drugą stronę.", "Tułów prosto, powoli."], "Ruch z bioder.", "Nie pomagaj sobie rękami, jeśli możesz."),
    "thoracic_open_book": (["Leżenie bokiem, kolana ugięte, ręce razem przed sobą.", "Przenieś górną rękę łukiem na drugą stronę.", "Wróć powoli."], "Kolana razem na macie.", "Nie odrywaj kolan."),
    "leg_swings": (["Stanie bokiem do ściany, dłoń na ścianie.", "Wymachuj nogą w przód i w tył.", "Zwiększaj zakres stopniowo."], "Tułów prosto.", "Nie bujaj tułowiem."),
    "bodyweight_squat": (["Stopy na szerokość bioder, ręce przed sobą.", "Zejdź w przysiad, biodra w tył i w dół.", "Wstań."], "Pięty na podłodze.", "Nie wypuszczaj kolan do środka."),
    "hip_flexor_stretch": (["Klęk jednonóż, ręce na biodrach.", "Wypchnij biodra w przód, napnij pośladek tylnej nogi.", "Trzymaj 30 s, zmień stronę."], "Tułów pionowo.", "Nie wyginaj lędźwi."),
    "inchworm": (["Skłon, dłonie przy stopach.", "Przejdź dłońmi do podporu przodem.", "Wróć dłońmi do stóp i wstań."], "Kolana jak najprostsze.", "Nie opadaj biodrami w podporze."),
})

# Propozycja ocen (2026-10-03): podstawowe (P) z pierwszenstwem 1-3 (3 = najczesciej, np. wyciskanie na lawce);
# reszta rotacyjne (R). Uzytkownik zmienia na stronie /cwiczenia.html (trainer_exercise_user.tier/prio, wygrywa z propozycja);
# X = pomijaj (silnik nie wybiera). Silnik: ~70% slotow z podstawowych (wg prio, bez powtorki z rzedu), reszta rotacyjne.
PROPOSAL = {
    "bench_press_db": 3, "pushup": 2, "floor_press_db": 1,
    "row_one_arm_db": 3, "chest_supported_row_db": 2, "bent_over_row_db": 1, "reverse_fly_db": 1,
    "shoulder_press_seated_db": 3, "lateral_raise_db": 2, "band_pull_apart": 1,
    "goblet_squat_db": 3, "bulgarian_split_squat_db": 2, "reverse_lunge_db": 1, "step_up_db": 1,
    "rdl_db": 3, "hip_thrust_db": 2, "single_leg_rdl_db": 1,
    "bicep_curl_db": 2, "overhead_triceps_ext_db": 1,
    "plank_forearm": 3, "dead_bug": 2, "side_plank": 1, "bird_dog": 1,
    "cat_cow": 1, "worlds_greatest_stretch": 1, "arm_circles": 1, "bodyweight_squat": 1,
}
TIERS = {"P": "podstawowe", "R": "rotacyjne", "X": "pomijaj"}


BATCH1 = ["row_one_arm_db", "bent_over_row_db", "pullover_db", "ytw_prone", "bench_press_db", "pushup", "pushup_knees",
          "shoulder_press_seated_db", "band_pull_apart", "plank_forearm", "arm_circles", "torso_rotations"]
_NEW = [r[0] for r in CATALOG if r[0] not in BATCH1]
BATCH_SIZE = 11


def batch_of(key: str) -> int:
    if key in BATCH1:
        return 1
    return 2 + _NEW.index(key) // BATCH_SIZE


def batches() -> int:
    return 1 + (len(_NEW) + BATCH_SIZE - 1) // BATCH_SIZE


def rows() -> list[dict]:
    out = []
    for (k, name, grp, lvl, wc, eq, uni, dose, mus, warm, desc) in CATALOG:
        t = TEXTS.get(k)
        out.append({"key": k, "name": name, "grp": grp, "level": lvl, "wclass": wc, "equip": [e for e in eq.split() if e],
                    "unilateral": uni, "dose": dose, "muscles": mus, "warmup": warm, "img_desc": desc, "batch": batch_of(k),
                    "steps": t[0] if t else None, "ok": t[1] if t else None, "bad": t[2] if t else None})
    return out


def manifest() -> dict:
    try:
        return json.load(open(os.path.join(IMG_DIR, "manifest.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


STYLE = """Przygotuj serię ilustracji ćwiczeń do bazy mojej aplikacji treningowej. To NIE jest plakat ani ściąga — każde ćwiczenie to OSOBNY obraz, który aplikacja sama wstawi do swojego układu i dopisze do niego tekst. Generuj obrazy JEDEN PO DRUGIM, w kolejności z listy, aż zrobisz wszystkie. Jeśli musisz przerwać, napisz, na którym numerze skończyłeś.

STYL (identyczny jak w poprzednich paczkach, bez wyjątków):
- Format poziomy 1536×1024, czyste białe tło, delikatna szara linia podłogi, bez cienia otoczenia i bez wnętrza pokoju.
- Ta sama postać na wszystkich obrazach: mężczyzna ok. 40 lat, sylwetka kolarza z lekką nadwagą (ok. 100 kg, szeroki w barkach), krótkie ciemne włosy, czarna koszulka sportowa, czarne spodenki, szare buty treningowe. Spokojna, skupiona twarz.
- Ilustracja w stylu nowoczesnego infografiku fitness: realistyczne proporcje, czyste kontury, miękkie cieniowanie, jak w profesjonalnych atlasach ćwiczeń.
- Dwie fazy ruchu obok siebie: po LEWEJ pozycja startowa, po PRAWEJ pozycja końcowa (chyba że opis mówi JEDNA faza albo trzy fazy). Przy ręce/hantlu pomarańczowa strzałka (#E8742A) pokazująca kierunek ruchu.
- Mięśnie pracujące podświetlone na postaci półprzezroczystym czerwonym kolorem (#D9362B, ok. 50%), TYLKO te wymienione w opisie.
- Kamera: widok z boku pod kątem ok. 30° (ćwiczenia leżąc na brzuchu lub na plecach: także z góry, jeśli lepiej widać ruch). Cała postać i sprzęt w kadrze, z marginesem.
- Sprzęt WYŁĄCZNIE: hantle z wymiennym obciążeniem (czarne, okrągłe talerze), płaska ławka treningowa, mata, guma oporowa (pomarańczowa długa pętla), mini band (pomarańczowa krótka pętla), ściana. Nic więcej.
- ZERO TEKSTU na obrazie: bez napisów, liter, cyfr, logo, podpisów, numerów, znaków wodnych (pauzę pokazuj symbolem klepsydry, nie liczbą).
- Technika ma być PRAWIDŁOWA: plecy neutralne, barki z dala od uszu, kolana w linii stóp. To baza do nauki — błąd techniki na obrazku jest gorszy niż brak obrazka.

PO KAŻDYM OBRAZIE napisz jedną linię: PLIK: <klucz>.png — <nazwa>. Nic więcej.
Na koniec spakuj wszystkie obrazy tej paczki do jednego pliku ZIP o nazwie ilustracje_paczka_{n}.zip, każdy obraz pod nazwą <klucz>.png.

LISTA (klucz · nazwa · start → koniec · mięśnie):
"""


def prompt(batch: int) -> str:
    items = [r for r in rows() if r["batch"] == batch]
    if not items:
        return ""
    lines = [f"{i + 1}. {r['key']} · {r['name']} · {r['img_desc']} · {r['muscles']}." for i, r in enumerate(items)]
    return STYLE.replace("{n}", str(batch)) + "\n".join(lines)


def seed(c, force: bool = False) -> dict:
    """Dopisuje do qbot_v2.trainer_exercise klucze, ktorych nie ma (force=True nadpisuje opisy z katalogu)."""
    n_new = n_upd = 0
    for r in rows():
        c.execute("SELECT key FROM qbot_v2.trainer_exercise WHERE key=%s", (r["key"],))
        exists = bool(c.fetchone())
        if exists and not force:
            continue
        vals = (r["name"], r["grp"], r["level"], r["wclass"], r["equip"], r["unilateral"], r["dose"], r["muscles"], r["warmup"],
                r["img_desc"], json.dumps(r["steps"], ensure_ascii=False) if r["steps"] else None, r["ok"], r["bad"], r["batch"])
        if exists:
            c.execute("UPDATE qbot_v2.trainer_exercise SET name=%s, grp=%s, level=%s, wclass=%s, equip=%s, unilateral=%s, dose=%s, "
                      "muscles=%s, warmup=%s, img_desc=%s, steps=%s::jsonb, ok=%s, bad=%s, batch=%s, updated_at=now() WHERE key=%s",
                      vals + (r["key"],))
            n_upd += 1
        else:
            c.execute("INSERT INTO qbot_v2.trainer_exercise (name, grp, level, wclass, equip, unilateral, dose, muscles, warmup, img_desc, "
                      "steps, ok, bad, batch, key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)", vals + (r["key"],))
            n_new += 1
    return {"new": n_new, "updated": n_upd}


def seed_proposal(c) -> int:
    """Propozycja tier/prio do trainer_exercise (nie rusza ocen uzytkownika)."""
    c.execute("UPDATE qbot_v2.trainer_exercise SET tier='R', prio=0")
    n = 0
    for k, p in PROPOSAL.items():
        c.execute("UPDATE qbot_v2.trainer_exercise SET tier='P', prio=%s WHERE key=%s", (p, k)); n += c.rowcount
    return n


def set_rating(c, user: str, key: str, tier: str | None, prio: int | None) -> dict:
    """Ocena uzytkownika. tier None = wroc do propozycji. P wymaga prio 1-3 (domyslnie 1); R/X -> prio 0."""
    c.execute("SELECT key FROM qbot_v2.trainer_exercise WHERE key=%s", (key,))
    if not c.fetchone():
        raise ValueError("nie ma takiego ćwiczenia")
    if tier is None:
        c.execute("UPDATE qbot_v2.trainer_exercise_user SET tier=NULL, prio=NULL, updated_at=now() WHERE username=%s AND key=%s", (user, key))
        return {"key": key, "user": False}
    if tier not in TIERS:
        raise ValueError("tier: P / R / X")
    prio = (min(3, max(1, int(prio or 1))) if tier == "P" else 0)
    c.execute("INSERT INTO qbot_v2.trainer_exercise_user (username, key, tier, prio) VALUES (%s,%s,%s,%s) "
              "ON CONFLICT (username, key) DO UPDATE SET tier=EXCLUDED.tier, prio=EXCLUDED.prio, updated_at=now()", (user, key, tier, prio))
    return {"key": key, "tier": tier, "prio": prio, "user": True}


def list_db(c, user: str | None = None) -> list[dict]:
    """Baza z tabeli + stan grafik z manifestu + ocena (uzytkownika albo propozycja)."""
    man = manifest()
    mine = {}
    if user:
        c.execute("SELECT key, tier, prio FROM qbot_v2.trainer_exercise_user WHERE username=%s AND tier IS NOT NULL", (user,))
        mine = {r["key"]: r for r in c.fetchall()}
    c.execute("SELECT * FROM qbot_v2.trainer_exercise WHERE active ORDER BY batch, key")
    out = []
    for r in c.fetchall():
        d = dict(r)
        d["tier_prop"], d["prio_prop"] = d.get("tier", "R"), d.get("prio", 0)
        u = mine.get(d["key"])
        d["tier_user"] = bool(u)
        if u:
            d["tier"], d["prio"] = u["tier"], u["prio"] or 0
        m = man.get(d["key"])
        d["img"] = (f"/cwiczenia/{d['key']}_m.webp?v={m.get('v', 1)}" if m else None)
        d["img_full"] = (f"/cwiczenia/{d['key']}.webp?v={m.get('v', 1)}" if m else None)
        d.pop("created_at", None); d.pop("updated_at", None)
        out.append(d)
    return out
