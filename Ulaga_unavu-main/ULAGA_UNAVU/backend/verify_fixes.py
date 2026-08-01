"""Quick verification script to confirm all 4 bug fixes are applied correctly."""
import json

print("=" * 60)
print("ULAGA_UNAVU - Fix Verification Script")
print("=" * 60)

# 1. Verify disease_class_map.json
print("\n[1] Checking disease_class_map.json...")
with open('datasets/disease_class_map.json', encoding='utf-8') as f:
    cmap = json.load(f)
print(f"    Entries: {len(cmap)} (was 7, expected 44+)")

# 2. Verify disease_data.json
print("\n[2] Checking disease_data.json...")
with open('datasets/disease_data.json', encoding='utf-8') as f:
    ddata = json.load(f)
print(f"    Entries: {len(ddata)} (was 13, expected 33)")

# 3. Check all class_map targets exist in disease_data
disease_names = {d['disease_name'] for d in ddata}
missing = []
for key, target in cmap.items():
    if target != 'Healthy' and target not in disease_names:
        missing.append(f"{key} -> {target}")

if missing:
    print(f"    WARNING: {len(missing)} targets missing in disease_data:")
    for m in missing:
        print(f"      {m}")
else:
    print("    All class_map targets found in disease_data - OK")

# 4. Verify router_registry.py
print("\n[3] Checking router_registry.py...")
with open('api/router_registry.py', encoding='utf-8') as f:
    content = f.read()
count = content.count('include_router(pdf_router')
status = "OK (1 mount)" if count == 1 else f"ISSUE ({count} mounts found)"
print(f"    PDF router mounts: {count} - {status}")

# 5. Verify detection.py weather fix
print("\n[4] Checking detection.py weather call fix...")
with open('api/disease/detection.py', encoding='utf-8') as f:
    det = f.read()
if 'get_current_weather(str(float(lat)), float(lon))' in det:
    print("    STILL WRONG - old 2-arg call found")
elif 'get_current_weather(f"' in det or "get_current_weather(f'" in det:
    print("    FIXED - single location string call - OK")
else:
    print("    UNKNOWN - check manually")

# 6. Verify App.jsx
print("\n[5] Checking App.jsx routing fix...")
with open('../frontend/src/App.jsx', encoding='utf-8') as f:
    jsx = f.read()
if '/crop-selection" element={<CropSelection' in jsx or "/crop-selection\" element={<CropSelection" in jsx:
    print("    FIXED - /crop-selection -> CropSelection - OK")
elif '/crop-selection" element={<CropRecommend' in jsx:
    print("    STILL WRONG - /crop-selection -> CropRecommend")
else:
    print("    Route not found - check manually")

print("\n" + "=" * 60)
print("Verification complete!")
print("=" * 60)
