"""
Bulk dataset importer for ULAGA_UNAVU.

Purpose:
- Safely merge large real datasets (1000+ rows) into existing JSON datasets.
- Validate schema fields.
- De-duplicate by id/name.

Usage example:
python scripts/bulk_import_dataset.py --entity disease --input data/new_disease.json --output datasets/disease_data.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


ENTITY_RULES = {
    "disease": {
        "id_key": "disease_id",
        "name_key": "disease_name",
        "id_prefix": "DS",
        "required": ["disease_name", "affected_crop", "severity_level", "treatment"],
    },
    "crop": {
        "id_key": "crop_id",
        "name_key": "crop_name",
        "id_prefix": "CR",
        "required": ["crop_name", "growing_season", "soil_compatibility", "risk_level"],
    },
    "soil": {
        "id_key": "soil_id",
        "name_key": "soil_name",
        "id_prefix": "ST",
        "required": ["soil_name", "ph_range", "suitable_crops"],
    },
}


def _norm(value: str) -> str:
    text = str(value or "").lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _load_json_list(path: Path) -> List[dict]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected list JSON: {path}")
    return data


def _validate_record(record: dict, required: List[str]) -> Tuple[bool, List[str]]:
    errors = []
    for key in required:
        value = record.get(key)
        if value is None:
            errors.append(f"missing '{key}'")
            continue
        if isinstance(value, str) and not value.strip():
            errors.append(f"empty '{key}'")
        if isinstance(value, list) and not value:
            errors.append(f"empty list '{key}'")
    return len(errors) == 0, errors


def _next_id(existing: List[dict], id_key: str, prefix: str) -> str:
    max_num = 0
    for row in existing:
        raw = str(row.get(id_key, ""))
        if raw.startswith(prefix):
            num_part = raw[len(prefix):]
            if num_part.isdigit():
                max_num = max(max_num, int(num_part))
    return f"{prefix}{max_num + 1:03d}"


def merge_dataset(entity: str, incoming: List[dict], existing: List[dict]) -> Dict[str, int]:
    rules = ENTITY_RULES[entity]
    id_key = rules["id_key"]
    name_key = rules["name_key"]
    id_prefix = rules["id_prefix"]
    required = rules["required"]

    by_id = {str(row.get(id_key, "")).strip().lower(): idx for idx, row in enumerate(existing) if row.get(id_key)}
    by_name = {_norm(row.get(name_key, "")): idx for idx, row in enumerate(existing) if row.get(name_key)}

    inserted = 0
    updated = 0
    rejected = 0

    for row in incoming:
        if not isinstance(row, dict):
            rejected += 1
            continue

        ok, _ = _validate_record(row, required)
        if not ok:
            rejected += 1
            continue

        record = dict(row)
        record_id = str(record.get(id_key, "")).strip()
        if not record_id:
            record_id = _next_id(existing, id_key=id_key, prefix=id_prefix)
            record[id_key] = record_id

        target_idx = None
        id_lookup = record_id.lower()
        name_lookup = _norm(record.get(name_key, ""))
        if id_lookup in by_id:
            target_idx = by_id[id_lookup]
        elif name_lookup and name_lookup in by_name:
            target_idx = by_name[name_lookup]

        if target_idx is None:
            existing.append(record)
            new_idx = len(existing) - 1
            by_id[id_lookup] = new_idx
            if name_lookup:
                by_name[name_lookup] = new_idx
            inserted += 1
        else:
            existing[target_idx] = record
            updated += 1

    return {"inserted": inserted, "updated": updated, "rejected": rejected, "total": len(existing)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk merge dataset JSON with schema validation")
    parser.add_argument("--entity", required=True, choices=sorted(ENTITY_RULES.keys()))
    parser.add_argument("--input", required=True, help="Input JSON file path (list of records)")
    parser.add_argument("--output", required=True, help="Target dataset JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Validate + report only, do not write file")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    incoming = _load_json_list(input_path)
    existing = _load_json_list(output_path) if output_path.exists() else []
    stats = merge_dataset(args.entity, incoming=incoming, existing=existing)

    if not args.dry_run:
        output_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "entity": args.entity,
        "input_records": len(incoming),
        "output_path": str(output_path),
        "dry_run": args.dry_run,
        **stats,
    }, indent=2))


if __name__ == "__main__":
    main()
