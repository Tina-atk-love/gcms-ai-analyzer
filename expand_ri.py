"""Continue expanding RI database from NIST WebBook. Run in background."""
import requests, re, time, json
from pathlib import Path
from public_library_manager import parse_msp_file

session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; GCMS-Research/3.1)'})
OUT = Path("public_libraries")

print("Loading library...")
entries = parse_msp_file(str(OUT / "ei_ms_combined.msp"))
ri_path = OUT / "nist_webbook_ri.json"

ri_db = json.load(open(ri_path, encoding="utf-8")) if ri_path.exists() else {}
existing = set(ri_db.keys())

candidates = [e for e in entries
             if e.get('name', '').strip().lower() not in existing
             and 3 <= len(e.get('name', '')) <= 100]

print(f"Current RI: {len(ri_db)} | To check: {len(candidates)} | ETA: {len(candidates)*0.5/3600:.1f}h")
print()

ri_new = 0
ri_checked = 0
start = time.time()

for e in candidates:
    name = e.get('name', '').strip()
    ri_checked += 1

    try:
        r = session.get(
            f"https://webbook.nist.gov/cgi/cbook.cgi?Name={name}&Units=SI&Mask=2000",
            timeout=6
        )
        if r.status_code == 200 and ('Gas Chromatography' in r.text or 'Kovats' in r.text):
            matches = re.findall(
                r'<td class="right-nowrap">\s*(\d{2,4}\.\d{1,2})\s*</td>',
                r.text
            )
            ri_vals = [float(m) for m in matches if 400 < float(m) < 4000]
            if ri_vals:
                ri_vals.sort()
                ri_db[name.lower()] = {
                    'ri': round(ri_vals[len(ri_vals) // 2], 1),
                    'all_ri': [round(v, 1) for v in ri_vals[:5]],
                    'n': len(ri_vals),
                    'cas': e.get('cas', ''),
                }
                ri_new += 1
    except Exception:
        pass

    if ri_checked % 50 == 0:
        elapsed = time.time() - start
        rate = ri_checked / elapsed if elapsed > 0 else 0
        remaining = len(candidates) - ri_checked
        eta_h = remaining / rate / 3600 if rate > 0 else 0
        with open(ri_path, 'w', encoding='utf-8') as f:
            json.dump(ri_db, f, indent=2, ensure_ascii=False)
        print(f"  [{ri_checked}/{len(candidates)}] RI={len(ri_db)} (+{ri_new}) ETA={eta_h:.1f}h")
        ri_new = 0
        time.sleep(0.5)

with open(ri_path, 'w', encoding='utf-8') as f:
    json.dump(ri_db, f, indent=2, ensure_ascii=False)

elapsed = time.time() - start
print(f"\nDONE! RI entries: {len(ri_db)} | Time: {elapsed/3600:.1f}h | Saved: {ri_path}")
