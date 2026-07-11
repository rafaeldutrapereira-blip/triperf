import sys, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('C:/Users/rafae/projects/LabX/training_detail.html', encoding='utf-8') as f:
    c = f.read()

fixes = [
    # Back button
    ('← Ir al Plan de Entrenamiento',
     '<span data-i18n="td_back">← Ir al Plan de Entrenamiento</span>',
     None),

    # Zone distribution title
    ('Distribución de Zonas',
     '<span data-i18n="td_zones">Distribución de Zonas</span>',
     None),

    # Segment details title
    ('Detalles por Segmento',
     '<span data-i18n="td_laps">Detalles por Segmento</span>',
     None),

    # REPLAY button text
    ('▶ REPLAY',
     '<span data-i18n="td_replay">▶ REPLAY</span>',
     None),
]

count = 0
for old_text, new_text, _ in fixes:
    # Find the containing element and add data-i18n if not already there
    # Simple text replacement approach
    if old_text in c and 'data-i18n' not in c[c.find(old_text)-50:c.find(old_text)]:
        c = c.replace(old_text, new_text, 1)
        count += 1
        print(f'OK: {old_text[:40]}')
    else:
        print(f'SKIP: {old_text[:40]}')

# Add data-i18n to nav links that are using hardcoded text
# Sidebar nav items (these are in the shared sidebar)
nav_replacements = [
    ('Dashboard\n    </a>', 'data-i18n="nav_dashboard">Dashboard\n    </a>'),
    ('>Módulos<', ' data-i18n="nav_modules">Módulos<'),
    ('Entrenamiento\n    </a>', 'data-i18n="nav_training">Entrenamiento\n    </a>'),
    ('Nutrición\n    </a>', 'data-i18n="nav_nutrition">Nutrición\n    </a>'),
    ('Bienestar\n    </a>', 'data-i18n="nav_wellness">Bienestar\n    </a>'),
    ('Predictor\n    </a>', 'data-i18n="nav_predictor">Predictor\n    </a>'),
    ('Blood Labs\n    </a>', 'data-i18n="nav_labs">Blood Labs\n    </a>'),
]

# More targeted: find the sidebar nav links section
# The sidebar has links like: <a href="..." class="sb-lnk ...">SVG Dashboard</a>
# We need to add data-i18n to the text nodes - but since text is mixed with SVG,
# use a wrapper span approach

# Find all sidebar text links and wrap text in data-i18n spans
def add_i18n_to_nav_link(html, href_fragment, key):
    # Pattern: <a href="...href_fragment..." ...>SVG_CONTENT TEXT</a>
    pattern = r'(<a[^>]+href="[^"]*' + re.escape(href_fragment) + r'[^"]*"[^>]*>)((?:<svg[^>]*>.*?</svg>)?\s*)([A-Za-záéíóúÁÉÍÓÚñÑ\s]+)(\s*</a>)'
    def replacer(m):
        text = m.group(3).strip()
        return m.group(1) + m.group(2) + '<span data-i18n="' + key + '">' + text + '</span>' + m.group(4)
    new_html, n = re.subn(pattern, replacer, html, flags=re.DOTALL)
    return new_html, n

nav_links = [
    ('dashboard.html', 'nav_dashboard'),
    ('athlete_profile.html', 'nav_profile'),
    ('training_plan.html', 'nav_plan'),
    ('training_detail.html', 'nav_training'),
    ('nutrition.html', 'nav_nutrition'),
    ('blood_labs.html', 'nav_labs'),
    ('race_predictor.html', 'nav_predictor'),
    ('coach.html', 'nav_coach'),
    ('wellness.html', 'nav_wellness'),
]

for href, key in nav_links:
    new_c, n = add_i18n_to_nav_link(c, href, key)
    if n > 0:
        c = new_c
        count += n
        print(f'OK nav: {href} → {key}')

# Add data-i18n to the section title "Módulos"
c = re.sub(
    r'(<span class="sb-sect">)Módulos(</span>)',
    r'\1<span data-i18n="nav_modules">Módulos</span>\2',
    c, count=1
)

# Add data-i18n to key stat labels in the detail view
# These are generated dynamically in JS, so we need to handle via lx:langchange event
# The static ones we can add directly

with open('C:/Users/rafae/projects/LabX/training_detail.html', 'w', encoding='utf-8') as f:
    f.write(c)
print(f'\nTotal changes: {count}')
print('Saved training_detail.html')
