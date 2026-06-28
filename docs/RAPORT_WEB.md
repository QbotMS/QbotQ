# RAPORT WEB (qbot-web) — jak modelowac i wdrazac raport trasy

Status zywy (weryfikuj zawsze): raport trasy jest serwowany publicznie przez
usluge qbot-web. Ten plik to instrukcja dla kazdej nowej sesji.

## Usluga
- Kod: /opt/qbot/app/qbot_web.py  (FastAPI + StaticFiles, nasluch 0.0.0.0:30181, czysty HTTP)
- Web root: /opt/qbot/web/public/   (index.html = raport)
- systemd: qbot-web.service  (User=qbot). Restart NIE jest potrzebny przy zmianie
  pliku — StaticFiles czyta z dysku na biezaco.
- Publiczny adres: Cytrus albert.cytr.us -> olga181.mikrus.xyz:30181
  (port lokalny 30181 = port zewnetrzny; HTTPS dokłada Cytrus; apka oddaje HTTP).

## Struktura raportu (jeden plik index.html)
Cala tresc danych siedzi w jednym bloku JS oznaczonym DATA START / DATA END.
To JEDYNE co podmieniasz przy nowej trasie. Funkcja render() wstrzykuje dane do
elementow o id r-*.
Pola DATA:
- route: { name, id, distance_km, ascent_m, max_grade_pct }
- weather: { temp_c, wind_dir, wind_ms (ZAWSZE m/s), gust_ms, precip_pct, cloud_pct, sun, note }
- composition: [ { key, label, km, pct, color } ]  -> ribbon nawierzchni (sekcja 01)
- summary: tekst pod ribbonem
- alarms: [ { km_from, km_to, level (red|orange|info), reason, env (las|otwarte|null), note } ] (sekcja 02)
- narrative: [ akapity ] (sekcja 03)

## Mapa
Blok mapy to <div id="r-map"> z <img src="data:image/jpeg;base64,...">, wstawiany
NAD <div class="ribbon" id="r-ribbon"> w sekcji 01. Portrait, szerokosc ~460px.
Czysta mapa w base64 zwykle lezy na serwerze (np. /tmp/map_small_b64.txt).

## Jak wdrazac (KANAL ODPORNY NA KORUPCJE — to jest najwazniejsze)
Tresc raportu ma duzo nie-ASCII (polskie znaki, emoji) i base64 mapy. Te dwa
kanaly PSUJA tresc i nie wolno ich uzywac do zapisu raportu:
- NIE heredoc z trescia nie-ASCII / base64 (wstawia homoglify cyrylicy, niszczy base64).
- NIE dev_codex (parafrazuje base64 i tekst).
Uzywaj jednego z dwoch:
1) dev_write_file(path, content) z DEV MCP — zapis BAJT-W-BAJT, parametr content
   idzie przez JSON MCP (czysty). Allowlist obejmuje /opt/qbot/web. Robi .bak.
   To preferowana droga: jeden tool, bez gimnastyki.
2) Skladanie po stronie serwera (Python) + cp do /opt/qbot/web/public/index.html.
   Skladaj z plikow ktore juz sa czyste na serwerze, nie przesylaj duzych danych.

Po wdrozeniu ZAWSZE weryfikuj na zywo (bez dowodu nie ma sukcesu):
- md5sum zrodla vs /opt/qbot/web/public/index.html (musi sie zgadzac)
- curl -s -m 8 http://127.0.0.1:30181/ -> kod 200, rozmiar = rozmiar pliku
- grep data:image/jpeg w odpowiedzi (mapa obecna)
- decode UTF-8 bez bledu, brak znaku U+FFFD, brak bajtow sterujacych

## Konwencje
- Zawsze .bak (timestamp) przed nadpisaniem index.html.
- Wiatr ZAWSZE w m/s.
- Stopka makiety mowi "Liczby przyblizone" — alarmy/dane to tresc do podmiany
  z prawdziwego generatora trasy, nie wymyslaj ich.

## Artefakty na serwerze (stan z 2026-06-26)
- /tmp/makieta_final.html      — ostatni czysty zlozony raport (szkielet + mapa)
- /tmp/map_small_b64.txt       — czysta mapa w base64
- /tmp/build_raport.py         — skrypt skladajacy raport
- /tmp/html_in_b64.txt         — STARY, USZKODZONY base64 (nie uzywac)

## Historia / lekcja
Poprzednia sesja stracila czysty szkielet przy przesylaniu base64 heredokiem
(korupcja: homoglify cyrylicy + zniszczony ~320B blok w tablicy alarms).
Dlatego powstal dev_write_file i rozszerzono safe dev roots o /opt/qbot/web.
