import ast, os

PATH = "/opt/qbot/app/fitmodel/modelq2/publish.py"
s = open(PATH, encoding="utf-8").read()

# 1. Dodaj flage
old1 = "EF_ANCHOR_MIN_DAYS = 7      # najwyzej jedna auto-kotwica EF na tyle dni"
new1 = """EF_ANCHOR_MIN_DAYS = 7      # najwyzej jedna auto-kotwica EF na tyle dni
EF_ANCHOR_DISABLED = True   # 2026-08-25: TYMCZASOWO wylaczona -- mediana 28d EF
                            # zanieczyszczona jazdami z wadliwym miernikiem w osi
                            # (7 jazd w kwarantannie 08.2026). Wlaczyc z powrotem
                            # ~2026-09-05 gdy okno 28d wypelni sie jazdami z pajaka.
                            # DECISIONS 2026-08-25."""
assert s.count(old1) == 1
s = s.replace(old1, new1)

# 2. Wstaw early return - szukam unikalnego fragmentu wewnatrz ef_anchor_step
old2 = '    """2026-08-11 (DECISIONS): przywrocenie EF do MQ2 po cutoverze z 17.07.\n\n    Cutover odlaczyl ftp_resolver'
new2 = '    """2026-08-11 (DECISIONS): przywrocenie EF do MQ2 po cutoverze z 17.07.\n\n    Cutover odlaczyl ftp_resolver'
# nie, lepiej szukam konca docstringa i wstawiam po nim
# szukam unikalnego markera w ef_anchor_step
marker = '    obsadza ef_med_28d w fitmodel_daily'
assert s.count(marker) == 1
# znajdz pozycje zamkniecia docstringa po tym markerze
pos = s.index(marker)
# szukam zamkniecia docstringa
docend = s.index('    """', pos + len(marker))
insert_pos = docend + len('    """') + 1  # +1 for newline
guard_code = "    if EF_ANCHOR_DISABLED:\n        return {\"ef_anchor\": \"DISABLED (EF zanieczyszczone, patrz DECISIONS 2026-08-25)\"}\n"
s = s[:insert_pos] + guard_code + s[insert_pos:]

ast.parse(s)
open(PATH, "w", encoding="utf-8").write(s)
print("PATCH OK")
os.remove(__file__)
