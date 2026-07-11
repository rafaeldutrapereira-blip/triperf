"""
Systematic i18n coverage improvement across all LabX pages.
Each page gets a targeted pass adding data-i18n attrs to static text.
"""
import sys, re, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
base = 'C:/Users/rafae/projects/LabX/'

def fix(path, replacements):
    with open(path, encoding='utf-8') as f:
        c = f.read()
    count = 0
    for old, new in replacements:
        if old in c and new not in c:
            c = c.replace(old, new, 1)
            count += 1
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c)
    return count

total = 0

# ── LOGIN.HTML ───────────────────────────────────────────────────────────────
n = fix(base+'login.html', [
    ('>Acceso Privado<',              ' data-i18n="auth_private">Acceso Privado<'),
    ('>Ingresa tus credenciales para continuar<',
                                      ' data-i18n="auth_credentials">Ingresa tus credenciales para continuar<'),
    ('>Usuario o contraseña incorrectos.<',
                                      ' data-i18n="auth_error">Usuario o contraseña incorrectos.<'),
    ('>Recordar sesión en este dispositivo<',
                                      ' data-i18n="form_remember">Recordar sesión en este dispositivo<'),
    ('>Ingresar a LabX<',             ' data-i18n="btn_login">Ingresar a LabX<'),
    ('>¿Olvidaste tu contraseña?<',   ' data-i18n="btn_forgot">¿Olvidaste tu contraseña?<'),
    ('>¿No tienes cuenta?<',          ' data-i18n="auth_no_account">¿No tienes cuenta?<'),
    ('>Regístrate<',                  ' data-i18n="auth_register">Regístrate<'),
    ('>Privado<',                     ' data-i18n="auth_private">Privado<'),
    # Labels
    ('>Usuario<',                     ' data-i18n="form_email">Usuario<'),
    ('>Contraseña<',                  ' data-i18n="form_password">Contraseña<'),
])
print(f'login.html: +{n} attrs')
total += n

# ── REGISTRO.HTML ────────────────────────────────────────────────────────────
n = fix(base+'registro.html', [
    ('>Crea tu cuenta<',              ' data-i18n="reg_title">Crea tu cuenta<'),
    ('>Plan Básico gratuito incluido<',' data-i18n="reg_free_badge">Plan Básico gratuito incluido<'),
    ('>Empieza gratis · Sin tarjeta de crédito<',
                                      ' data-i18n="reg_no_card">Empieza gratis · Sin tarjeta de crédito<'),
    ('>Nombre completo<',             ' data-i18n="form_name">Nombre completo<'),
    ('>Email<',                       ' data-i18n="form_email">Email<'),
    ('>Contraseña<',                  ' data-i18n="form_password">Contraseña<'),
    ('>Confirmar contraseña<',        ' data-i18n="form_confirm_password">Confirmar contraseña<'),
    ('>Crear mi cuenta gratis<',      ' data-i18n="btn_register">Crear mi cuenta gratis<'),
    ('>¿Ya tienes cuenta?<',          ' data-i18n="auth_have_account">¿Ya tienes cuenta?<'),
    ('>Inicia sesión<',               ' data-i18n="auth_login">Inicia sesión<'),
])
print(f'registro.html: +{n} attrs')
total += n

# ── RESET-PASSWORD.HTML ──────────────────────────────────────────────────────
n = fix(base+'reset-password.html', [
    ('>Email de tu cuenta<',          ' data-i18n="form_email_account">Email de tu cuenta<'),
    ('>Enviar link de recuperación<', ' data-i18n="btn_send_reset">Enviar link de recuperación<'),
    ('>Nueva contraseña<',            ' data-i18n="form_new_password">Nueva contraseña<'),
    ('>Confirmar contraseña<',        ' data-i18n="form_confirm_password">Confirmar contraseña<'),
    ('>Actualizar contraseña<',       ' data-i18n="btn_update_password">Actualizar contraseña<'),
    ('>Volver al login<',             ' data-i18n="btn_back_login">Volver al login<'),
    ('>Te enviaremos un link de recuperación<',
                                      ' data-i18n="auth_credentials">Te enviaremos un link de recuperación<'),
])
print(f'reset-password.html: +{n} attrs')
total += n

# ── 404.HTML ─────────────────────────────────────────────────────────────────
t_404 = open(base+'404.html', encoding='utf-8').read()
# Show what's there
texts = re.findall(r'<(?:h[12]|p|button|a|span)[^>]*>([^<]{4,60})</(?:h[12]|p|button|a|span)>', t_404)
for tx in texts: print(f'  404: {repr(tx.strip())}')

n = fix(base+'404.html', [
    ('>Página no encontrada<',       ' data-i18n="notfound_title">Página no encontrada<'),
    ('>Ir al Dashboard<',            ' data-i18n="notfound_go_dash">Ir al Dashboard<'),
    ('>Inicio<',                     ' data-i18n="notfound_go_home">Inicio<'),
    ('>Volver atrás<',               ' data-i18n="td_back">Volver atrás<'),
])
print(f'404.html: +{n} attrs')
total += n

print(f'\nB1 total attrs added: {total}')
