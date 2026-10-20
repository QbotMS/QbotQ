---
tytul: Adres domowy (dom QBota)
dzial: system
typ: ustawienie
opis: Jeden punkt „dom” dla całego QBota — adres podany w SETUP > Użytkownik albo dokładny punkt wyliczony z jazd.
tagi: [dom, adres, uzytkownik, setup, pogoda, brama, trener]
synonimy: [adres domowy, mój dom, home, lokalizacja domu, punkt domu, moja pogoda]
skroty: []
gdzie_widac: [SETUP, Pogoda, Trener, Dziś, Brama]
liczby: [300 m, 0,01°]
zalezy_od: []
wplywa_na: [../pogoda/index, ../trener/index, ../qext2/brama]
zrodla_kodu: [qbot_home.py home point save clear geocode, qbot_web.py setup_user_get setup_user_save setup_geocode, qbot_trener_engine.py home_point, qbot_pogoda.py home, web/public/setup.html uLoad uFind uPost]
aktualizacja: 20.10.2026
---

# Adres domowy (dom QBota)

## Co to jest

„Dom” to jeden punkt, którego używa cały QBot: pogoda „Moja” na stronie Pogoda i na tarczy dnia, pogoda w planie Trenera oraz punkt bramy dla pola BRAMA na Karoo.

## Skąd dane

1. **Adres z SETUP → Użytkownik**, jeśli go podasz. Wpisujesz ulicę i miejscowość, wybierasz właściwą propozycję (wyszukiwarka OpenStreetMap), a pinezkę na mapie możesz przesunąć.
2. **Bez adresu** QBot liczy dom z jazd: bierze 120 ostatnich jazd, szuka kratki ok. 1 × 1 km, z której startujesz najczęściej, i bierze środek startów w tej kratce. Dokładność to ok. 100 m.

## Decyzje i historia

- 20.10.2026: Pogoda i Trener zaokrąglały dom do 0,1° (kratka ok. 11 km), przez co punkt „Moja” był ok. 5 km od domu. Brama liczyła dokładnie, a starsze narzędzia używały centrum Warszawy. Od teraz wszystko korzysta z jednego punktu. Decyzja Michała: adres można podać ręcznie w SETUP → Użytkownik.

## Ograniczenia i pułapki

Zapis adresu przestawia od razu punkt bramy na serwerze. Karoo pamięta swój punkt bramy (pobrany wcześniej) — po dużej zmianie adresu pole BRAMA może przez chwilę oceniać odległość od starego punktu.

## Powiązane hasła

- [Brama z Karoo](../qext2/brama.md)
- [Status](status.md)

## Zrodla

- `qbot_home.py` — jedno źródło domu. Dok.: `docs/DOM.md`.
- `qbot_web.py` — `/api/setup/user`, `/api/setup/geocode`.
- `web/public/setup.html` — zakładka „Użytkownik”.
