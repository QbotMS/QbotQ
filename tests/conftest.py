"""Wspolne ustawienia testow (15.10.2026).

BEZPIECZNIK: testy NIGDY nie wysylaja prawdziwych wiadomosci na Telegram. Incydent 15.10.2026: test logowania gościa (QR)
tworzyl prawdziwa prosbe o dostep -> serwer wysylal na Telegram "ktos prosi o dostep tymczasowy" przy kazdym pelnym
przebiegu testow (i w audycie tygodniowym). Ten plik przechwytuje wszystkie wywolania api.telegram.org (requests/httpx)
i zwraca udawana odpowiedz "ok" -- bez wychodzenia do sieci.
"""
import pytest


class _FakeResp:
    status_code = 200
    text = '{"ok":true,"result":{}}'

    def json(self):
        return {"ok": True, "result": {}}

    def raise_for_status(self):
        return None


def _is_tg(args, kwargs):
    url = kwargs.get("url") or (args[0] if args else "")
    return "api.telegram.org" in str(url)


@pytest.fixture(autouse=True)
def _no_real_telegram(monkeypatch):
    try:
        import requests
        _rp, _sp = requests.post, requests.Session.post

        def rpost(*a, **k):
            return _FakeResp() if _is_tg(a, k) else _rp(*a, **k)

        def spost(self, *a, **k):
            return _FakeResp() if _is_tg(a, k) else _sp(self, *a, **k)
        monkeypatch.setattr(requests, "post", rpost)
        monkeypatch.setattr(requests.Session, "post", spost)
    except ImportError:
        pass
    try:
        import httpx
        _hp, _cp = httpx.post, httpx.Client.post

        def hpost(*a, **k):
            return _FakeResp() if _is_tg(a, k) else _hp(*a, **k)

        def cpost(self, *a, **k):
            return _FakeResp() if _is_tg(a, k) else _cp(self, *a, **k)
        monkeypatch.setattr(httpx, "post", hpost)
        monkeypatch.setattr(httpx.Client, "post", cpost)
    except ImportError:
        pass
    yield
