using System.Net;
using System.Net.Http.Json;
namespace CarsATTM_CustomerApp.Services;

public sealed class LoginService(HttpClient httpClient) : ILoginService
{
    private readonly string loginEndpoint = "api/auth/login";

    public async Task<string?> LoginAsync(LoginRequest request, CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(loginEndpoint, request, cancellationToken);

        if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
        {
            return null;
        }

        response.EnsureSuccessStatusCode();
        var result = await response.Content.ReadFromJsonAsync<LoginResponse>(cancellationToken);
        return string.IsNullOrWhiteSpace(result?.Token) ? null : result.Token;
    }
}

public sealed class ApiOptions
{
    public string LoginBaseUrl { get; set; } = "http://localhost:8000/";
    public string MultasBaseUrl { get; set; } = "https://localhost:5002/";
}
