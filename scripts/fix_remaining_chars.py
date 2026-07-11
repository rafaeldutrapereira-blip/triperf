import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

base = 'C:/Users/rafae/projects/LabX/'

def fix_file(fname, replacements):
    path = base + fname
    with open(path, encoding='utf-8') as f:
        content = f.read()
    changed = 0
    for old, new in replacements:
        if old in content:
            n = content.count(old)
            content = content.replace(old, new)
            changed += n
            print(f'  {n}x: {repr(old[:60])}')
    if changed:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'  Saved {fname}')
    return changed

FFFD  = '�'
SWIM  = '\U0001f3ca'   # 🏊
RUN   = '\U0001f3c3'   # 🏃
MEDAL = '\U0001f3c5'   # 🏅
CHART = '\U0001f4ca'   # 📊
CLIP  = '\U0001f4cb'   # 📋
TIMER = '⏱'       # ⏱
DOT   = '●'       # ●

fix_file('athlete.html', [
    (f'color:var(--green);font-size:1rem">{FFFD}?</span>', f'color:var(--green);font-size:1rem">{DOT}</span>'),
    (f'color:var(--green);font-size:1rem">??</span>',       f'color:var(--green);font-size:1rem">{DOT}</span>'),
])

fix_file('landing.html', [
    (f'class="lx-badge kb-swim">{FFFD}?', f'class="lx-badge kb-swim">{SWIM} '),
    (f'class="lx-badge kb-run">{FFFD}?',  f'class="lx-badge kb-run">{RUN} '),
    (f'color:rgba(168,85,247,.3)">{FFFD}?', f'color:rgba(168,85,247,.3)">{MEDAL} '),
])

fix_file('blood_labs.html', [
    (f"\"switchTab('resumen',this)\">{FFFD}?", f"\"switchTab('resumen',this)\">{CHART} "),
    (f"'switchTab('resumen',this)'>{FFFD}?",   f"'switchTab('resumen',this)'>{CHART} "),
])

fix_file('nutrition.html', [
    (f"setRace('olympic',this)\">{FFFD}?", f"setRace('olympic',this)\">{SWIM} "),
    (f'class="kpi-l">{FFFD}?',             f'class="kpi-l">{TIMER} '),
    (f"switchTab('plan',this)\">{FFFD}?",  f"switchTab('plan',this)\">{CLIP} "),
])

fix_file('registro.html', [
    (f'rgba(16,185,129,.9))">?{FFFD}?</text>', 'rgba(16,185,129,.9))">LX</text>'),
    (f'rgba(16,185,129,.9))">??</text>',        'rgba(16,185,129,.9))">LX</text>'),
    (f'rgba(240,165,0,.1)">{FFFD}??',          f'rgba(240,165,0,.1)">{MEDAL}'),
    ('\U0001f9d1�?\U0001f4bc',             '\U0001f9d1‍\U0001f4bc'),
])

print('All done.')
