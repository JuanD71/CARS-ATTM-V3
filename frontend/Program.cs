using CarsATTM_CustomerApp.Components;
using CarsATTM_CustomerApp.Services;
using Microsoft.AspNetCore.HttpOverrides;

var builder = WebApplication.CreateBuilder(args);

// La web se publica detrás de Cloudflare Tunnel. El túnel termina TLS y
// reenvía al contenedor por HTTP; procesamos X-Forwarded-Proto antes de
// HSTS/HTTPS redirection para evitar bucles de redirección.
builder.Services.Configure<ForwardedHeadersOptions>(options =>
{
    options.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto;

    // El puerto del frontend se publica únicamente en 127.0.0.1 del host.
    // En este despliegue el proxy local cloudflared es el único punto de entrada.
    options.KnownNetworks.Clear();
    options.KnownProxies.Clear();
});

builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents();

builder.Services.Configure<ApiOptions>(builder.Configuration.GetSection("Api"));
builder.Services.AddScoped<AuthSession>();
builder.Services.AddScoped<BrowserAuthStore>();
builder.Services.AddScoped<LoginPrompt>();
builder.Services.AddHttpClient();
builder.Services.AddScoped<CarsApi>();
builder.Services.AddScoped<VehicleConversationService>();
builder.Services.AddHttpClient<ILoginService, LoginService>((serviceProvider, client) =>
{
    var options = serviceProvider.GetRequiredService<Microsoft.Extensions.Options.IOptions<ApiOptions>>().Value;
    client.BaseAddress = new Uri(options.LoginBaseUrl);
});

var app = builder.Build();

// Debe ejecutarse antes de redirecciones, HSTS y componentes que lean el esquema.
app.UseForwardedHeaders();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
    app.UseHsts();
}

app.UseStatusCodePagesWithReExecute("/not-found", createScopeForStatusCodePages: true);
app.UseHttpsRedirection();
app.UseAntiforgery();

app.MapGet("/health", () => Results.Ok(new { status = "ok" }));
// Las fotografías personalizadas se guardan en un volumen de Inventario y
// se sirven a través del frontend, sin exponer el microservicio a Internet.
app.MapGet("/uploads/vehicles/{name}", async (string name, IHttpClientFactory clients, IConfiguration config) =>
{
    if (!System.Text.RegularExpressions.Regex.IsMatch(name, @"^[0-9a-f]{32}\.webp$"))
        return Results.NotFound();
    var url = (config["Api:InventarioBaseUrl"] ?? "http://inventario-service:8000/").TrimEnd('/');
    using var client = clients.CreateClient();
    using var response = await client.GetAsync($"{url}/uploads/vehicles/{name}");
    if (!response.IsSuccessStatusCode) return Results.NotFound();
    var bytes = await response.Content.ReadAsByteArrayAsync();
    return Results.File(bytes, "image/webp");
});
app.MapStaticAssets();
app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

app.Run();
