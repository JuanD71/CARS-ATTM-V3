"""Regresión estática de la confirmación previa al login (sin .NET SDK).

No sustituye la compilación de Blazor ni una prueba con navegador.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "frontend"


def read(relative: str) -> str:
    return (FRONT / relative).read_text(encoding="utf-8-sig")


def test_catalog_action_shows_prompt_without_login_redirect():
    catalog = read("Components/Pages/Catalog.razor")
    assert 'LoginPrompt.Request("añadir un vehículo al carrito", "/catalog")' in catalog
    assert 'Nav.NavigateTo("/login' not in catalog
    assert "await Api.AddCartAsync(id,startDate,endDate)" in catalog


def test_vehicle_detail_action_shows_prompt_without_login_redirect():
    detail = read("Components/Pages/VehicleDetail.razor")
    assert 'LoginPrompt.Request("añadir este vehículo al carrito", $"/vehicle/{Id}")' in detail
    assert 'Nav.NavigateTo("/login' not in detail
    assert 'await Api.AddCartAsync(Id,startDate,endDate)' in detail


def test_home_private_buttons_do_not_navigate_for_visitors():
    home = read("Components/Pages/Home.razor")
    assert 'OpenProtected("/cart", "consultar tu carrito")' in home
    assert 'OpenProtected("/orders", "consultar tus alquileres")' in home
    assert 'if (!Session.IsAuthenticated)' in home
    assert 'LoginPrompt.Request(action, destination);' in home
    assert 'Nav.NavigateTo(destination);' in home
    assert '<a href="/cart">' not in home
    assert '<a href="/orders">' not in home


def test_navigation_guard_blocks_private_routes_before_prompt():
    layout = read("Components/Layout/MainLayout.razor")
    assert 'RegisterLocationChangingHandler(ConfirmProtectedNavigation)' in layout
    assert 'if (AuthSession.IsAuthenticated || !AuthSession.IsInitialized)' in layout
    assert 'context.PreventNavigation();' in layout
    assert 'LoginPrompt.Request(action, "/" + relative);' in layout
    assert 'OnCancel="LoginPrompt.Dismiss"' in layout
    assert '@key="LoginPrompt.Revision"' in layout
    assert 'navigationHandler?.Dispose();' in layout


def test_direct_private_url_stays_on_confirmation_instead_of_redirect():
    view = read("Components/ProtectedRouteView.razor")
    assert 'Inline="true"' in view
    assert 'ReturnUrl="@ProtectedReturnUrl"' in view
    assert 'OnCancel="BackToCatalog"' in view
    assert 'NavigateTo("/login' not in view
    assert 'Redirigiendo al inicio de sesión' not in view
    assert 'OnAfterRender' not in view
    assert 'AuthSession.IsAuthenticated && HasPermission()' in view


def test_navigation_to_login_only_on_user_confirmation():
    prompt = read("Components/LoginRequiredPrompt.razor")
    assert '¿Quieres iniciar sesión?' in prompt
    assert 'Seguir explorando' in prompt
    assert 'Iniciar sesión →' in prompt
    assert 'Crear cuenta' in prompt
    assert 'href="@LoginHref" data-enhance-nav="false"' in prompt
    assert 'href="/register" data-enhance-nav="false"' in prompt
    assert 'href="/catalog" data-enhance-nav="false"' in prompt
    assert 'data-login-prompt-dismiss' in prompt
    assert 'private string LoginHref => "/login?returnUrl="' in prompt
    assert 'NavigateTo("/login' not in prompt
    assert '@onclick:stopPropagation="true"' in prompt


def test_dialog_scoped_per_user_and_safe_return_path():
    service = read("Services/LoginPrompt.cs")
    policy = read("Services/LoginRequiredRoutes.cs")
    program = read("Program.cs")
    assert 'builder.Services.AddScoped<LoginPrompt>();' in program
    assert 'url.StartsWith("//", StringComparison.Ordinal)' in service
    assert "url.Contains('\\\\')" in service
    for route in ('cart', 'orders', 'multas', 'panel', 'admin', 'flota-admin', 'usuarios-admin'):
        assert f'"{route}" =>' in policy
    for route in ('catalog', 'vehicle', 'login', 'register'):
        assert f'"{route}" =>' not in policy


def test_docker_compose_still_contains_five_services_and_five_databases():
    import yaml
    services = yaml.safe_load((ROOT / 'docker-compose.yml').read_text(encoding='utf-8'))['services']
    microservices = [k for k in services if k.endswith('-service')]
    databases = [k for k in services if k.endswith('-db')]
    assert len(microservices) == len(databases) == 5
    assert 'kafka' in services and 'frontend' in services
    assert services['kafka']['image'] == 'apache/kafka:3.7.0'


def test_prompt_never_requires_a_live_blazor_circuit_for_navigation():
    app = read("Components/App.razor")
    prompt = read("Components/LoginRequiredPrompt.razor")
    js = read("wwwroot/js/cars-login-prompt-fallback.js")
    css = read("wwwroot/app.css")
    service = read("Services/LoginPrompt.cs")
    assert '/js/cars-login-prompt-fallback.js' in app
    assert 'data-login-prompt-dismiss' in prompt
    assert 'data-enhance-nav="false"' in prompt
    assert 'window.__carsLoginFallbackInstalled' in js
    assert 'data-login-prompt-hidden' in js
    assert 'data-login-prompt-hidden="true"' in css
    assert 'public long Revision' in service
    assert 'Revision++' in service
