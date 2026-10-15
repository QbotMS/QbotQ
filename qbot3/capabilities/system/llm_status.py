#!/usr/bin/env python3
"""Internal capability: llm_status (przepisane 15.10.2026).

Model AI, na ktorym FAKTYCZNIE dziala Albert = aktywny profil przelacznika modelu
(qbot3/llm/model_profiles.py, stan data/albert_model.json; przelaczanie: "przelacz na gpt/gemini/claude").
Poprzednia wersja czytala stara konfiguracje QGPT/OpenRouter (sprzed przelacznika) i pokazywala inny model
niz uzywany -- dwa sprzeczne zrodla. Teraz jedno zrodlo. Bez sekretow (tylko: czy klucz jest).
"""
from __future__ import annotations

from typing import Any

from qbot3.capabilities.base import Capability, CapabilityDef, PROMOTION_ACTIVE, SAFETY_READ_ONLY_CONFIG


class LlmStatusCapability(Capability):
    def manifest(self) -> CapabilityDef:
        return CapabilityDef(
            name="llm_status",
            description="Model AI, na ktorym dziala Albert (aktywny profil: gpt / gemini / claude, nazwa modelu, czy profil ma wlasny klucz). Tylko odczyt, bez sekretow.",
            safety_class=SAFETY_READ_ONLY_CONFIG,
            capability_type="READ_ONLY_CONFIG",
            data_sources=["data/albert_model.json", "qbot3/llm/model_profiles.py"],
            promotion_state=PROMOTION_ACTIVE,
            inputs_schema={},
            output_schema={"type": "object", "properties": {"profile": {"type": "string"}, "model": {"type": "string"}}},
            reason_existing_insufficient="Jedno zrodlo prawdy o modelu Alberta.",
        )

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from qbot3.llm.model_profiles import public_status, PROFILES
        p = public_status()
        key_txt = ("ma własny klucz" if p.get("key_present")
                   else "bez osobnego klucza profilu — używa klucza domyślnego Alberta")
        summary = f"Albert działa na: {p.get('label')} ({p.get('model')}); {key_txt}. Dostępne profile: {', '.join(PROFILES)}."
        data = {"profile": p.get("profile"), "label": p.get("label"), "model": p.get("model"),
                "base_url": p.get("base_url"), "profile_key_present": bool(p.get("key_present")),
                "available_profiles": list(PROFILES), "summary": summary}
        return {"status": "OK", "data": data, "summary": summary}
