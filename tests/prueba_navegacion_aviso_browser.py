"""Prueba de clics del aviso sin circuito Blazor: Chromium + Playwright.

Ejecutar: python tests/prueba_navegacion_aviso_browser.py
Nota: comprueba navegación HTML, cierre JavaScript y diseño del aviso; no
sustituye una prueba real de la aplicación .NET conectada a Docker.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / 'frontend'
source = (FRONT / 'Components/LoginRequiredPrompt.razor').read_text(encoding='utf-8')
js = (FRONT / 'wwwroot/js/cars-login-prompt-fallback.js').read_text(encoding='utf-8')
css = (FRONT / 'wwwroot/app.css').read_text(encoding='utf-8')
# Evitar la importación de Google Fonts: el navegador de pruebas no tiene red.
css = '\n'.join(line for line in css.splitlines() if not line.startswith('@import '))

# El accesorio de prueba usa los mismos enlaces/clases/atributos que el Razor.
for expected in ('href="@LoginHref" data-enhance-nav="false"',
                 'href="/register" data-enhance-nav="false"',
                 'href="/catalog" data-enhance-nav="false"',
                 'data-login-prompt-dismiss',
                 'private string LoginHref'):
    assert expected in source, f'El aviso no cumple la ruta verificable: {expected}'


def fixture(inline):
    close = '<a class="login-required-close" href="/catalog" data-enhance-nav="false">×</a>' if inline else \
        '<button class="login-required-close" data-login-prompt-dismiss>×</button>'
    cancel = '<a href="/catalog" data-enhance-nav="false" class="btn btn-outline-dark">Seguir explorando</a>' if inline else \
        '<button class="btn btn-outline-dark" data-login-prompt-dismiss>Seguir explorando</button>'
    wrap = 'login-required-route' if inline else 'login-required-backdrop'
    return f'''<!DOCTYPE html><html><head><style>{css}</style></head><body>
    <div class="{wrap}" data-login-prompt role="presentation">
        <section class="login-required-dialog" role="dialog">
            {close}
            <h2>¿Quieres iniciar sesión?</h2>
            <p>Para continuar necesitas iniciar sesión.</p>
            <div class="login-required-actions">
                {cancel}
                <a href="/login?returnUrl=%2Forders" data-enhance-nav="false" class="btn btn-primary">Iniciar sesión →</a>
            </div>
            <p class="login-required-register"><a href="/register" data-enhance-nav="false"
                class="login-required-register-button">Crear cuenta</a></p>
        </section>
    </div></body></html>'''

with sync_playwright() as play:
    browser = play.chromium.launch(headless=True, executable_path='/usr/bin/chromium',
                                   args=['--no-sandbox', '--disable-dev-shm-usage'])
    for width in (1300, 390):
        page = browser.new_page(viewport={'width': width, 'height': 800})
        for inline in (True, False):
            # Cada apertura simula un aviso recién montado: es lo que garantiza @key.
            page.set_content(fixture(inline), wait_until='domcontentloaded')
            page.evaluate('delete window.__carsLoginFallbackInstalled')
            page.add_script_tag(content=js)
            page.evaluate('''() => {
                window.__lastLink = null;
                document.addEventListener('click', event => {
                    const link = event.target.closest('a[data-enhance-nav="false"]');
                    if (link) { window.__lastLink = link.getAttribute('href'); event.preventDefault(); }
                }, {capture:true});
            }''')
            for label, expected in [('Iniciar sesión', '/login?returnUrl=%2Forders'),
                                    ('Crear cuenta', '/register')]:
                page.locator('a.btn-primary' if label == 'Iniciar sesión' else 'a.login-required-register-button').click(timeout=5000)
                assert page.evaluate('window.__lastLink') == expected, (width, inline, label)
            page.get_by_text('Seguir explorando').click(timeout=5000)
            if inline:
                assert page.evaluate('window.__lastLink') == '/catalog'
                assert page.locator('div[data-login-prompt]').is_visible()
            else:
                assert page.locator('div[data-login-prompt]').get_attribute('data-login-prompt-hidden') == 'true'
                assert not page.locator('div[data-login-prompt]').is_visible()
            # Comprobar también la X en un aviso nuevo (sin estado del anterior).
            page.set_content(fixture(inline), wait_until='domcontentloaded')
            page.evaluate('delete window.__carsLoginFallbackInstalled')
            page.add_script_tag(content=js)
            page.evaluate('''() => document.addEventListener('click', e => {
                if (e.target.closest('a[data-enhance-nav="false"]')) e.preventDefault();
            }, {capture:true})''')
            page.evaluate('delete window.__carsLoginFallbackInstalled')
            page.add_script_tag(content=js)
            page.locator('.login-required-close').click(timeout=5000)
            if not inline:
                assert not page.locator('div[data-login-prompt]').is_visible()
        print(f'OK: botones Inicio sesión, Crear cuenta, Seguir explorando y X: {width}px')
        page.close()
    browser.close()
print('OK: avisos inline/overlay y diseño escritorio/móvil, sin Blazor conectado.')
