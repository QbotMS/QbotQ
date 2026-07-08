"""Filar 0 -- Sygnatura fitness (TP, HIE, PP).

Trzy parametry opisuja cala krzywa mocy (patrz SPEC Filar 0):
  TP  -- Threshold Power (W), prog. Odpowiednik CP/FTP.
  HIE -- High Intensity Energy (J w srodku, kJ na zewnatrz), pojemnosc nad TP. Odpowiednik W'.
  PP  -- Peak Power (W), moc chwilowa 1s.

Klasa jest CZYSTA: bez I/O, bez zaleznosci od bazy. Tylko dane + walidacja + pochodne.
"""
from __future__ import annotations
from dataclasses import dataclass
import math


@dataclass
class Signature:
    tp_w: float            # Threshold Power [W]
    hie_j: float           # High Intensity Energy [J]  (uwaga: J, nie kJ)
    pp_w: float            # Peak Power [W]

    # --- walidacja fizjologiczna ---
    def __post_init__(self) -> None:
        if self.tp_w <= 0:
            raise ValueError(f"TP musi byc > 0, jest {self.tp_w}")
        if self.hie_j <= 0:
            raise ValueError(f"HIE musi byc > 0, jest {self.hie_j}")
        if self.pp_w <= self.tp_w:
            raise ValueError(f"PP ({self.pp_w}) musi byc > TP ({self.tp_w})")

    # --- wygodne konwersje ---
    @property
    def hie_kj(self) -> float:
        return self.hie_j / 1000.0

    @classmethod
    def from_kj(cls, tp_w: float, hie_kj: float, pp_w: float) -> "Signature":
        return cls(tp_w=float(tp_w), hie_j=float(hie_kj) * 1000.0, pp_w=float(pp_w))

    # --- pochodne (SPEC Filar 4) ---
    @property
    def ltp_w(self) -> float:
        """Lower Threshold Power = TP - HIE/400 (wzor Xert, HIE w J). Zweryfikowany."""
        return self.tp_w - self.hie_j / 400.0

    def power_for_duration(self, t_s: float) -> float:
        """Krzywa mocy z sygnatury (Focus Power dla czasu t) -- model 2-param
        z zaginajacym PP na krotkim koncu. Uzywane do walidacji/predykcji.
        P(t) = TP + (HIE/t) * (1 - exp(-t*(PP-TP)/HIE))
          t->0  -> PP ; t->inf -> TP. Pole nad TP = HIE.
        """
        if t_s <= 0:
            return self.pp_w
        return self.tp_w + (self.hie_j / t_s) * (1.0 - math.exp(-t_s * (self.pp_w - self.tp_w) / self.hie_j))

    def to_dict(self) -> dict:
        return {"tp_w": round(self.tp_w, 1), "hie_kj": round(self.hie_kj, 2), "pp_w": round(self.pp_w, 1),
                "ltp_w": round(self.ltp_w, 1)}

    def __repr__(self) -> str:
        return f"Signature(TP={self.tp_w:.0f}W, HIE={self.hie_kj:.1f}kJ, PP={self.pp_w:.0f}W, LTP={self.ltp_w:.0f}W)"
