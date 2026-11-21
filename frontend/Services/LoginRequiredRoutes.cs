namespace CarsATTM_CustomerApp.Services;

/// <summary>
/// Etiquetas destinadas al aviso previo de autenticación en navegación interna.
/// Los permisos de las rutas siguen controlados por ProtectedRouteView y por las APIs.
/// </summary>
public static class LoginRequiredRoutes
{
    public static bool TryDescribe(string relativeUrl, out string actionText)
    {
        var path = relativeUrl.Split('?', '#')[0].Trim('/').ToLowerInvariant();
        actionText = path switch
        {
            "cart" => "consultar tu carrito",
            "orders" => "consultar o gestionar alquileres",
            "multas" => "consultar tus multas",
            "panel" => "abrir el panel de control",
            "admin" => "gestionar las solicitudes",
            "flota-admin" => "administrar la flota",
            "usuarios-admin" => "administrar los usuarios",
            _ => ""
        };
        return actionText.Length > 0;
    }
}
