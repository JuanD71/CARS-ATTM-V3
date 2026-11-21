using Microsoft.JSInterop;

namespace CarsATTM_CustomerApp.Services;

/// <summary>
/// Sesión JWT independiente por pestaña. Una pestaña duplicada empieza
/// como visitante; actualizar la misma pestaña conserva su autenticación.
/// Las APIs siguen validando la firma JWT, su vencimiento y los permisos.
/// </summary>
public sealed class BrowserAuthStore(IJSRuntime js) : IAsyncDisposable
{
    private IJSObjectReference? module;

    private async ValueTask<IJSObjectReference> GetModuleAsync()
        => module ??= await js.InvokeAsync<IJSObjectReference>("import", "/js/cars-auth-tabs.js");

    public async Task<BrowserTabStartup> InitializeAsync()
        => await (await GetModuleAsync()).InvokeAsync<BrowserTabStartup>("initializeTab");

    public async Task SaveAsync(string jwt)
        => await (await GetModuleAsync()).InvokeVoidAsync("saveToken", jwt);

    public async Task ClearAsync()
        => await (await GetModuleAsync()).InvokeVoidAsync("clearToken");

    public async ValueTask DisposeAsync()
    {
        if (module is null) return;
        var current = module;
        module = null;
        try
        {
            await current.InvokeVoidAsync("unsubscribe");
        }
        catch (JSDisconnectedException) { }
        catch (ObjectDisposedException) { }
        try
        {
            await current.DisposeAsync();
        }
        catch (JSDisconnectedException) { }
        catch (ObjectDisposedException) { }
    }
}

public sealed class BrowserTabStartup
{
    public string? Token { get; set; }
    public bool StartAtHome { get; set; }
}
