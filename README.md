# Business Case Agent PoC

Aplicación local sin autenticación compuesta por Angular, FastAPI y SQLite. Todos los comandos de runtime, instalación, build y pruebas se ejecutan dentro de contenedores.

## Arranque

```bash
cp .env.example .env
export CODEX_API_KEY='PEGA_AQUI_TU_TOKEN'
docker compose up --build
```

La API no arranca sin un proveedor real, un modelo permitido y `CODEX_API_KEY`. La credencial se entrega al contenedor como secreto y no debe guardarse en `.env`.

En Windows también puedes abrir PowerShell en la raíz del proyecto y ejecutar:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\iniciar-app.ps1
```

El script inicia Docker Desktop si es necesario, solicita el token de forma segura, levanta los servicios, comprueba que los mocks estén desactivados y abre el navegador. Usa `-NoBuild` para omitir la reconstrucción o `-NoBrowser` para no abrir la página automáticamente.

- Aplicación: `http://localhost:4200`
- OpenAPI: `http://localhost:8000/api/docs`
- Healthcheck: `http://localhost:8000/api/v1/health`

La copia de `.env` es opcional para los valores no secretos. `CODEX_API_KEY` sí es obligatorio y debe permanecer fuera de ese archivo.

## Pruebas

Suite integral (un solo comando de shell, todas las ejecuciones dentro de Compose):

```bash
docker compose --profile test build test-backend test-frontend test-e2e && docker compose --profile test run --rm test-backend && docker compose --profile test run --rm test-frontend && docker compose --profile test run --rm test-e2e
```

Ejecución individual durante desarrollo:

```bash
docker compose --profile test run --rm test-backend
docker compose --profile test run --rm test-frontend
docker compose --profile test run --rm test-e2e
docker compose build web api
```

## Contrato OpenAPI

El contrato es generado por FastAPI y los tipos de Angular por `openapi-typescript`:

```bash
docker compose --profile tools run --rm api-contract
docker compose --profile tools run --rm frontend-tools
```

## Datos

SQLite vive en el volumen Docker `business-case-data`. Para este spec solo se persisten los metadatos del proyecto. Documentos, generación y revisión pertenecen a los specs 002–005.

## Límites de la PoC

- Uso local y monousuario.
- Sin autenticación ni autorización.
- No debe exponerse directamente a internet.
- Los proveedores simulados están restringidos al entorno automatizado de pruebas.

## Variables

- `API_PORT` y `WEB_PORT`: puertos públicos; por defecto `8000` y `4200`.
- `DATABASE_URL`: ruta SQLite del contenedor; por defecto `/data/business_case.db`.
- `MAX_REQUEST_BODY_BYTES`: máximo aceptado por request; por defecto 1 MiB.
- `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_GENERATOR_MODEL` y `LLM_CRITIC_MODEL`: configuran el agente real.
- `AGENT_MODE` y `AGENT_ENV`: identifican el entorno de ejecución.
