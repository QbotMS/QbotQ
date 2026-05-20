#!/usr/bin/env python3
"""Heuristics for mapping free-form gear notes into garage tool calls."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


GearSaver = Callable[[str, dict | None], object]


PERSONAL_GEAR_KEYWORDS = {
    "helmet": ["kask", "helmet"],
    "shoes": ["but", "buty", "shoe", "shoes"],
    "jersey": ["koszul", "jersey", "bluza", "base layer", "base-layer"],
    "bib_shorts": ["spoden", "bib", "spodnie", "szort"],
    "jacket": ["kurtk", "jacket", "shell"],
    "vest": ["kamizelk", "vest"],
    "gloves": ["rękaw", "rekaw", "glov"],
    "socks": ["skarp"],
    "arm_warmers": ["rękawk", "rekawk", "arm warmer"],
    "leg_warmers": ["nogawk", "leg warmer"],
    "glasses": ["okular", "glasse", "eyewear"],
    "cap": ["czapk", "cap", "komin", "buff", "neck gaiter"],
    "bag": ["plecak", "torba", "bag", "sakwa"],
    "other": [],
}

COMPONENT_KEYWORDS = {
    "tires": ["opon", "tire", "tyre", "guma"],
    "chain": ["łańcuch", "lancuch", "chain"],
    "cassette": ["kaset", "cassette"],
    "brakes": ["hamulc", "brake", "klock", "tarcz"],
    "saddle": ["siod", "saddle"],
    "pedals": ["peda", "pedal"],
    "wheels": ["koł", "kol", "wheel", "rim", "obręcz", "obrecz"],
    "handlebar": ["kierown", "bar", "hood"],
    "stem": ["mostk", "stem"],
    "drivetrain": ["przerzut", "napęd", "naped", "groupset", "napinacz"],
    "computer": ["komputer", "licznik", "garmin", "karoo"],
    "lights": ["lamp", "light", "świat", "swiat"],
    "other": [],
}

PERSONAL_ORDER = list(PERSONAL_GEAR_KEYWORDS.keys())
COMPONENT_ORDER = list(COMPONENT_KEYWORDS.keys())


@dataclass(frozen=True)
class GarageAction:
    tool: str
    payload: dict
    label: str


def _text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _match(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)


def classify_gear_text(text: str) -> GarageAction:
    """Return the best garage tool for a free-form equipment note."""
    t = _text(text)
    if not t:
        return GarageAction("save_memory", {}, "memory")

    if any(x in t for x in ["nowy rower", "kupiłem rower", "kupilem rower", "dodałem rower", "dodalem rower"]):
        bike_type = "gravel" if "gravel" in t or "grizl" in t else ("mtb" if "mtb" in t else ("road" if "szosa" in t else None))
        payload = {"name": text[:120], "notes": text}
        if bike_type:
            payload["type"] = bike_type
        return GarageAction("save_bike", payload, "bike")

    if any(x in t for x in ["fitting", "bikefit", "bike fit", "wysokość siodła", "wysokosc siodla", "klamkomanet", "reach", "stack", "drop", "ustawienie pozycji"]):
        return GarageAction(
            "save_memory",
            {"topic": "fitting_note", "content": text},
            "fitting:memory",
        )

    if any(x in t for x in ["rower", "rama", "gravel", "szosa", "mtb", "canyon", "grizl"]):
        if _match(t, COMPONENT_KEYWORDS["tires"]):
            return GarageAction("save_component", {"category": "tires", "notes": text}, "component:tires")
        if _match(t, COMPONENT_KEYWORDS["chain"]):
            return GarageAction("save_component", {"category": "chain", "notes": text}, "component:chain")
        if _match(t, COMPONENT_KEYWORDS["cassette"]):
            return GarageAction("save_component", {"category": "cassette", "notes": text}, "component:cassette")
        if _match(t, COMPONENT_KEYWORDS["brakes"]):
            return GarageAction("save_component", {"category": "brakes", "notes": text}, "component:brakes")

    for category in COMPONENT_ORDER:
        if category == "other":
            continue
        if _match(t, COMPONENT_KEYWORDS[category]):
            return GarageAction("save_component", {"category": category, "notes": text}, f"component:{category}")

    for category in PERSONAL_ORDER:
        if category == "other":
            continue
        if _match(t, PERSONAL_GEAR_KEYWORDS[category]):
            return GarageAction("save_gear", {"category": category, "notes": text}, f"gear:{category}")

    if any(x in t for x in ["odzie", "ubran", "strój", "stroj", "outfit"]):
        return GarageAction("save_gear", {"category": "other", "notes": text}, "gear:other")

    if any(x in t for x in ["opon", "łańcuch", "lancuch", "kaset", "hamulc", "siod", "peda", "koł", "kol"]):
        return GarageAction("save_component", {"category": "other", "notes": text}, "component:other")

    if any(x in t for x in ["kask", "but", "rękaw", "rekaw", "skarp", "czapk", "okular", "kamiz", "koszul", "spoden", "kurtk"]):
        return GarageAction("save_gear", {"category": "other", "notes": text}, "gear:other")

    return GarageAction("save_memory", {}, "memory")


def save_gear_text(mcp_call: Callable[[str, dict | None], object], text: str, *, topic: str | None = None) -> GarageAction:
    action = classify_gear_text(text)
    if action.tool == "save_memory":
        payload = {"topic": topic or "equipment_note", "content": text}
    elif action.tool == "save_component":
        payload = dict(action.payload)
        payload.setdefault("active", 1)
    else:
        payload = dict(action.payload)
        payload.setdefault("active", 1)
    result = mcp_call(action.tool, payload)
    return action if result else GarageAction("save_memory", {}, "memory")
