import sys, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

FFFD = chr(0xfffd)
base = 'C:/Users/rafae/projects/LabX/'

SWIM  = '\U0001f3ca'
MEDAL = '\U0001f3c5'
TROPHY= '\U0001f3c6'
CHART = '\U0001f4ca'
SWIM2 = '\U0001f3ca'
TIMER = '⏱'

def fix(fname, replacements):
    path = base + fname
    with open(path, encoding='utf-8') as f:
        c = f.read()
    changed = 0
    for old, new in replacements:
        if old in c:
            n = c.count(old)
            c = c.replace(old, new)
            changed += n
            print(f'  {n}x {repr(old[:70])}')
    if changed:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(c)
        print(f'  Saved {fname}')

# landing.html: badges have emoji + FFFD remainder; buttons have FFFD?FFFD
fix('landing.html', [
    # badges: emoji was inserted but FFFD spacer remains after it
    (f'\U0001f3ca {FFFD}',   f'\U0001f3ca '),
    (f'\U0001f3c3 {FFFD}',   f'\U0001f3c3 '),
    (f'\U0001f3c5 {FFFD}',   f'\U0001f3c5 '),
    # Filter buttons (not yet fixed)
    (f"calFilter(this,'marathon')\">{FFFD}?{FFFD}",   f"calFilter(this,'marathon')\">{MEDAL}"),
    (f"calFilter(this,'triathlon')\">{FFFD}?{FFFD}",  f"calFilter(this,'triathlon')\">{TROPHY}"),
    # Fallback if different pattern
    (f"calFilter(this,'marathon')\">{FFFD}?",   f"calFilter(this,'marathon')\">{MEDAL}"),
    (f"calFilter(this,'triathlon')\">{FFFD}?",  f"calFilter(this,'triathlon')\">{TROPHY}"),
    (f"calFilter(this,'marathon')\">{FFFD}",    f"calFilter(this,'marathon')\">{MEDAL} "),
    (f"calFilter(this,'triathlon')\">{FFFD}",   f"calFilter(this,'triathlon')\">{TROPHY} "),
])

# blood_labs.html: emoji + FFFD spacer
fix('blood_labs.html', [
    (f'\U0001f4ca {FFFD}', f'\U0001f4ca '),
])

# nutrition.html: emoji + FFFD spacer
fix('nutrition.html', [
    (f'\U0001f3ca {FFFD}', f'\U0001f3ca '),
    (f'⏱ {FFFD}',          f'⏱ '),
])

# registro.html: SVG text still broken
fix('registro.html', [
    # The SVG has remaining FFFD?FFFD or FFFD sequences
    (f'rgba(16,185,129,.9))">?{FFFD}?</text>', 'rgba(16,185,129,.9))">LX</text>'),
    (f'rgba(16,185,129,.9))">{FFFD}?{FFFD}</text>', 'rgba(16,185,129,.9))">LX</text>'),
    (f'rgba(16,185,129,.9))">{FFFD}?</text>', 'rgba(16,185,129,.9))">LX</text>'),
    (f'rgba(16,185,129,.9))">{FFFD}</text>', 'rgba(16,185,129,.9))">LX</text>'),
])

print('Done.')
