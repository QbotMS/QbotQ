import ast, os

PATH = "/opt/qbot/app/fitmodel/modelq2/publish.py"
s = open(PATH, encoding="utf-8").read()

old = """EF_ANCHOR_MIN_DAYS = 7      # najwyzej jedna auto-kotwica EF na tyle dni"""
new = """EF_ANCHOR_MIN_DAYS = 7      # najwyzej jedna auto-kotwica EF na tyle dni
EF_ANCHOR_DISABLED = True   # 2026-08-25: TYMCZASOWO wylaczona -- mediana 28d EF
                            # zanieczyszczona jazdami z wadliwym miernikiem w osi
                            # (7 jazd w kwarantannie 08.2026). Wlaczyc z powrotem
                            # ~2026-09-05 gdy okno 28d wypelni sie jazdami z pajaka.
                            # DECISIONS 2026-08-25."""

assert s.count(old) == 1
s = s.replace(old, new)

# dodaj early return na poczatku ef_anchor_step
old2 = '''def ef_anchor_step(conn, days_back: int = 45):
    """2026-08-11 (DECISIONS): przywrocenie EF do MQ2 po cutoverze z 17.07.'''
new2 = '''def ef_anchor_step(conn, days_back: int = 45):
    """2026-08-11 (DECISIONS): przywrocenie EF do MQ2 po cutoverze z 17.07.'''

# lepiej: wstawiam guard na poczatku ciala funkcji
old3 = '''    Cutover odlaczyl ftp_resolver i zaden pisarz nie wypelnial juz ef_med_28d --'''
new3 = '''    Cutover odlaczyl ftp_resolver i zaden pisarz nie wypelnial juz ef_med_28d --'''

# Najczysciej: wstawic if na poczatku funkcji po docstringu
# Szukam pierwszej linii kodu po docstringu
old_body = '    cur = conn.cursor()'
new_body = """    if EF_ANCHOR_DISABLED:
        return {"ef_anchor": "DISABLED (EF zanieczyszczone, patrz DECISIONS 2026-08-25)"}
    cur = conn.cursor()"""

assert s.count(old_body) == 1
s = s.replace(old_body, new_body, 1)
ast.parse(s)
open(PATH, "w", encoding="utf-8").write(s)
print("PATCH OK")
os.remove(__file__)
