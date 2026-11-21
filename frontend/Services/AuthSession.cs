namespace CarsATTM_CustomerApp.Services;

public sealed class AuthSession
{
    public string? Jwt { get; private set; }
    public long? Sub { get; private set; }
    public string? Name { get; private set; }
    public string Role { get; private set; } = "cliente";

    public event Action? Changed;

    // Se activa después de consultar el token de ESTA pestaña; evita mostrar
    // avisos de visitante durante la recuperación de la sesión.
    public bool IsInitialized { get; private set; }

    public void MarkInitialized()
    {
        if (IsInitialized) return;
        IsInitialized = true;
        Changed?.Invoke();
    }

    public bool IsAuthenticated => !string.IsNullOrWhiteSpace(Jwt) &&
        ExpiresAt.HasValue && ExpiresAt.Value > DateTimeOffset.UtcNow;

    public DateTimeOffset? ExpiresAt { get; private set; }

    public void SignIn(string jwt)
    {
        if (string.IsNullOrWhiteSpace(jwt))
        {
            throw new ArgumentException("El JWT no puede estar vacío.", nameof(jwt));
        }

        try
        {
            var payload = jwt.Split('.')[1];
            var payloadJson = Convert.FromBase64String(
                payload.Replace('-', '+').Replace('_', '/') + new string('=', (4 - payload.Length % 4) % 4));
            using var document = System.Text.Json.JsonDocument.Parse(payloadJson);
            var root = document.RootElement;

            // PyJWT codifica "sub" como texto, conforme al estándar JWT.
            var sub = root.GetProperty("sub");
            var subValue = sub.ValueKind == System.Text.Json.JsonValueKind.String
                ? sub.GetString()
                : sub.GetRawText();
            if (!long.TryParse(subValue, out var userId))
                throw new FormatException("La cédula del token no es válida.");

            var expires = root.GetProperty("exp").GetInt64();
            if (DateTimeOffset.FromUnixTimeSeconds(expires) <= DateTimeOffset.UtcNow)
                throw new FormatException("La sesión ha vencido.");

            Sub = userId;
            Name = root.GetProperty("name").GetString();
            Role = root.TryGetProperty("role", out var role) ? role.GetString() ?? "cliente" : "cliente";
            Jwt = jwt;
            ExpiresAt = DateTimeOffset.FromUnixTimeSeconds(expires);
        }
        catch (Exception exception) when (exception is IndexOutOfRangeException or FormatException or System.Text.Json.JsonException or KeyNotFoundException or InvalidOperationException)
        {
            throw new ArgumentException("El JWT no contiene claims válidos.", nameof(jwt), exception);
        }

        Changed?.Invoke();
    }

    public void SignOut()
    {
        Jwt = null;
        ExpiresAt = null;
        Sub = null;
        Name = null;
        Role = "cliente";
        Changed?.Invoke();
    }
}
