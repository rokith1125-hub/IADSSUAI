"""
Validate disease model-label alignment with dataset.

Checks:
- disease_cnn.json labels coverage
- disease_data.json coverage
- optional disease_class_map.json coverage

Usage:
python scripts/validate_disease_alignment.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
MODEL_LABELS_PATH = ROOT / "ai_models" / "disease_cnn.json"
DATASET_PATH = ROOT / "datasets" / "disease_data.json"
CLASS_MAP_PATH = ROOT / "datasets" / "disease_class_map.json"
UNRESOLVED_REPORT = ROOT / "datasets" / "disease_unmapped_labels.json"


def _norm(value: str) -> str:
    text = str(value or "").lower().replace("___", " ").replace("_", " ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _load_model_labels() -> List[str]:
    raw = json.loads(MODEL_LABELS_PATH.read_text(encoding="utf-8"))
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        raw = raw[0]
    if isinstance(raw, dict) and "labels" in raw:
        raw = raw["labels"]
    if isinstance(raw, dict):
        labels = [str(v) for _, v in sorted(raw.items(), key=lambda kv: int(kv[0]))]
    elif isinstance(raw, list):
        labels = [str(v) for v in raw]
    else:
        labels = []
    return labels


def _load_dataset_names() -> List[str]:
    rows = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    return [str(row.get("disease_name", "")).strip() for row in rows if isinstance(row, dict)]


def _load_class_map() -> Dict[str, str]:
    if not CLASS_MAP_PATH.exists():
        return {}
    raw = json.loads(CLASS_MAP_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    mapping: Dict[str, str] = {}
    for key, value in raw.items():
        k = str(key or "").strip()
        v = str(value or "").strip()
        if not k or not v:
            continue
        mapping[k] = v
        mapping[_norm(k)] = v
    return mapping


def main() -> None:
    labels = _load_model_labels()
    dataset_names = _load_dataset_names()
    class_map = _load_class_map()

    dataset_norm = {_norm(name): name for name in dataset_names}
    resolvable = []
    unresolved = []
    skipped_healthy = []

    for label in labels:
        lower = label.lower()
        if "healthy" in lower or "normal" in lower:
            skipped_healthy.append(label)
            continue

        mapped_target = class_map.get(label) or class_map.get(_norm(label))
        if mapped_target:
            target_norm = _norm(mapped_target)
            if target_norm in dataset_norm:
                resolvable.append({
                    "label": label,
                    "method": "class_map",
                    "target": dataset_norm[target_norm],
                })
                continue

        label_norm = _norm(label)
        if label_norm in dataset_norm:
            resolvable.append({
                "label": label,
                "method": "direct_name",
                "target": dataset_norm[label_norm],
            })
        else:
            unresolved.append({"label": label})

    report = {
        "model_labels_total": len(labels),
        "dataset_diseases_total": len(dataset_names),
        "skipped_healthy_labels": len(skipped_healthy),
        "resolvable_labels": len(resolvable),
        "unresolved_labels": len(unresolved),
        "coverage_percent": round((len(resolvable) / max(1, len(labels) - len(skipped_healthy))) * 100, 2),
        "unresolved": unresolved,
    }

    UNRESOLVED_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nReport written: {UNRESOLVED_REPORT}")


if __name__ == "__main__":
    main()
