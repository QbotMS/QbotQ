"""Eksperyment 2026-10-04 (zgoda Michala): dubel jazdy 04.10 do Garmin Connect z progiem TP ModelQ.

Kopia /opt/qbot/artifacts/fit/24603122930.fit (= plik u Garmina, manufacturer juz przepisany),
w wiadomosci session (global 18) nadpisane W MIEJSCU 3 pola uint16 (rozmiar pliku bez zmian):
  45 threshold_power 247 -> 256, 36 intensity_factor (x1000), 35 training_stress_score (x10).
Nowa suma CRC pliku. Walidacja fitparse: wszystko poza tymi 3 polami identyczne. Potem upload.
Uzycie: .venv/bin/python3 scripts/garmin_dubel_ftp.py [--upload]
"""
from __future__ import annotations
import struct, sys
from pathlib import Path
sys.path.insert(0, "/opt/qbot/app")

SRC = Path("/opt/qbot/artifacts/fit/24603122930.fit")
OUT = Path("/opt/qbot/app/outgoing/garmin_dubel/24603122930_tp256.fit")
FTP_NEW = 256


def crc16(data: bytes, crc: int = 0) -> int:
    t = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
         0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]
    for b in data:
        tmp = t[crc & 0xF]; crc = (crc >> 4) & 0x0FFF; crc = crc ^ tmp ^ t[b & 0xF]
        tmp = t[crc & 0xF]; crc = (crc >> 4) & 0x0FFF; crc = crc ^ tmp ^ t[(b >> 4) & 0xF]
    return crc


def session_field_offsets(blob: bytes) -> dict[int, tuple[int, str]]:
    """Przechodzi rekordy FIT; zwraca {field_num: (offset_w_pliku, endian)} dla pol 35/36/45 sesji."""
    hsize = blob[0]
    data_size = struct.unpack_from("<I", blob, 4)[0]
    pos, end = hsize, hsize + data_size
    defs: dict[int, dict] = {}
    found: dict[int, tuple[int, str]] = {}
    while pos < end:
        h = blob[pos]; pos += 1
        if h & 0x80:  # compressed timestamp header -> data message
            local = (h >> 5) & 0x3
            d = defs[local]
            rec_start = pos
            pos += d["size"]
        elif h & 0x40:  # definition
            local = h & 0x0F
            has_dev = bool(h & 0x20)
            arch = blob[pos + 1]
            endian = ">" if arch == 1 else "<"
            gnum = struct.unpack_from(endian + "H", blob, pos + 2)[0]
            nf = blob[pos + 4]
            p = pos + 5
            fields, size = [], 0
            for _ in range(nf):
                fnum, fsize, btype = blob[p], blob[p + 1], blob[p + 2]
                fields.append((fnum, size, fsize)); size += fsize; p += 3
            if has_dev:
                nd = blob[p]; p += 1
                for _ in range(nd):
                    size += blob[p + 1]; p += 3
            defs[local] = {"gnum": gnum, "fields": fields, "size": size, "endian": endian}
            pos = p
            continue
        else:
            local = h & 0x0F
            d = defs[local]
            rec_start = pos
            pos += d["size"]
        if d["gnum"] == 18:
            for fnum, off, fsize in d["fields"]:
                if fnum in (35, 36, 45) and fsize == 2:
                    found[fnum] = (rec_start + off, d["endian"])
    return found


def main(upload: bool) -> None:
    import fitmodel._fitparse_compat  # noqa: F401
    from fitparse import FitFile
    blob = bytearray(SRC.read_bytes())
    sess = [{f.name: f.value for f in m.fields} for m in FitFile(str(SRC)).get_messages("session")][0]
    np_w, t = float(sess["normalized_power"]), float(sess["total_timer_time"])
    if_new = np_w / FTP_NEW
    tss_new = t * np_w * if_new / (FTP_NEW * 3600.0) * 100.0
    offs = session_field_offsets(bytes(blob))
    assert set(offs) == {35, 36, 45}, f"nie znaleziono pol sesji: {offs}"
    for fnum, val in ((45, FTP_NEW), (36, round(if_new * 1000)), (35, round(tss_new * 10))):
        o, e = offs[fnum]
        struct.pack_into(e + "H", blob, o, val)
    hsize = blob[0]
    data_size = struct.unpack_from("<I", blob, 4)[0]
    if hsize == 14:
        struct.pack_into("<H", blob, 12, crc16(bytes(blob[:12])))
    struct.pack_into("<H", blob, hsize + data_size, crc16(bytes(blob[:hsize + data_size])))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(bytes(blob))

    # walidacja: wszystkie wiadomosci identyczne poza 3 polami sesji
    def dump(path):
        out = []
        for m in FitFile(str(path), check_crc=True).get_messages():
            out.append((m.name, tuple((f.name, str(f.value)) for f in m.fields)))
        return out
    a, b = dump(SRC), dump(OUT)
    assert len(a) == len(b), "rozna liczba wiadomosci"
    diffs = [(x, y) for x, y in zip(a, b) if x != y]
    assert len(diffs) == 1 and diffs[0][0][0] == "session", f"nieoczekiwane roznice: {len(diffs)}"
    s2 = [{f.name: f.value for f in m.fields} for m in FitFile(str(OUT)).get_messages("session")][0]
    print(f"OK plik {OUT} ({len(blob)} B, wiadomosci {len(b)}, roznice tylko w session)")
    print(f"  threshold_power {sess['threshold_power']} -> {s2['threshold_power']}, "
          f"IF {sess['intensity_factor']} -> {s2['intensity_factor']}, "
          f"TSS {sess['training_stress_score']} -> {s2['training_stress_score']}")
    if upload:
        from garmin_auth import upload_activity
        try:
            print("UPLOAD:", upload_activity(OUT, method="upload"))
        except Exception as exc:
            msg = str(exc)
            print("UPLOAD BLAD:", "DUPLIKAT (409)" if ("Duplicate" in msg or "409" in msg) else "", msg[:300])


if __name__ == "__main__":
    main("--upload" in sys.argv)
