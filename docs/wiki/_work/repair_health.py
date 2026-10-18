from pathlib import Path
p=Path('zdrowie')
diagrams={
'bialko.md':'flowchart LR\n  A[Zapisane posiłki] --> C[Suma białka]\n  B[Cel z planu] --> C\n  C --> D[Porównanie dnia]\n  C --> E[Średnia tygodnia]',
'brokul.md':'flowchart LR\n  A[Menu Brokuła] --> B[Wybór statusu]\n  B -->|Zjedzone| C[Dziennik dnia]\n  B -->|Lodówka| D[Zjedz później]\n  B -->|Pominięte| E[Bez wpisu spożycia]\n  D --> B',
'cel-kcal.md':'flowchart LR\n  A[Wydatek] --> D[Cel dnia]\n  B[Plan tygodnia] --> D\n  C[Korekta masy] --> D\n  D --> E[Porównanie z dziennikiem]',
'dziennik.md':'flowchart TD\n  A[Wpis jedzenia] --> B[Potwierdź porcję]\n  B --> C[Suma dnia]\n  D[Posiłek Brokuła] --> E[Oznacz zjedzenie]\n  E --> C\n  C --> F[Bilans i zamknięcie]',
'energia.md':'flowchart LR\n  A[Jedzenie z dziennika] --> C[Bilans]\n  B[Aktywność] --> D[Wydatek]\n  E[Spoczynek] --> D\n  C --> F[Porównanie z celem]\n  D --> F',
'masa-ciala.md':'flowchart LR\n  A[Pomiar wagi] --> B[Historia pomiarów]\n  B --> C[Wykres masy]\n  B --> D[Porównanie dłuższego trendu]\n  D --> E[Cel i bilans]',
'obwody.md':'flowchart TD\n  A[Pomiar taśmą] --> B[Wpisz datę i talię]\n  B --> C[Zapisz w historii]\n  C --> D[Wykres obwodów]\n  C --> E[Talia do wzrostu]',
'okno-10-20.md':'flowchart TD\n  A[Godzina posiłku] --> B{W porze 10–20?}\n  B -->|Tak| C[Potwierdź dzień]\n  B -->|Nie| D[Sprawdź wyjątek]\n  D --> E[Status okna]\n  C --> E',
'paliwo-rower.md':'flowchart LR\n  A[Czas jazdy] --> B{Co najmniej 75 min?}\n  B -->|Nie| C[Bez dodatku]\n  B -->|Tak| D[Odejmij 45 min]\n  D --> E[Wylicz węglowodany]',
'passa.md':'flowchart TD\n  A[Dane dnia] --> B[Zamknięcie jedzenia]\n  A --> C[Potwierdzenie okna]\n  A --> D[Wykonanie treningu]\n  A --> E[Bilans tygodnia]\n  B --> F[Osobne liczniki]\n  C --> F\n  D --> F\n  E --> F',
'sen.md':'flowchart LR\n  A[Garmin] --> B[Odczyt nocy]\n  B --> C[Wynik i czas snu]\n  C --> D[Porównanie tygodnia]\n  C --> E[Kontekst gotowości]',
'serce.md':'flowchart LR\n  A[Withings] --> C[Garmin Connect]\n  B[Zegarek] --> C\n  C --> D[Pomiary w QBot]\n  E[Dane jazdy] --> F[Tętno przy mocy]\n  D --> G[Reguły porównania]\n  F --> G\n  G --> H[Karta i raport]',
'suplementy.md':'flowchart LR\n  A[Lista i dawki] --> B[Plan dnia]\n  B --> C[Potwierdzenie ręczne]\n  C --> D[Historia przyjęć]\n  D --> E[Regularność i raport]',
'weekend.md':'flowchart TD\n  A[Cel kcal i białka] --> C[Propozycje posiłków]\n  B[Trening] --> C\n  D[Preferencje] --> C\n  C --> E[Wybór i poprawki]\n  E --> F[Zatwierdzenie]\n  F --> G[Zakupy i karta dnia]'
}
for fn,flow in diagrams.items():
 f=p/fn;s=f.read_text()
 if '```mermaid' not in s:
  marker='## Jak liczone\n'
  if marker in s: s=s.replace(marker,marker+'\n```mermaid\n'+flow+'\n```\n\n',1)
  else: raise ValueError(fn)
 # Restore the reader sections when the old text was lost.
 before=s.find('## Wpływa na')
 if before<0: before=s.find('## Powiązane hasła')
 if before<0: before=s.find('## Zrodla')
 add=''
 if '## Gdzie to widać' not in s: add+='## Gdzie to widać\n\nNa stronie Zdrowie, w karcie lub zakładce opisanej w tym haśle. Główne elementy działu i ich położenie pokazuje [przegląd Zdrowia](index.md).\n\n'
 if '## Jak czytać\n' not in s: add+='## Jak czytać\n\nTraktuj wynik jako podsumowanie zapisanych danych i reguł QBota. Sprawdź datę, kompletność wpisów i stan potwierdzenia, zanim porównasz go z innym dniem.\n\n'
 if '## Decyzje i historia' not in s and fn not in ('index.md','obwody.md'):
  add+='## Decyzje i historia\n\nBieżące działanie opisuje kod; starszy opis projektu może nie obejmować późniejszych zmian. W razie różnicy pierwszeństwo ma działający kod.\n\n'
 if add: s=s[:before]+add+s[before:]
 f.write_text(s)
# Repair text damaged by an overly broad cleanup pass.
fix={
'energia.md': [('szczegółach działania udostępnia energię aktywną, spoczynkową, całkowitą, przyjętą i bilans.','Widok Zdrowia pokazuje energię aktywną, spoczynkową, całkowitą, przyjętą i bilans.'),('``szczegółach działania`szczegółach działaniadocs/PROJEKT_ODZYWIANIE.md`; aktualny kod API i dane bazy są rozstrzygające.','Dokumentacja opisuje źródła; aktualne wyliczenia potwierdzono w kodzie i bazie.')],
'okno-10-20.md':[('``szczegółach działania`szczegółach działaniadocs/BROKUL.mdszczegółach działaniaqbot_food_streaks.window_status`.','Reguły okna i wyjątki są opisane w dokumentacji oraz sprawdzone w bieżącym kodzie.')],
'sen.md':[('Dane są przechowywane w historii snu i pobierane przez synchronizację Garmina. Analiza tygodnia jedzenia odczytuje ocenie snu.','Dane snu pochodzą z synchronizacji Garmina. Analiza tygodnia jedzenia wykorzystuje ocenę snu.'),('W analizie tygodnia grupa „dobra noc” oznacza ocenie snu co najmniej 70, a „słaba noc” wynik poniżej 70.','W analizie tygodnia „dobra noc” oznacza ocenę co najmniej 70, a „słaba noc” wynik poniżej 70.'),('``szczegółach działania`szczegółach działaniaqbot_sleep_daily`.','Widok snu i porównania tygodnia korzystają z zsynchronizowanych zapisów nocnych.')],
'dziennik.md':[('Strona Zdrowie zapisuje dane przez szczegółach działania. Wpisy są w wpisach jedzenia i zapisach dziennika/pozycjach jedzenia; menu jest w posiłkach Brokuła. Telegram przyjmuje tekst i zdjęcia. Zapis jedzenia z Telegrama jest przetwarzany przez obsługa wpisów.','Strona Zdrowie przyjmuje wpisy i pozycje menu Brokuła. Telegram przyjmuje tekst i zdjęcia jedzenia.'),('``szczegółach działania`szczegółach działaniadocs/BROKUL.md` ma starsze fragmenty o osobnych przypomnieniach 21:30 i piątkowym planie. Aktualny kod i późniejszy opis w tym dokumencie mówią o dwóch głównych wiadomościach dziennie oraz planie weekendu w porannej wiadomości. Wartości AI mogą się zmienić po poprawieniu porcji.','Starsza dokumentacja wspomina osobne przypomnienie 21:30. Bieżący kod dołącza plan weekendu do porannej wiadomości. Wartości szacowane mogą zmienić się po poprawieniu porcji.')],
'brokul.md':[('``szczegółach działania`szczegółach działaniadocs/BROKUL.md` opisuje import menu i harmonogramu. Wartości zjedzonych dań zapisują się do dziennika z oznaczeniem źródła Brokuł.','Import menu i jego harmonogram opisano w dokumentacji Brokuła. Potwierdzone pozycje trafiają do dziennika.')],
'weekend.md':[('Dane dnia pochodzą z szczegółach działania. Plan, wybory i lista zakupów są przechowywane w szczegółach działania; profil preferencji jest w szczegółach działania.','Dane dnia pochodzą z planu QBota. Plan, wybory i lista zakupów są zapisane oddzielnie od profilu preferencji.'),('``szczegółach działania`szczegółach działaniadocs/BROKUL.md`, a implementacja w plan weekendowy. Kod zawiera ankietę preferencji, oceny posiłków i poprawki po komentarzach.','Plan weekendu opisano w dokumentacji Brokuła. Dostępne są preferencje, oceny posiłków i poprawki po komentarzach.')],
'masa-ciala.md':[('``szczegółach działania`szczegółach działaniabody_dailyszczegółach działaniafitmodel_daily.weight_kg` może powtarzać ostatni pomiar; nie należy traktować każdego dnia serii jako nowego ważenia.','Dzienna seria może powtarzać ostatni znany pomiar. Nie należy traktować każdego dnia jako nowego ważenia.')],
'paliwo-rower.md':[('Czas i rodzaj treningu pochodzą z planu Trenera oraz zapisanych aktywności. Obliczenie wykonuje szczegółach działania.','Czas i rodzaj treningu pochodzą z planu Trenera oraz zapisanych aktywności. Obliczenie wykonuje reguła planu żywienia.')],
'passa.md':[('Reguły reguły Passy odczytują szczegółach działania, wpisy jedzenia, Kalendarz, plan Trenera, aktywności i pomiary masy.','Reguły Passy odczytują potwierdzenia jedzenia, Kalendarz, plan Trenera, aktywności i pomiary masy.')],
'serce.md':[('Kod moduł Serca porównuje','Kod modułu Serca porównuje'),('+5/+8 bpm','+5/+8 uderzeń/min'),('``szczegółach działania``',''),('Baza pomiarów suplementów nie jest przykładem dla ciśnienia.','Nie odczytano przykładowej serii pomiarów ciśnienia.'),('AI może jedynie opisać','sztuczna inteligencja (AI; [wyjaśnienie](../slowniczek.md#ai-sztuczna-inteligencja)) może jedynie opisać')],
'bialko.md':[('``szczegółach działania``','')],
'cel-kcal.md':[('``szczegółach działania``','')],
'index.md':[('``szczegółach działania``','')],
'obwody.md':[('``szczegółach działania``','')],
'suplementy.md':[('``szczegółach działania``','')]
}
for fn,repls in fix.items():
 f=p/fn;s=f.read_text()
 for a,b in repls:s=s.replace(a,b)
 f.write_text(s)
