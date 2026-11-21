"""Regresiones estáticas: la prueba real requiere un navegador y .NET."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "frontend"


def get(path):
    return (FRONT / path).read_text(encoding="utf-8-sig")


def test_tabs_restore_only_their_own_session_before_private_routes():
    auth = get("Services/AuthSession.cs")
    bootstrap = get("Components/AuthSessionBootstrapper.razor")
    guard = get("Components/ProtectedRouteView.razor")
    assert "public bool IsInitialized" in auth
    assert "Session.MarkInitialized();" in bootstrap
    assert "Store.InitializeAsync()" in bootstrap
    assert "await RestoreAsync(tab.Token)" in bootstrap
    assert "if (mustOpenHome &&" in bootstrap
    assert 'NavigationManager.NavigateTo("/", replace: true)' in bootstrap
    assert "!AuthSession.IsInitialized && !isPublicRoute" in guard
    assert "Comprobando tu sesión..." in guard
    assert "AuthSession.Changed += OnSessionChanged" in guard


def test_separate_accounts_and_duplicate_detection():
    js = get("wwwroot/js/cars-auth-tabs.js")
    browser = get("Services/BrowserAuthStore.cs")
    bootstrap = get("Components/AuthSessionBootstrapper.razor")
    login = get("Components/Pages/Login.razor")
    nav = get("Components/Layout/NavMenu.razor")
    routes = get("Components/Routes.razor")
    assert "window.sessionStorage" in js
    assert "window.BroadcastChannel" in js
    assert "findActiveCopy" in js
    assert 'message?.type === "present"' in js
    assert 'message?.type === "probe"' in js
    assert 'store().removeItem(TOKEN_KEY)' in js
    assert "return { token: readToken(), startAtHome: !previousId || cloned }" in js
    assert "localStorage.setItem(KEY" not in js
    assert "BrowserSessionChanged" not in bootstrap
    assert "public bool StartAtHome" in browser
    assert "await BrowserAuthStore.SaveAsync(token)" in login
    assert "await BrowserAuthStore.ClearAsync()" in nav
    assert "await Store.ClearAsync()" in bootstrap  # expired JWT
    assert "<AuthSessionBootstrapper />" in routes
    assert "AddScoped<BrowserAuthStore>" in get("Program.cs")
    assert '"/js/cars-auth-tabs.js"' in browser


def test_login_modal_still_never_redirects_automatically():
    guard = get("Components/ProtectedRouteView.razor")
    prompt = get("Components/LoginRequiredPrompt.razor")
    assert 'Inline="true"' in guard
    assert 'href="@LoginHref" data-enhance-nav="false"' in prompt
    assert 'private string LoginHref => "/login?returnUrl="' in prompt
    assert 'NavigateTo("/login' not in guard


def test_payment_account_and_button_have_distinct_responsive_containers():
    cart = get("Components/Pages/Cart.razor")
    css = get("wwwroot/app.css")
    assert '<div class="payment-bank-controls">' in cart
    assert '<label for="payment-account-select"' in cart
    assert '<select id="payment-account-select" class="form-select"' in cart
    assert 'class="btn btn-outline-dark payment-bank-add"' in cart
    assert "grid-template-columns:minmax(0,390px) max-content" in css
    assert "@media(max-width:680px){.payment-bank-controls{grid-template-columns:minmax(0,1fr)}" in css
    assert ".payment-contact-card h2{line-height:1.32;letter-spacing:0" in css


def test_backend_and_docker_config_unchanged():
    import yaml
    data = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = data["services"]
    assert sum(x.endswith("-service") for x in services) == 5
    assert sum(x.endswith("-db") for x in services) == 5
    assert services["kafka"]["environment"]["KAFKA_ADVERTISED_LISTENERS"] == "INTERNAL://kafka:29092"
