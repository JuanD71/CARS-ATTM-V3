namespace CarsATTM_CustomerApp.Services;

/// <summary>
/// Solicita consentimiento antes de abandonar la pantalla pública para iniciar sesión.
/// Es un estado de interfaz por circuito Blazor, no un cambio de autenticación del backend.
/// </summary>
public sealed class LoginPrompt
{
    public bool IsOpen { get; private set; }
    // Reemplaza el nodo del aviso en cada apertura. Evita que el cierre nativo de
    // emergencia mantenga oculto un diálogo posterior.
    public long Revision { get; private set; }
    public string ActionText { get; private set; } = "continuar con esta acción";
    public string ReturnUrl { get; private set; } = "/";
    public event Action? Changed;

    public void Request(string actionText, string returnUrl)
    {
        ActionText = string.IsNullOrWhiteSpace(actionText) ? "continuar con esta acción" : actionText;
        ReturnUrl = IsSafeReturnUrl(returnUrl) ? returnUrl : "/";
        IsOpen = true;
        Revision++;
        Changed?.Invoke();
    }

    public void Dismiss()
    {
        IsOpen = false;
        Changed?.Invoke();
    }

    private static bool IsSafeReturnUrl(string url) =>
        !string.IsNullOrWhiteSpace(url) && url.StartsWith('/') &&
        !url.StartsWith("//", StringComparison.Ordinal) && !url.Contains('\\');
}
