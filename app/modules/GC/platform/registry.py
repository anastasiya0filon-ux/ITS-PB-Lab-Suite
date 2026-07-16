# -*- coding: utf-8 -*-
"""Реестр подключаемых нормативных документов."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "methods" / "registry.json"


def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def list_methods() -> list[dict[str, Any]]:
    data = load_registry()
    return list(data.get("methods", []))


def get_method_entry(method_id: str) -> dict[str, Any]:
    for entry in list_methods():
        if entry.get("method_id") == method_id:
            return entry
    raise KeyError(f"Метод не зарегистрирован: {method_id}")


def load_method_module(method_id: str):
    entry = get_method_entry(method_id)
    return importlib.import_module(entry["adapter_module"])
