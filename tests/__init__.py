"""Pakiet testow QBot.

Plik dodany 2026-07-26. Bez niego `python -m unittest discover` z /opt/qbot/app
zwracal "NO TESTS RAN" (katalog tests/ nie byl importowalny jako pakiet), przez co
39 plikow i ~386 przypadkow bylo niewidocznych dla domyslnego uruchomienia
i dla dev_run_tests. Same testy dzialaly - tylko nikt ich nie zbieral.
"""
