# Dom QBota (20.10.2026, sesja dom-2010)

Jedno zrodlo: `qbot_home.py`.
1. `qbot_v2.app_settings` klucz `user_home` = {address, lat, lon, saved} z SETUP > Uzytkownik (zakladka w setup.html, API
   `/api/setup/user` GET/POST {address,lat,lon} | {clear:true}, wyszukiwarka `/api/setup/geocode?q=` = Nominatim, countrycodes=pl).
2. Bez adresu: 120 ostatnich jazd, komorka 0,01 st z najwieksza liczba startow, mediana startow (dokladnosc ~100 m).
   Cache w procesie 10 min (wynik z jazd 24 h); zapis czysci cache.
Odbiorcy: `qbot_trener_engine.home_point` (Trener: pogoda planu, powiadomienia, qbot_web), `qbot_pogoda.home` (/api/pogoda/dom:
Pogoda "Moja", tarcza dnia), brama: zapis/usuniecie adresu nadpisuje `/opt/qbot/artifacts/gate_home.json` (qbot_qlab_server._gate_home,
promien 300 m; GATE_LAT/GATE_LON w .env nadal maja pierwszenstwo).
Przed 20.10: Trener/Pogoda zaokraglaly do 0,1 st (~5 km bledu), mcp_server LOCATION_* = centrum Warszawy (zostaje tylko jako
domyslna nazwa w starym narzedziu get_weather).
Karoo cache'uje punkt bramy (prefs `qext2_gate`) i pobiera go tylko, gdy go nie ma.

## Mapy: plynne skalowanie (20.10.2026)
`qmap-tiles.js smoothWheel(map)` (wywolanie w `qTilesAttach`): kolko myszy / gladzik = ciagly zoom w rytmie klatek
(wzor Leaflet.SmoothWheelZoom, MIT), punkt pod kursorem stoi; wbudowany scrollWheelZoom wylaczony. Dotyk i przyciski bez zmian.
Wszystkie strony z qmap-tiles.js?v=17.
