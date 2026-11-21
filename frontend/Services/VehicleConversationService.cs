using System.Globalization;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace CarsATTM_CustomerApp.Services;

// Estado privado del componente Blazor. No se almacena en la BD ni se comparte entre visitantes.
public sealed class VehicleConversationState
{
    public int? Pasajeros { get; set; }
    public int? Maletas { get; set; }
    public decimal? PresupuestoDia { get; set; }
    public string? Transmision { get; set; }
    public string? Combustible { get; set; }
    public string? Categoria { get; set; }
    public string? Uso { get; set; }
    public bool Economico { get; set; }
    public DateTime? FechaInicio { get; set; }
    public DateTime? FechaFin { get; set; }
    public int? DuracionDias { get; set; }
    public List<int> UltimosVehiculos { get; } = [];
    public int? VehiculoElegido { get; set; }

    public void Clear()
    {
        Pasajeros = null; Maletas = null; PresupuestoDia = null;
        Transmision = null; Combustible = null; Categoria = null;
        Uso = null; Economico = false;
        FechaInicio = null; FechaFin = null; DuracionDias = null;
        UltimosVehiculos.Clear(); VehiculoElegido = null;
    }
}

public sealed record VehicleChatSuggestion(Vehicle Vehiculo, string Motivo);
public sealed record VehicleChatReply(
    string Mensaje, List<VehicleChatSuggestion> Vehiculos, bool FechasVerificadas,
    bool MostrarAvisoFechas = false);

/// <summary>
/// Qwen3 identifica la intencion y las preferencias; todas las recomendaciones,
/// cifras, comparaciones y validaciones de fechas se resuelven en C# con Inventario.
/// No se crean reservas ni se modifican datos a traves del chat.
/// </summary>
public sealed class VehicleConversationService(
    CarsApi api, IHttpClientFactory clients, IConfiguration configuration)
{
    private static readonly CultureInfo Colombia = new("es-CO");
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true
    };

    private sealed class Interpretation
    {
        public string? Intencion { get; set; }
        public int? Pasajeros { get; set; }
        public int? Maletas { get; set; }
        public decimal? PresupuestoDia { get; set; }
        public string? Transmision { get; set; }
        public string? Combustible { get; set; }
        public string? Categoria { get; set; }
        public string? Uso { get; set; }
        public bool? Economico { get; set; }
        public string? FechaInicio { get; set; }
        public string? FechaFin { get; set; }
        public int? DuracionDias { get; set; }
        public string? Criterio { get; set; }
        public string? Referencia { get; set; }
        public int? NumeroOpcion { get; set; }
        public bool? QuitarPresupuesto { get; set; }
        public bool? QuitarFechas { get; set; }
        public bool? QuitarTransmision { get; set; }
        public bool? QuitarCombustible { get; set; }
        public bool? QuitarCategoria { get; set; }
    }

    public async Task<VehicleChatReply> RespondAsync(
        string message, VehicleConversationState state,
        DateTime? formStart = null, DateTime? formEnd = null)
    {
        message = (message ?? "").Trim();
        if (message.Length is < 2 or > 1200)
            throw new InvalidOperationException("Escribe un mensaje de entre 2 y 1.200 caracteres.");

        var intent = await InterpretAsync(message, state);
        var action = Normalize(intent.Intencion ?? "buscar");
        // Refuerzo determinista para las preguntas conversacionales frecuentes.
        // Un modelo pequeño puede clasificarlas como una busqueda nueva.
        var question = Normalize(message);
        // Detecta duraciones escritas con cifras incluso si Qwen omite el dato.
        var durationMatch = Regex.Match(question, @"\b(?<dias>\d{1,3})\s*dias?\b");
        if (durationMatch.Success && int.TryParse(durationMatch.Groups["dias"].Value, out var duration)
            && duration is >= 1 and <= 365)
            intent.DuracionDias = duration;
        if (state.UltimosVehiculos.Count > 0)
        {
            if (Regex.IsMatch(question, @"\b(segundo|segunda|tercero|tercera|primero|primera)\b") &&
                !question.Contains("buscar") && !question.Contains("recomienda"))
            {
                action = "detalle";
                intent.NumeroOpcion = Regex.IsMatch(question, @"\b(segundo|segunda)\b") ? 2 :
                    Regex.IsMatch(question, @"\b(tercero|tercera)\b") ? 3 : 1;
            }
            var asksComparison = question.Contains("cual") || question.Contains("que opcion") ||
                                 question.Contains("de esos") || question.Contains("de esas");
            if (asksComparison && (question.Contains("barat") || question.Contains("econom") || question.Contains("precio")))
            {
                action = "comparar";
                intent.Criterio = "precio";
            }
            else if (asksComparison && (question.Contains("maleta") || question.Contains("equipaje") || question.Contains("espacio")))
            {
                action = "comparar";
                intent.Criterio = "maletas";
            }
            else if (asksComparison && (question.Contains("puesto") || question.Contains("pasajero")))
            {
                action = "comparar";
                intent.Criterio = "puestos";
            }
            else if (asksComparison && (question.Contains("deposito") || question.Contains("garantia")))
            {
                action = "comparar";
                intent.Criterio = "deposito";
            }
            else if (question.Contains("cuanto cuesta") || question.Contains("costo total") || question.Contains("por cuantos dias"))
                action = "costo";
            else if (IsPersonalizedComparison(question))
            {
                // "De esos 3, cual es mejor para mi" no es una nueva busqueda.
                // Qwen3 1.7B a veces lo clasifica como "buscar"; aqui prevalece
                // la referencia explicita a las opciones previas.
                action = "comparar";
                intent.Criterio = "general";
                // No sobreescribir las preferencias previas con campos inferidos
                // erróneamente por el modelo al hacer una pregunta de seguimiento.
                if (!Regex.IsMatch(question, @"\b(somos|viajamos|personas?|pasajeros?|puestos?)\b"))
                    intent.Pasajeros = null;
                if (!Regex.IsMatch(question, @"\b(maletas?|equipaje)\b"))
                    intent.Maletas = null;
                if (!Regex.IsMatch(question, @"\b(presupuesto|diarios?|dia|limite)\b|\$\s*\d"))
                    intent.PresupuestoDia = null;
                if (!Regex.IsMatch(question, @"\b(barat[oa]s?|econom[ia]c[oa]s?|ahorrar|ahorro)\b"))
                    intent.Economico = null;
                if (!Regex.IsMatch(question, @"\b(automatic[ao]s?|manual(?:es)?)\b"))
                    intent.Transmision = null;
                if (!Regex.IsMatch(question, @"\b(gasolina|diesel|hibrid[oa]|electric[oa])\b"))
                    intent.Combustible = null;
                if (!Regex.IsMatch(question, @"\b(suv|sedan|compacto|pickup|premium|van)\b"))
                    intent.Categoria = null;
                intent.Uso = null;
            }
        }
        if (action is "reiniciar" or "reset")
        {
            state.Clear();
            return Reply("Empecemos de nuevo. ¿Cuántas personas viajan, cuánto equipaje llevan y cuál es tu presupuesto diario?");
        }
        if (action is "saludo" or "saludar")
            return Reply("¡Hola! Soy el asistente de CARS ATTM. Puedo ayudarte a buscar, comparar y calcular el alquiler de nuestros vehículos. ¿Qué necesitas?");

        MergePreferences(intent, state);
        // Una instrucción explícita para quitar fechas anula el selector del formulario.
        if (intent.QuitarFechas == true) { formStart = null; formEnd = null; }
        if (formStart.HasValue != formEnd.HasValue)
            return Reply("Para verificar disponibilidad necesito las fechas de retiro y devolución.");
        if (formStart.HasValue)
        {
            state.FechaInicio = formStart.Value.Date;
            state.FechaFin = formEnd!.Value.Date;
        }

        bool mentionedStart = !string.IsNullOrWhiteSpace(intent.FechaInicio);
        bool mentionedEnd = !string.IsNullOrWhiteSpace(intent.FechaFin);
        if (mentionedStart || mentionedEnd)
        {
            if (!TryDate(intent.FechaInicio, out var start) && mentionedStart)
                return Reply("No pude interpretar la fecha de retiro. Indícala como día/mes/año.");
            if (!TryDate(intent.FechaFin, out var end) && mentionedEnd)
                return Reply("No pude interpretar la fecha de devolución. Indícala como día/mes/año.");
            // Evita emparejar una nueva fecha suelta con una fecha antigua de otro viaje.
            if (mentionedStart != mentionedEnd)
            {
                if (mentionedStart) { state.FechaInicio = start; state.FechaFin = null; }
                else state.FechaFin = end;
            }
            else
            {
                state.FechaInicio = start;
                state.FechaFin = end;
            }
        }

        if (state.FechaInicio.HasValue != state.FechaFin.HasValue)
            return Reply("¿Cuál es la otra fecha del alquiler? Necesito el retiro y la devolución para consultar Inventario.");
        if (state.FechaInicio.HasValue)
        {
            var today = BogotaToday();
            if (state.FechaInicio.Value.Date < today || state.FechaFin!.Value.Date <= state.FechaInicio.Value.Date)
                return Reply("Las fechas no son válidas. Selecciona un retiro desde hoy y una devolución posterior al retiro.");
            state.DuracionDias = (state.FechaFin.Value.Date - state.FechaInicio.Value.Date).Days;
        }

        var hasDates = state.FechaInicio.HasValue && state.FechaFin.HasValue;
        if (action is "disponibilidad" && !hasDates)
            return Reply("Puedo revisar la disponibilidad real, pero primero dime las fechas de retiro y devolución.");

        // Consultas sin escritura: una copia nueva en cada turno evita mostrar precios antiguos.
        var all = await api.VehiclesAsync();
        var fleet = all.Where(IsEligibleStatus).ToList();
        List<Vehicle> available = hasDates
            ? (await api.AvailableVehiclesAsync(state.FechaInicio!.Value, state.FechaFin!.Value))
                .Where(IsEligibleStatus).ToList()
            : fleet;
        var availableIds = available.Select(v => v.Id).ToHashSet();

        // La pregunta de comparacion se refiere exclusivamente a la ultima lista mostrada.
        if (action is "comparar" or "detalle" or "costo" or "calcular")
        {
            var previous = state.UltimosVehiculos
                .Select(id => fleet.FirstOrDefault(v => v.Id == id))
                .Where(v => v is not null)
                .Cast<Vehicle>().ToList();
            var chosen = IdentifySelectedVehicle(intent, message, previous, state);
            if (chosen is not null) state.VehiculoElegido = chosen.Id;

            if (previous.Count == 0 && chosen is null)
                return Reply("Primero cuéntame qué necesitas y te mostraré algunas opciones del catálogo para poder compararlas.");

            if (action is "costo" or "calcular")
                return ExplainCost(previous, chosen, state, hasDates);
            if (action == "detalle")
                return ExplainDetail(chosen ?? previous.First(), hasDates, availableIds);
            return ExplainComparison(previous, chosen, intent.Criterio, state, hasDates, availableIds);
        }

        // Si solo pregunta por la disponibilidad de uno de los anteriores, respetamos la referencia.
        if (action is "disponibilidad" && state.UltimosVehiculos.Count > 0)
        {
            var previous = state.UltimosVehiculos
                .Select(id => fleet.FirstOrDefault(v => v.Id == id))
                .Where(v => v is not null).Cast<Vehicle>().ToList();
            var target = IdentifySelectedVehicle(intent, message, previous, state);
            if (target is not null)
            {
                var ok = availableIds.Contains(target.Id);
                return ok
                    ? new VehicleChatReply($"Sí, {target.Marca} {target.Linea} figura disponible del {state.FechaInicio:dd/MM/yyyy} al {state.FechaFin:dd/MM/yyyy}. Se verificará nuevamente al reservar.",
                        [new(target, Reason(target))], true)
                    : Reply($"{target.Marca} {target.Linea} no está disponible para esas fechas. Puedo buscar otras alternativas.");
            }
        }

        // Una pregunta abierta de seguimiento sin nuevas preferencias no debe olvidar el contexto.
        var matched = available.Where(v =>
            (!state.Pasajeros.HasValue || v.Puestos >= state.Pasajeros.Value) &&
            (!state.Maletas.HasValue || v.Maletas >= state.Maletas.Value) &&
            (!state.PresupuestoDia.HasValue || v.PrecioDia <= state.PresupuestoDia.Value) &&
            Matches(v.Transmision, state.Transmision) &&
            Matches(v.Combustible, state.Combustible) &&
            Matches(v.Categoria, state.Categoria));

        var candidates = (state.Economico
                ? matched.OrderBy(v => v.PrecioDia).ThenByDescending(v => v.Modelo)
                : matched.OrderByDescending(v => Suitability(v, state)).ThenBy(v => v.PrecioDia))
            .Take(3).ToList();

        state.UltimosVehiculos.Clear();
        state.UltimosVehiculos.AddRange(candidates.Select(v => v.Id));
        state.VehiculoElegido = null;

        if (candidates.Count == 0)
        {
            var onDates = hasDates ? " para las fechas seleccionadas" : "";
            return Reply($"No encontré vehículos{onDates} que cumplan todas tus condiciones. Puedes ampliar el presupuesto o flexibilizar alguna preferencia.");
        }

        var cheapest = candidates.OrderBy(v => v.PrecioDia).First();
        var top = candidates.First();
        var text = candidates.Count == 1
            ? $"Encontré una opción que cumple tus preferencias: {top.Marca} {top.Linea}, desde {Price(top.PrecioDia)} al día."
            : $"Encontré {candidates.Count} opciones que se ajustan a lo que buscas. " +
              $"{cheapest.Marca} {cheapest.Linea} es la más económica de esta selección, a {Price(cheapest.PrecioDia)} diarios.";
        if (hasDates)
            text += $" Consulté Inventario del {state.FechaInicio:dd/MM/yyyy} al {state.FechaFin:dd/MM/yyyy}.";
        text += " ¿Quieres comparar el espacio, el precio total o alguna de estas opciones?";

        return new VehicleChatReply(text,
            candidates.Select(v => new VehicleChatSuggestion(v, Reason(v))).ToList(),
            hasDates, !hasDates);
    }

    private async Task<Interpretation> InterpretAsync(string question, VehicleConversationState state)
    {
        var endpoint = configuration["Ollama:BaseUrl"] ?? "http://localhost:11434/";
        var model = configuration["Ollama:Model"] ?? "qwen3:1.7b";
        var date = BogotaToday().ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        var known = $"Estado previo: pasajeros={state.Pasajeros?.ToString() ?? "?"}, " +
            $"maletas={state.Maletas?.ToString() ?? "?"}, presupuestoDia={state.PresupuestoDia?.ToString(CultureInfo.InvariantCulture) ?? "?"}, " +
            $"transmision={state.Transmision ?? "?"}, combustible={state.Combustible ?? "?"}, categoria={state.Categoria ?? "?"}, " +
            $"fechas={state.FechaInicio:yyyy-MM-dd}/{state.FechaFin:yyyy-MM-dd}, dias={state.DuracionDias?.ToString() ?? "?"}. " +
            $"Ultimas opciones: {string.Join(",", state.UltimosVehiculos)}.";
        var instructions = $$"""
            Eres un analizador de intenciones para un chat de alquiler de vehículos en Colombia.
            Fecha de hoy: {{date}}. Responde SOLO JSON sin markdown ni explicación.
            Esquema con todas las claves:
            {"intencion":"buscar","pasajeros":null,"maletas":null,"presupuestoDia":null,"transmision":null,"combustible":null,"categoria":null,"uso":null,"economico":null,"fechaInicio":null,"fechaFin":null,"duracionDias":null,"criterio":null,"referencia":null,"numeroOpcion":null,"quitarPresupuesto":false,"quitarFechas":false,"quitarTransmision":false,"quitarCombustible":false,"quitarCategoria":false}
            intencion: "buscar" cuando pide nuevas recomendaciones o cambia filtros; "comparar" para preguntas sobre las opciones anteriores,
            "detalle" para una opción individual, "costo" si pide precio total, dias de alquiler o deposito,
            "disponibilidad" para disponibilidad en fechas, "saludo" para saludos sin solicitud, "reiniciar" si pide borrar contexto.
            criterio: "precio", "maletas", "puestos", "deposito", "transmision", "combustible", "general".
            referencia: nombre o marca exacta que el usuario menciona (p.ej., "Yaris"), o null.
            numeroOpcion: 1,2,3 si dice "el primero", "segundo", "tercero", etc. Si no, null.
            Solo extrae restricciones NUEVAS presentes en el mensaje, no copies las anteriores del estado.
            Transmision: "Automática" o "Manual"; combustible: "Gasolina", "Diésel", "Híbrido", "Eléctrico";
            categoria: "Compacto", "Sedán", "SUV", "Pickup", "Premium", "Eléctrico", "Van".
            COP: "$180.000 diarios" = 180000 (no confundir alquiler diario con deposito ni total).
            fechaInicio y fechaFin en YYYY-MM-DD solo si se pueden identificar de forma fiable.
            La fecha de devolución debe ser la siguiente fecha cuando dice "del 25 al 28".
            duracionDias se usa si menciona cantidad de dias (p.ej., "por 4 dias" => 4).
            Si dice "sin limite de presupuesto", quitarPresupuesto=true; "sin importar la transmision", quitarTransmision=true;
            "sin fechas", quitarFechas=true.
            economico=true si pide el mas barato, economico o ahorrar; false si dice que ya no prioriza precio; null en otros casos.
            No inventes datos, no agregues texto fuera del objeto JSON.
            """;
        var payload = new
        {
            model,
            stream = false,
            think = false,
            format = "json",
            options = new { temperature = 0, num_predict = 380 },
            messages = new[]
            {
                new { role = "system", content = instructions },
                new { role = "user", content = known + "\nMensaje actual: " + question }
            }
        };
        try
        {
            using var client = clients.CreateClient();
            client.Timeout = TimeSpan.FromSeconds(150);
            using var response = await client.PostAsJsonAsync(
                new Uri(new Uri(endpoint.TrimEnd('/') + "/"), "api/chat"), payload);
            response.EnsureSuccessStatusCode();
            using var envelope = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync());
            var content = envelope.RootElement.GetProperty("message").GetProperty("content").GetString();
            var parsed = JsonSerializer.Deserialize<Interpretation>(content ?? "", Json);
            return parsed ?? throw new JsonException("El objeto de intenciones está vacío.");
        }
        catch (HttpRequestException ex)
        {
            throw new InvalidOperationException("No fue posible conectar con Ollama. Comprueba que está abierto en Windows.", ex);
        }
        catch (TaskCanceledException ex)
        {
            throw new InvalidOperationException("Ollama tardó demasiado en responder. Intenta de nuevo.", ex);
        }
        catch (JsonException ex)
        {
            throw new InvalidOperationException("Qwen3 no pudo interpretar la solicitud. Escríbela con otras palabras.", ex);
        }
    }

    private static void MergePreferences(Interpretation input, VehicleConversationState state)
    {
        if (input.Pasajeros is >= 1 and <= 20) state.Pasajeros = input.Pasajeros;
        if (input.Maletas is >= 0 and <= 30) state.Maletas = input.Maletas;
        if (input.QuitarPresupuesto == true) state.PresupuestoDia = null;
        else if (input.PresupuestoDia is > 0 and <= 100000000) state.PresupuestoDia = input.PresupuestoDia;
        if (input.QuitarTransmision == true) state.Transmision = null;
        else if (IsAllowed(input.Transmision, "automatica", "manual")) state.Transmision = input.Transmision;
        if (input.QuitarCombustible == true) state.Combustible = null;
        else if (IsAllowed(input.Combustible, "gasolina", "diesel", "hibrido", "electrico")) state.Combustible = input.Combustible;
        if (input.QuitarCategoria == true) state.Categoria = null;
        else if (IsAllowed(input.Categoria, "compacto", "sedan", "suv", "pickup", "premium", "electrico", "van"))
            state.Categoria = input.Categoria;
        if (!string.IsNullOrWhiteSpace(input.Uso) && input.Uso.Length < 40) state.Uso = input.Uso;
        if (input.Economico.HasValue) state.Economico = input.Economico.Value;
        if (input.QuitarFechas == true)
        {
            state.FechaInicio = null; state.FechaFin = null;
            state.DuracionDias = null;
        }
        if (input.DuracionDias is >= 1 and <= 365) state.DuracionDias = input.DuracionDias;
    }

    private static bool IsPersonalizedComparison(string question)
    {
        // El texto ya se normalizo: minusculas y sin tildes.
        var asksWhich = Regex.IsMatch(question, @"\b(cual|que|entre|de esos|de esas|de estos|de estas)\b");
        var requestsAdvice = Regex.IsMatch(question,
            @"\b(mejor|conviene|convendria|recomiendas|recomienda|recomendarias|elegir|elegirias|escoger|escogerias|ideal|adecuado|adecuada|sirve|sirven|preferible)\b");
        var refersToEarlier = Regex.IsMatch(question,
            @"\b(esos|esas|estos|estas|anteriores|opciones|de los (3|tres)|de las (3|tres)|entre los (3|tres)|entre las (3|tres))\b");
        // "Cual es mejor para mi" tambien compara cuando ya hay alternativas.
        var directQuestion = Regex.IsMatch(question, @"\b(cual|que)\b") &&
            (question.Contains("mejor") || question.Contains("conviene") || question.Contains("recomiend") || question.Contains("elegir"));
        return (asksWhich && requestsAdvice && refersToEarlier) || directQuestion;
    }

    private static Vehicle? IdentifySelectedVehicle(
        Interpretation input, string message, List<Vehicle> options, VehicleConversationState state)
    {
        if (input.NumeroOpcion is >= 1 and <= 3 && options.Count >= input.NumeroOpcion)
            return options[input.NumeroOpcion.Value - 1];
        if (!string.IsNullOrWhiteSpace(input.Referencia))
        {
            var term = Normalize(input.Referencia);
            var found = options.FirstOrDefault(v => Normalize(v.Marca + " " + v.Linea).Contains(term));
            if (found is not null) return found;
        }
        var messageLower = Normalize(message);
        var directlyNamed = options.FirstOrDefault(v => messageLower.Contains(Normalize(v.Linea)) ||
            messageLower.Contains(Normalize(v.Marca + " " + v.Linea)));
        if (directlyNamed is not null) return directlyNamed;
        if (state.VehiculoElegido.HasValue)
            return options.FirstOrDefault(v => v.Id == state.VehiculoElegido.Value);
        return options.Count == 1 ? options[0] : null;
    }

    private static VehicleChatReply ExplainDetail(Vehicle v, bool dates, HashSet<int> availableIds)
    {
        if (dates && !availableIds.Contains(v.Id))
            return Reply($"{v.Marca} {v.Linea} ya no figura disponible para esas fechas. Prueba con otra opción o cambia las fechas.");
        var description = $"{v.Marca} {v.Linea} {v.Modelo} es un {v.Categoria.ToLowerInvariant()} de " +
            $"{v.Puestos} puestos, {v.Maletas} maletas, transmisión {v.Transmision.ToLowerInvariant()} y combustible {v.Combustible.ToLowerInvariant()}. " +
            $"Cuesta {Price(v.PrecioDia)} diarios; el depósito fijo es {Price(v.PrecioDia * 4)}. " +
            "Puedes abrir su ficha con el botón «Ver vehículo».";
        return new(description, [new(v, Reason(v))], dates, !dates);
    }

    private static VehicleChatReply ExplainComparison(
        List<Vehicle> vehicles, Vehicle? selection, string? criterion,
        VehicleConversationState state, bool dates, HashSet<int> availableIds)
    {
        var current = dates ? vehicles.Where(v => availableIds.Contains(v.Id)).ToList() : vehicles;
        if (current.Count == 0)
            return Reply("Las opciones anteriores ya no están disponibles para las fechas seleccionadas. Pide nuevas recomendaciones.");
        if (selection is not null && !current.Any(v => v.Id == selection.Id))
            return Reply("Ese vehículo no está disponible para las fechas seleccionadas.");

        var topic = Normalize(criterion ?? "general");
        if (topic is "maletas" or "equipaje" or "espacio")
        {
            var best = current.OrderByDescending(v => v.Maletas).ThenBy(v => v.PrecioDia).First();
            var listing = string.Join("; ", current.Select(v => $"{v.Marca} {v.Linea}: {v.Maletas} maletas"));
            return Reply($"En capacidad de equipaje, {best.Marca} {best.Linea} ofrece hasta {best.Maletas} maletas. Comparación: {listing}.");
        }
        if (topic is "puestos" or "pasajeros" or "capacidad")
        {
            var best = current.OrderByDescending(v => v.Puestos).ThenBy(v => v.PrecioDia).First();
            var listing = string.Join("; ", current.Select(v => $"{v.Marca} {v.Linea}: {v.Puestos} puestos"));
            return Reply($"{best.Marca} {best.Linea} ofrece hasta {best.Puestos} puestos. Comparación: {listing}.");
        }
        if (topic is "deposito")
        {
            var min = current.MinBy(v => v.PrecioDia)!;
            return Reply($"El depósito más bajo es el de {min.Marca} {min.Linea}: {Price(min.PrecioDia * 4)}. " +
                         "En CARS ATTM el depósito equivale a cuatro tarifas diarias, independientemente de la duración.");
        }
        if (topic is "transmision" or "combustible")
        {
            var rows = current.Select(v => $"{v.Marca} {v.Linea}: {v.Transmision}, {v.Combustible.ToLowerInvariant()}");
            return Reply("Estas son las características registradas en el catálogo: " + string.Join("; ", rows) + ".");
        }
        if (topic is "general" or "mejor" or "conveniencia")
        {
            // Comparar SOLO las ultimas opciones. Aplicar de nuevo las preferencias
            // conocidas y, si hay fechas, excluir las opciones ahora ocupadas.
            var suitable = current.Where(v =>
                (!state.Pasajeros.HasValue || v.Puestos >= state.Pasajeros.Value) &&
                (!state.Maletas.HasValue || v.Maletas >= state.Maletas.Value) &&
                (!state.PresupuestoDia.HasValue || v.PrecioDia <= state.PresupuestoDia.Value) &&
                Matches(v.Transmision, state.Transmision) &&
                Matches(v.Combustible, state.Combustible) &&
                Matches(v.Categoria, state.Categoria)).ToList();
            if (suitable.Count == 0)
                return Reply("Ninguna de las opciones anteriores cumple ahora todas tus preferencias. " +
                             "Pídeme nuevas recomendaciones para actualizar la selección.");

            var recommended = (state.Economico
                    ? suitable.OrderBy(v => v.PrecioDia).ThenByDescending(v => v.Modelo)
                    : suitable.OrderByDescending(v => Suitability(v, state)).ThenBy(v => v.PrecioDia))
                .First();
            var other = suitable.Where(v => v.Id != recommended.Id).ToList();
            var why = new List<string>();
            if (state.Economico)
                why.Add("priorizas un vehículo económico y es la opción más barata de esta selección");
            else if (recommended.PrecioDia == suitable.Min(v => v.PrecioDia))
                why.Add("es la opción de menor tarifa entre las que cumplen tus condiciones");
            else
                why.Add("combina las características solicitadas con una buena posición en la selección");
            if (state.Pasajeros.HasValue)
                why.Add($"tiene {recommended.Puestos} puestos para las {state.Pasajeros.Value} personas indicadas");
            if (state.Maletas.HasValue)
                why.Add($"admite {recommended.Maletas} maletas (necesitas {state.Maletas.Value})");
            if (!string.IsNullOrWhiteSpace(state.Transmision))
                why.Add($"cuenta con transmisión {recommended.Transmision.ToLowerInvariant()}");

            var message = $"De las {suitable.Count} opciones anteriores que siguen cumpliendo tus requisitos, " +
                $"te recomendaría {recommended.Marca} {recommended.Linea} {recommended.Modelo}. " +
                $"Cuesta {Price(recommended.PrecioDia)} por día, con depósito fijo de {Price(recommended.PrecioDia * 4)}. " +
                $"¿Por qué? {string.Join("; ", why)}.";
            if (other.Count > 0)
                message += " Si prefieres otra prioridad, puedo comparar estas alternativas por precio o espacio para maletas.";
            if (!dates)
                message += " La disponibilidad para tus fechas todavía no se ha verificado.";
            return new VehicleChatReply(message, [new(recommended, Reason(recommended))], dates, !dates);
        }
        var low = current.MinBy(v => v.PrecioDia)!;
        return Reply($"La opción más económica es {low.Marca} {low.Linea}, con {Price(low.PrecioDia)} diarios. " +
                     "Tarifas de los demás: " + string.Join("; ", current.Select(v => $"{v.Marca} {v.Linea}: {Price(v.PrecioDia)}")) + ".");
    }

    private static VehicleChatReply ExplainCost(
        List<Vehicle> vehicles, Vehicle? chosen, VehicleConversationState state, bool dates)
    {
        var days = state.DuracionDias;
        if (days is null)
            return Reply("¿Cuántos días necesitas el vehículo? Puedo calcular el alquiler y el depósito con las tarifas reales.");
        if (chosen is null)
        {
            var values = vehicles.Select(v =>
                $"{v.Marca} {v.Linea}: alquiler {Price(v.PrecioDia * days.Value)}, depósito {Price(v.PrecioDia * 4)}");
            return Reply($"Para {days} días, los valores son: " + string.Join("; ", values) +
                ". El depósito es aparte del alquiler y equivale siempre a cuatro tarifas diarias.");
        }
        var rental = chosen.PrecioDia * days.Value;
        var deposit = chosen.PrecioDia * 4;
        return Reply($"Para {days} días con {chosen.Marca} {chosen.Linea}: " +
            $"alquiler estimado {Price(rental)} y depósito fijo {Price(deposit)}. " +
            $"La suma de ambos conceptos es {Price(rental + deposit)}. " +
            "El depósito se gestiona según las condiciones de entrega, devolución y daños.");
    }

    private static bool IsEligibleStatus(Vehicle v) => v.Activo &&
        string.Equals(v.Estado, "DISPONIBLE", StringComparison.OrdinalIgnoreCase);

    private static bool Matches(string actual, string? expected) =>
        string.IsNullOrWhiteSpace(expected) || Normalize(actual) == Normalize(expected);

    private static bool IsAllowed(string? value, params string[] values) =>
        !string.IsNullOrWhiteSpace(value) && values.Contains(Normalize(value));

    private static string Normalize(string s)
    {
        var normalized = s.Trim().ToLowerInvariant().Normalize(NormalizationForm.FormD);
        return new string(normalized.Where(c =>
            CharUnicodeInfo.GetUnicodeCategory(c) != UnicodeCategory.NonSpacingMark).ToArray());
    }

    private static int Suitability(Vehicle v, VehicleConversationState s)
    {
        var score = 0;
        var usage = Normalize(s.Uso ?? "");
        var category = Normalize(v.Categoria);
        if ((usage.Contains("famil") || usage.Contains("viaje")) && (category is "suv" or "van")) score += 8;
        if (usage.Contains("ciudad") && (category is "compacto" or "sedan")) score += 8;
        if (s.Pasajeros.HasValue) score -= Math.Max(0, v.Puestos - s.Pasajeros.Value);
        if (s.Maletas.HasValue) score -= Math.Max(0, v.Maletas - s.Maletas.Value);
        if (!s.Economico) score += Math.Max(0, v.Modelo - 2020);
        return score;
    }

    private static bool TryDate(string? raw, out DateTime value) =>
        DateTime.TryParseExact(raw, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out value);

    private static DateTime BogotaToday()
    {
        try { return TimeZoneInfo.ConvertTimeBySystemTimeZoneId(DateTimeOffset.UtcNow, "America/Bogota").Date; }
        catch (TimeZoneNotFoundException) { return DateTime.Today; }
    }

    private static string Price(decimal amount) =>
        "$" + amount.ToString("N0", Colombia) + " COP";

    private static string Reason(Vehicle v) =>
        $"{v.Puestos} puestos, {v.Maletas} maletas, {v.Transmision.ToLowerInvariant()}. " +
        $"Tarifa diaria: {Price(v.PrecioDia)}.";

    private static VehicleChatReply Reply(string text) => new(text, [], false);
}
