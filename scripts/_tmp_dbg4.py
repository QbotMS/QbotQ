p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()
# entMap jest definiowany wewnatrz load(), ale renderDziennik go nie widzi bo jest var w load
# Szukam definicji
i=s.index("var entMap")
print("entMap at:", i)
print(repr(s[i:i+100]))
# jest wewnatrz load() -> renderDziennik widzi go przez closure -> powinno dzialac
# Ale! renderDziennik uzywa `days` z cal — a `cal` jest globalna zmienną. Sprawdzam
print("cal assignment:", s.count("cal=await"))
# sprawdzam calą sekwencje load
load_start=s.index("async function load()")
load_end=s.index("\n}", load_start)+2
print("load function:")
print(s[load_start:load_end])
