# Build de la aplicación Blazor con .NET 10 LTS.
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build

ARG PROJECT=CarsATTM-CustomerApp.csproj
WORKDIR /src
COPY . .
RUN dotnet restore "$PROJECT"
RUN dotnet publish "$PROJECT" -c Release -o /app/publish /p:UseAppHost=false

# Runtime con curl para el healthcheck de Docker Compose.
FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /app/publish .
ENV ASPNETCORE_URLS=http://+:80
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=8 CMD curl -fsS http://127.0.0.1/health || exit 1
ENTRYPOINT ["dotnet", "CarsATTM-CustomerApp.dll"]
