using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Components.Forms;

namespace CarsATTM_CustomerApp.Services;

public sealed class CarsApi(IHttpClientFactory clients, IConfiguration config, AuthSession session)
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
    { PropertyNameCaseInsensitive = true };

    private async Task<T> SendAsync<T>(string service, HttpMethod method, string path, object? payload = null)
    {
        var baseUrl = config[$"Api:{service}BaseUrl"] ?? throw new InvalidOperationException($"Falta configurar Api:{service}BaseUrl");
        using var request = new HttpRequestMessage(method, new Uri(new Uri(baseUrl), path.TrimStart('/')));
        if (session.IsAuthenticated)
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", session.Jwt);
        if (payload is not null)
            request.Content = JsonContent.Create(payload, options: Json);
        using var client = clients.CreateClient();
        using var response = await client.SendAsync(request);
        if (!response.IsSuccessStatusCode)
        {
            var detail = await response.Content.ReadAsStringAsync();
            try
            {
                using var doc = JsonDocument.Parse(detail);
                if (doc.RootElement.TryGetProperty("detail", out var d) && d.ValueKind == JsonValueKind.String)
                    detail = d.GetString() ?? detail;
            }
            catch (JsonException) { }
            throw new InvalidOperationException($"{(int)response.StatusCode}: {detail}");
        }
        if (response.StatusCode == System.Net.HttpStatusCode.NoContent)
            return default!;
        var result = await response.Content.ReadFromJsonAsync<T>(Json);
        return result ?? throw new InvalidOperationException("La API respondió sin datos");
    }

    public Task<List<Vehicle>> VehiclesAsync() => SendAsync<List<Vehicle>>("Inventario", HttpMethod.Get, "api/v1/vehiculos");
    public Task<Vehicle> VehicleAsync(int id) => SendAsync<Vehicle>("Inventario", HttpMethod.Get, $"api/v1/vehiculos/{id}");
    public Task<List<Vehicle>> AvailableVehiclesAsync(DateTime start, DateTime end) => SendAsync<List<Vehicle>>(
        "Inventario", HttpMethod.Get,
        $"api/v1/vehiculos?fechaInicio={start:yyyy-MM-dd}&fechaFin={end:yyyy-MM-dd}");
    // Gestión de flota: todos los cambios se autorizan nuevamente en Inventario.
    public Task<List<Vehicle>> AdminVehiclesAsync() => SendAsync<List<Vehicle>>(
        "Inventario", HttpMethod.Get, "api/v1/admin/vehiculos");
    public Task<List<InventoryMovement>> InventoryHistoryAsync() => SendAsync<List<InventoryMovement>>(
        "Inventario", HttpMethod.Get, "api/v1/admin/vehiculos/movimientos");
    public Task<Vehicle> CreateVehicleAsync(VehicleEditor data) => SendAsync<Vehicle>(
        "Inventario", HttpMethod.Post, "api/v1/vehiculos", data);
    public Task<Vehicle> UpdateVehicleAsync(int id, VehicleEditor data) => SendAsync<Vehicle>(
        "Inventario", HttpMethod.Put, $"api/v1/vehiculos/{id}", data);
    public Task<Vehicle> ChangeVehicleStatusAsync(int id, string status, string note) => SendAsync<Vehicle>(
        "Inventario", HttpMethod.Patch, $"api/v1/vehiculos/{id}/estado", new { estado = status, observacion = note });
    public Task<List<UserDto>> UsersAsync() => SendAsync<List<UserDto>>(
        "Login", HttpMethod.Get, "usuarios");
    public Task<object> BlockClientForOrderAsync(int id) => SendAsync<object>(
        "Ordenes", HttpMethod.Post, $"api/v1/ordenes/{id}/bloquear-cliente");
    public Task<CartDto> CartAsync() => SendAsync<CartDto>("Carrito", HttpMethod.Get, "api/v1/carrito");
    public Task<CartDto> AddCartAsync(int vehicleId, DateTime start, DateTime end) =>
        SendAsync<CartDto>("Carrito", HttpMethod.Post, "api/v1/carrito/elementos", new
        { vehiculoId = vehicleId, fechaInicio = start.ToString("yyyy-MM-dd"), fechaFin = end.ToString("yyyy-MM-dd") });
    public Task<CartDto> RemoveCartAsync(int id) => SendAsync<CartDto>("Carrito", HttpMethod.Delete, $"api/v1/carrito/elementos/{id}");
    public Task<OrderDto> CheckoutAsync(string email, string phone, string document, int accountId) =>
        SendAsync<OrderDto>("Ordenes", HttpMethod.Post, "api/v1/ordenes/checkout",
            new { correo = email, telefono = phone, documento = document, cuentaBancariaId = accountId });
    public Task<List<OrderDto>> OrdersAsync(bool all = false) => SendAsync<List<OrderDto>>("Ordenes", HttpMethod.Get, all ? "api/v1/ordenes" : "api/v1/ordenes/mis");
    public Task<List<PaymentDto>> PaymentsAsync() => SendAsync<List<PaymentDto>>("Ordenes", HttpMethod.Get, "api/v1/ordenes/solicitudes-pago");
    public Task<OrderDto> DecideOrderPaymentAsync(int id, bool approve) => SendAsync<OrderDto>("Ordenes", HttpMethod.Post,
        $"api/v1/ordenes/{id}/pago/{(approve ? "aprobar" : "rechazar")}", new { observacion = "Revisión administrativa de pago" });
    public Task<OrderDto> DeliverAsync(int id, DeliveryForm data) => SendAsync<OrderDto>("Ordenes", HttpMethod.Post, $"api/v1/ordenes/{id}/entrega", data);
    public Task<OrderDto> ReturnAsync(int id, ReturnForm data) => SendAsync<OrderDto>("Ordenes", HttpMethod.Post,
        $"api/v1/ordenes/{id}/devolucion", data);
    public Task<OrderDto> RefundDepositAsync(int id, string note) => SendAsync<OrderDto>(
        "Ordenes", HttpMethod.Post, $"api/v1/ordenes/{id}/deposito/devolucion", new { observacion = note });
    public Task<List<DamageDto>> DamageReportsAsync() => SendAsync<List<DamageDto>>("Ordenes", HttpMethod.Get, "api/v1/danos");
    public Task<object> VerifyDamageAsync(int id, bool approved, string note) => SendAsync<object>(
        "Ordenes", HttpMethod.Post, $"api/v1/danos/{id}/verificar", new { aprobado = approved, observacion = note });
    public Task<List<FineDto>> FinesAsync(bool all = false) => SendAsync<List<FineDto>>("Multas", HttpMethod.Get,
        all ? "api/v1/multas" : "api/v1/multas/mis");
    public Task<FineDto> DecideFineAsync(int id, bool approve) => SendAsync<FineDto>("Multas", HttpMethod.Post,
        $"api/v1/multas/{id}/{(approve ? "aprobar" : "rechazar")}", new { observacion = "Revisión administrativa" });
    public Task<FineDto> RequestFinePaymentAsync(int id) => SendAsync<FineDto>("Multas", HttpMethod.Post, $"api/v1/multas/{id}/solicitar-pago");
    public Task<FineDto> DecideFinePaymentAsync(int id, bool approve) => SendAsync<FineDto>("Multas", HttpMethod.Post,
        $"api/v1/multas/{id}/pago/{(approve ? "aprobar" : "rechazar")}", new { observacion = "Revisión administrativa del pago" });
    public Task<UserStatusDto> SetUserActiveAsync(long id, bool active) => SendAsync<UserStatusDto>(
        "Login", HttpMethod.Patch, $"usuarios/{id}/estado", new { activo = active });
    public Task<UserDto> CreateSellerAsync(long id, string name, string email, string password) => SendAsync<UserDto>(
        "Login", HttpMethod.Post, "usuarios/vendedores", new { id, nombre = name, email, password });
    public Task DeleteUserAsync(long id) => SendAsync<object>("Login", HttpMethod.Delete, $"usuarios/{id}");
    public Task<List<string>> BanksAsync() => SendAsync<List<string>>("Login", HttpMethod.Get, "usuarios/bancos");
    public Task<List<BankAccountDto>> BankAccountsAsync() => SendAsync<List<BankAccountDto>>(
        "Login", HttpMethod.Get, "usuarios/me/cuentas");
    public Task<BankAccountDto> AddBankAccountAsync(string bank, string number) => SendAsync<BankAccountDto>(
        "Login", HttpMethod.Post, "usuarios/me/cuentas", new { banco = bank, numeroCuenta = number });
    public Task<UserDto> RegisterAsync(long id, string name, string email, string password, string bank, string number) => SendAsync<UserDto>("Login", HttpMethod.Post,
        "usuarios", new { id, nombre = name, email, password, rol = "cliente", banco = bank, numeroCuenta = number });

    public async Task<VehicleImageDto> UploadVehicleImageAsync(IBrowserFile file)
    {
        if (!session.IsAuthenticated || session.Role != "admin")
            throw new InvalidOperationException("Solo el administrador puede cargar fotografías.");
        const long maxBytes = 5 * 1024 * 1024;
        if (file.Size > maxBytes)
            throw new InvalidOperationException("La fotografía supera los 5 MB.");
        var baseUrl = config["Api:InventarioBaseUrl"] ?? throw new InvalidOperationException("Falta Api:InventarioBaseUrl");
        using var request = new HttpRequestMessage(HttpMethod.Post,
            new Uri(new Uri(baseUrl), "api/v1/admin/vehiculos/imagen"));
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", session.Jwt);
        using var form = new MultipartFormDataContent();
        using var stream = file.OpenReadStream(maxBytes);
        using var body = new StreamContent(stream);
        body.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue(file.ContentType);
        form.Add(body, "file", file.Name);
        request.Content = form;
        using var response = await clients.CreateClient().SendAsync(request);
        if (!response.IsSuccessStatusCode)
            throw new InvalidOperationException($"Error al subir fotografía: {(int)response.StatusCode} {await response.Content.ReadAsStringAsync()}");
        return await response.Content.ReadFromJsonAsync<VehicleImageDto>(Json)
            ?? throw new InvalidOperationException("Inventario no devolvió la dirección de la imagen.");
    }
}

public sealed record Vehicle(int Id, string Placa, string Marca, string Linea, int Modelo, string Categoria,
    string Combustible, string Transmision, int Puestos, string Color, int Maletas, decimal PrecioDia,
    string Descripcion, bool Activo, string? ImagenUrl = null, string Estado = "DISPONIBLE");
public sealed record CartDto(List<CartItemDto> Items, decimal Alquiler, decimal Deposito, decimal Total, int Cantidad);
public sealed record CartItemDto(int Id, int VehiculoId, string Marca, string Linea, string FechaInicio,
    string FechaFin, int Dias, decimal PrecioDia, decimal Subtotal, string? ImagenUrl = null, decimal Deposito = 0);
public sealed record PaymentDto(int Id, int OrdenId, long UsuarioId, decimal Valor, string Modo,
    string Estado, DateTimeOffset SolicitadaEn, DateTimeOffset? RevisadaEn, long? AdministradorId, string? Observacion,
    string? CorreoContacto = null, string? TelefonoContacto = null, string? DocumentoContacto = null,
    int? CuentaBancariaId = null, string? Banco = null, string? CuentaUltimos4 = null);
public sealed record OrderLineDto(int Id, int VehiculoId, string Descripcion, string FechaInicio,
    string FechaFin, decimal PrecioDia, decimal Subtotal, string? ImagenUrl = null, decimal Deposito = 0);
public sealed record OrderDto(int Id, long UsuarioId, string Estado, decimal Total, DateTimeOffset CreadaEn,
    DateTimeOffset? EntregadaEn, DateTimeOffset? DevueltaEn, string? ObservacionDevolucion,
    bool ReportaDanos, bool Vencida, PaymentDto? SolicitudPago, List<OrderLineDto> Items, bool Incumplimiento = false,
    decimal AlquilerTotal = 0, decimal DepositoTotal = 0, bool DepositoRecibido = false,
    bool DepositoDevuelto = false, decimal ValorDepositoDevuelto = 0, string? ObservacionDeposito = null,
    List<VehicleInspectionDto>? Inspecciones = null, List<DamageDto>? ReportesDanos = null);
public sealed record FineDto(int Id, int OrdenId, long UsuarioId, string Tipo, decimal PrecioMulta,
    string Observacion, string Estado, DateTimeOffset CreadaEn, DateTimeOffset? FechaPago,
    long? AdministradorId, DateTimeOffset? DecididaEn, DateTimeOffset? PagoSolicitadoEn,
    long? PagoAdministradorId, string? ObservacionAdmin);
public sealed record UserDto(long Id, string Nombre, string Email, string Rol, bool Activo);

public sealed record UserStatusDto(long UsuarioId, bool Activo);

public sealed class VehicleEditor
{
    public string Placa {get;set;} = "";
    public string Marca {get;set;} = "";
    public string Linea {get;set;} = "";
    public int Modelo {get;set;} = DateTime.Today.Year;
    public string Categoria {get;set;} = "SUV";
    public string Combustible {get;set;} = "Gasolina";
    public string Transmision {get;set;} = "Automática";
    public int Puestos {get;set;} = 5;
    public string Color {get;set;} = "Blanco";
    public int Maletas {get;set;} = 3;
    public decimal PrecioDia {get;set;} = 180000;
    public string Descripcion {get;set;} = "";
    public string ImagenUrl {get;set;} = "/vehicles/car-01.webp";
    public static VehicleEditor From(Vehicle v) => new()
    {
        Placa = v.Placa, Marca = v.Marca, Linea = v.Linea, Modelo = v.Modelo,
        Categoria = v.Categoria, Combustible = v.Combustible, Transmision = v.Transmision,
        Puestos = v.Puestos, Color = v.Color, Maletas = v.Maletas, PrecioDia = v.PrecioDia,
        Descripcion = v.Descripcion, ImagenUrl = v.ImagenUrl ?? "/vehicles/car-01.webp"
    };
}

public sealed record InventoryMovement(int Id, int VehiculoId, long AdministradorId,
    string Accion, string? EstadoAnterior, string EstadoNuevo, string Observacion, DateTimeOffset RegistradoEn);

public sealed record BankAccountDto(int Id, string Banco, string Ultimos4, bool Principal);
public sealed record VehicleImageDto(string ImagenUrl);
public sealed record VehicleInspectionDto(int Id, int VehiculoId, string Tipo, int Kilometraje,
    string NivelCombustible, string Carroceria, string Interior, string Llantas, string Luces,
    string Observaciones, long ResponsableId, DateTimeOffset RegistradoEn);
public sealed record DamageDto(int Id, int OrdenId, int VehiculoId, string Tipo,
    string Severidad, string Descripcion, decimal CostoEstimado, string Estado,
    long RegistradoPor = 0, string? ObservacionAdmin = null);

public sealed class VehicleInspectionForm
{
    public int VehiculoId { get; set; }
    public int Kilometraje { get; set; }
    public string NivelCombustible { get; set; } = "LLENO";
    public string Carroceria { get; set; } = "BUENO";
    public string Interior { get; set; } = "BUENO";
    public string Llantas { get; set; } = "BUENO";
    public string Luces { get; set; } = "BUENO";
    public string Observaciones { get; set; } = "";
    // Sólo se utiliza en la UI de devolución, no en la solicitud de peritaje.
    public bool ReportarDano { get; set; }
    public string TipoDano { get; set; } = "CARROCERIA";
    public string SeveridadDano { get; set; } = "LEVE";
    public string DescripcionDano { get; set; } = "";
    public decimal CostoDano { get; set; }
}
public sealed class DamageForm
{
    public int VehiculoId { get; set; }
    public string Tipo { get; set; } = "CARROCERIA";
    public string Severidad { get; set; } = "LEVE";
    public string Descripcion { get; set; } = "";
    public decimal CostoEstimado { get; set; }
}
public sealed class DeliveryForm
{
    public bool DepositoRecibido { get; set; }
    public List<VehicleInspectionForm> Inspecciones { get; set; } = [];
    public string ObservacionDeposito { get; set; } = "";
}
public sealed class ReturnForm
{
    public bool DepositoDevuelto { get; set; }
    public decimal ValorDepositoDevuelto { get; set; }
    public string ObservacionDeposito { get; set; } = "";
    public List<VehicleInspectionForm> Inspecciones { get; set; } = [];
    public List<DamageForm> Danos { get; set; } = [];
    public string Observacion { get; set; } = "";
}
