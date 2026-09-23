#!/usr/bin/env python3
"""Sprzatanie po sesji Analiza trasy v2 / goscie / sprzet (2026-09-23).

NIC NIE USUWA - PRZENOSI do /opt/qbot/app/_bak_archive/cleanup_20260923/ (z zachowaniem sciezek), wiec da sie cofnac.
Tylko pliki z tej sesji; kopie .bak watku Trenera (qbot_trener_*, trener-mock, forma.html, nav.*, qbot_query_handler,
db_introspection, albert/tool_registry sprzed 21:58) sa POMIJANE.
Uzycie:  cleanup_20260923.py          -> podglad listy
         cleanup_20260923.py --yes    -> przeniesienie + usuniecie 2 testowych zaproszen z bazy (@example.com, uniewaznione)
         cleanup_20260923.py --undo   -> przywrocenie plikow z archiwum
"""
import glob, os, shutil, sys

ARCH = "/opt/qbot/app/_bak_archive/cleanup_20260923"
W, A = "/opt/qbot/web/public/", "/opt/qbot/app/"
MINE_WEB = ["kalendarz2-data.js", "raport-gosc.js", "raport-jazdy2-gear.js", "raport-render.js", "raport-trasy.html",
            "raport-trasy2-plan.js", "raport-trasy2.js", "start2.js", "forma2-data.js", "raport-gosc.css", "raport-trasy2.css"]
MINE_APP = ["fitmodel/form_projection.py", "qbot3/routes/ride_invite.py", "qbot3/routes/route_attraction_sources.py",
            "qbot3/routes/route_meteo_engine.py", "qbot3/routes/route_ride_sim.py", "qbot3/routes/route_intro.py",
            "qbot3/routes/route_day_pack.py", "qbot3/routes/outfit_advisor.py", "qbot_web.py"]


def files():
    out = [W + f for f in ("raport-mock.js", "raport-mock-plan.js", "raport-mock.css", "raport-render-mock.js", "raport-trasy-mock.html")]
    for b in MINE_WEB:
        out += glob.glob(W + b + ".bak.*")
    out += [W + "raport-jazdy.html.bak.1790185623", W + "index.html.bak.stats"]
    for b in MINE_APP:
        out += glob.glob(A + b + ".bak.*")
    out += [A + "qbot3/llm/albert.py.bak.1790193494", A + "qbot3/tool_registry.py.bak.1790193494"]
    out += glob.glob(A + "scripts/_pack_test_*") + glob.glob(A + "scripts/_tmp_*.bak.*")
    return sorted({f for f in out if os.path.isfile(f)})


def main():
    if "--undo" in sys.argv:
        n = 0
        for root, _, fs in os.walk(ARCH):
            for f in fs:
                src = os.path.join(root, f)
                dst = "/" + os.path.relpath(src, ARCH)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst); n += 1
        print("przywrocono:", n)
        return
    fs = files()
    tot = sum(os.path.getsize(f) for f in fs)
    for f in fs:
        print("  ", f.replace("/opt/qbot/", ""))
    print("RAZEM: %d plikow, %.1f MB" % (len(fs), tot / 1e6))
    if "--yes" not in sys.argv:
        print("(podglad - nic nie zmieniono; uruchom z --yes)")
        return
    for f in fs:
        dst = ARCH + f
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(f, dst)
    print("przeniesiono do", ARCH)
    try:
        import psycopg
        c = psycopg.connect(host="127.0.0.1", dbname="qbot", user="qbot", password="")
        n = c.execute("DELETE FROM qbot_v2.ride_invite WHERE email LIKE '%@example.com' AND revoked_at IS NOT NULL").rowcount
        c.commit()
        print("usunieto testowych zaproszen:", n)
    except Exception as e:
        print("baza:", e)


if __name__ == "__main__":
    main()
