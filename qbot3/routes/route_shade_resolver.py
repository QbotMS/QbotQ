"""Resolver cienia per segment trasy — transmitancja wiazki bezposredniej (fdir).

Czysta interpretacja warstwy qbot_v2.route_shade_layer (surowe klasy ESA WorldCover
w przekroju + heading). NIE dotyka bazy, pogody ani WBGT. Zwraca tau in [0,1];
konsument (route_analysis_run) stosuje: fdir_eff = fdir_base * tau.

Regula (uzgodniona, oparta na danych trasy 55798129):
- Cien liczy TYLKO klasa 10 (drzewa). Zabudowa(50)/uprawy(40)/trawa(30)/woda(80) = brak cienia.
- Oba boki las (lub srodek=las) -> tunel -> tau = TAU_CANOPY (0.10; preswit w koronie). ~54% trasy.
- Jeden bok las -> liczy sie strona slonca (azymut vs heading) + taper wysokosci slonca. ~18%.
- Odkryte -> tau = 1.0. ~28%.
- Slonce za nisko (cossza < CZA_MIN, stala solvera) -> brak wiazki -> tau = 1.0.
- coverage_status != ok/partial -> tau = 1.0 (nie zmyslamy cienia).

Geometria slonca: qbot_wbgt_tools.cos_solar_zenith / solar_azimuth_deg (jedno zrodlo, bez driftu).
Dok.: docs/PROJEKT_METEO.md (Watek 1, Tier 2), docs/PROJEKT_OTOCZENIE.md (warstwa zrodlowa).
"""
from __future__ import annotations

from datetime import datetime

from qbot_wbgt_tools import CZA_MIN, cos_solar_zenith, solar_azimuth_deg

TREE = 10                 # ESA WorldCover: drzewa (jedyna klasa liczona jako cien)

TAU_CANOPY = 0.10         # tunel / oba boki: 90% wiazki zablokowane, 10% przez preswit w koronie
TAU_PARTIAL = 0.50        # jeden bok, las tylko w probce 20 m (nie 10 m)

COSZA_LOW = 0.30          # ~17.5 st nad horyzontem: ponizej -> pelna sila cienia bocznego
COSZA_HIGH = 0.85         # ~58 st: powyzej -> przydrozny jednostronny las prawie nie cieni


def _side(c10, c20) -> int:
    """Sila lasu po jednej stronie: 0 brak / 1 czesciowy (tylko 20 m) / 2 pelny (10 m)."""
    if c10 == TREE:
        return 2
    if c20 == TREE:
        return 1
    return 0


def _elevation_factor(cza: float) -> float:
    """Taper wysokosci dla przypadku jednostronnego: 0 (pelny cien) -> 1 (brak cienia bocznego)."""
    if cza <= COSZA_LOW:
        return 0.0
    if cza >= COSZA_HIGH:
        return 1.0
    return (cza - COSZA_LOW) / (COSZA_HIGH - COSZA_LOW)


def segment_tau(row: dict, dt_utc: datetime, lat: float, lon: float) -> float:
    """Transmitancja wiazki bezposredniej dla segmentu o czasie przejazdu dt_utc.

    row: wiersz route_shade_layer (class_left_10/20, class_center, class_right_10/20,
         heading_deg, coverage_status). dt_utc/lat/lon: stan w momencie przejazdu segmentu.
    Zwraca tau in [0,1]: fdir_eff = fdir_base * tau.
    """
    if row.get("coverage_status") not in ("ok", "partial"):
        return 1.0  # brak wiarygodnego pokrycia -> nie zmyslamy cienia

    cza = cos_solar_zenith(dt_utc, lat, lon)
    if cza < CZA_MIN:
        return 1.0  # slonce za nisko: brak wiazki bezposredniej (solver i tak zeruje fdir)

    left = _side(row.get("class_left_10"), row.get("class_left_20"))
    right = _side(row.get("class_right_10"), row.get("class_right_20"))

    # 1) Tunel / oba boki las (lub srodek) -> cien niezalezny od azymutu.
    if (left == 2 and right == 2) or row.get("class_center") == TREE:
        return TAU_CANOPY

    # 2) Zaden bok nie ma lasu -> odkryte.
    if left == 0 and right == 0:
        return 1.0

    # 3) Jeden bok las -> liczy sie, czy slonce pada od strony lasu.
    az = solar_azimuth_deg(dt_utc, lat, lon)
    heading = float(row.get("heading_deg") or 0.0)
    rel = ((az - heading + 540.0) % 360.0) - 180.0  # <0 slonce z lewej, >0 z prawej
    sun_side = left if rel < 0 else right
    if sun_side == 0:
        return 1.0  # slonce od strony odkrytej -> brak cienia

    base = TAU_CANOPY if sun_side == 2 else TAU_PARTIAL
    f = _elevation_factor(cza)
    return base + f * (1.0 - base)  # nisko -> base (cien); wysoko -> 1.0 (brak cienia bocznego)
