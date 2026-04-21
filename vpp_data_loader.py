"""
Inspect the first 10 lines of each price CSV to see the actual delimiter and structure.
Run: python inspect_csv.py
"""
import os
from config import DATA_DIR, HUB_PRICE_FILE, LAVENDER_NODE_FILE, FAIRWAY_NODE_FILE

for fname in [HUB_PRICE_FILE, LAVENDER_NODE_FILE, FAIRWAY_NODE_FILE]:
    fp = os.path.join(DATA_DIR, fname)
    print(f"\n{'='*70}")
    print(f"FILE: {fname}")
    print(f"Size: {os.path.getsize(fp) / 1e6:.1f} MB")
    print('='*70)

    for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']:
        try:
            with open(fp, 'r', encoding=enc) as f:
                print(f"(encoding: {enc})")
                for i, line in enumerate(f):
                    if i >= 10:
                        break
                    # Show raw line with delimiter hints
                    comma_count = line.count(',')
                    semi_count = line.count(';')
                    tab_count = line.count('\t')
                    print(f"Line {i+1} [commas={comma_count}, semicolons={semi_count}, tabs={tab_count}]: {line.rstrip()[:200]}")
            break
        except UnicodeDecodeError:
            continue
