# ObraTrack — API de rastreo GPS para herramientas

Backend en **FastAPI + MySQL** que recibe posiciones de una **ESP32 + NEO-6M**, las asocia a una herramienta de construcción y genera alertas cuando sale de una **geocerca circular**. Incluye un panel web de demostración en HTML/CSS/JS vanilla y un simulador para probar sin hardware.

**Estado:** MVP funcional. 15 pruebas automatizadas y flujo completo verificado contra MySQL 8.0.46.

---

## Ruta rápida

1. **Crear la base de datos y el usuario** (una sola vez):

   ```bash
   sudo mysql < sql/create_database.sql
   ```

   El script crea `obratrack` y el usuario `obratrack / obratrack_dev` en localhost.

2. **Instalar dependencias**:

   ```bash
   make install
   ```

3. **Configurar variables de entorno**:

   ```bash
   cp .env.example .env
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   # Pega el resultado en JWT_SECRET dentro de .env
   ```

   Los valores por defecto de MySQL ya coinciden con el script SQL.

4. **Cargar datos de demostración** (opcional):

   ```bash
   make seed
   # Usuario: demo@example.com / demo1234
   # Imprime también el token de la ESP32
   ```

5. **Arrancar el servidor**:

   ```bash
   make dev
   ```

6. **Verificar**:

   - Panel web: <http://127.0.0.1:8000>
   - Salud de la API y MySQL: <http://127.0.0.1:8000/api/health>
   - Documentación interactiva: <http://127.0.0.1:8000/docs>

Si no usas `make`:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Cómo funciona

```text
┌─────────────────┐   POST /api/telemetry        ┌──────────────┐
│ ESP32 + NEO-6M  │   X-Device-Token             │   FastAPI    │
│ (WiFi)          │ ───────────────────────────► │              │
└─────────────────┘                              │  SQLAlchemy  │
                                                 │      │       │
┌─────────────────┐   JWT + polling cada 5 s     │      ▼       │
│ Panel web       │ ◄─────────────────────────── │    MySQL     │
│ HTML/CSS/JS     │   JSON                       └──────────────┘
└─────────────────┘
```

Cada POST de telemetría:

1. Autentica el dispositivo con `X-Device-Token`.
2. Guarda la posición en `positions` y actualiza la última posición en `devices`.
3. Calcula la distancia al centro de la geocerca con **Haversine**.
4. Si pasa de `inside` a `outside`, crea una alerta `geofence_exit`.
5. Si vuelve a entrar, resuelve las alertas abiertas de ese dispositivo.

El panel consulta el estado cada 5 segundos. No hay WebSockets en el MVP: es simple, suficiente para una demo y no requiere infraestructura extra.

---

## API

| Método | Ruta | Autenticación | Descripción |
|---|---|---|---|
| `POST` | `/api/auth/register` | Pública | Crear cuenta |
| `POST` | `/api/auth/login` | Pública | Obtener JWT |
| `GET` | `/api/auth/me` | JWT | Perfil actual |
| `GET` `POST` | `/api/devices` | JWT | Listar / registrar herramientas |
| `GET` `PATCH` `DELETE` | `/api/devices/{id}` | JWT | Detalle, edición, borrado |
| `POST` | `/api/devices/{id}/rotate-token` | JWT | Nuevo token para la ESP32 |
| `GET` | `/api/devices/{id}/positions` | JWT | Historial (`limit`, `since`, `until`) |
| `GET` | `/api/devices/{id}/status` | JWT | Última posición, distancia y alertas |
| `GET` `PUT` `DELETE` | `/api/devices/{id}/geofence` | JWT | Geocerca circular |
| `POST` | `/api/telemetry` | Token de dispositivo | Recibir posición GPS |
| `GET` | `/api/alerts` | JWT | Alertas (`state=open\|resolved\|all`) |
| `POST` | `/api/alerts/{id}/acknowledge` | JWT | Marcar alerta como vista |
| `GET` | `/api/overview` | JWT | Contadores del panel |
| `GET` | `/api/health` | Pública | Estado de API y MySQL |

La documentación interactiva con esquemas y ejemplos está en `/docs`.

### Autenticación

**Panel (JWT):**

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"demo1234"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/devices
```

**Dispositivo (token fijo):** se genera al crear la herramienta y se muestra en el panel. Se envía en el encabezado `X-Device-Token`.

### Contrato de telemetría

```bash
curl -X POST http://127.0.0.1:8000/api/telemetry \
  -H "X-Device-Token: ot_reemplaza_esto" \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 4.609710,
    "lon": -74.081750,
    "speed_kmh": 3.2,
    "accuracy_m": 4.5,
    "satellites": 9,
    "battery_pct": 87
  }'
```

| Campo | Tipo | Obligatorio | Notas |
|---|---|---|---|
| `lat` | número | Sí | −90 a 90 |
| `lon` | número | Sí | −180 a 180 |
| `recorded_at` | ISO 8601 | No | Hora del fix; si se omite, se usa la del servidor |
| `speed_kmh` | número | No | 0 a 400 |
| `accuracy_m` | número | No | Precisión estimada en metros |
| `altitude_m` | número | No | Altitud |
| `battery_pct` | entero | No | 0 a 100 |
| `satellites` | entero | No | 0 a 64 |

Respuesta `201`:

```json
{
  "position_id": 12,
  "recorded_at": "2026-11-16T16:30:00Z",
  "received_at": "2026-11-16T16:30:01Z",
  "inside_geofence": false,
  "distance_to_center_m": 1180.4,
  "alert_created": true,
  "resolved_alerts": 0
}
```

Los errores usan el formato estándar de FastAPI: `{"detail": "mensaje"}`. Los fixes `(0,0)` que envía el NEO-6M antes de tener señal se rechazan con `422` (configurable).

### Reglas de la geocerca

1. Cada dispositivo tiene **una** geocerca circular: centro + radio.
2. La **primera** posición solo guarda el estado (`inside`/`outside`); no genera alerta para evitar falsos positivos al instalar el equipo.
3. Una salida (`inside → outside`) crea **una** alerta `geofence_exit`.
4. Mientras siga fuera no se duplican alertas.
5. Un reingreso resuelve automáticamente las alertas abiertas.
6. Al crear o editar la geocerca se recalcula el estado con la última posición, sin alertar.

---

## Modelo de datos

| Tabla | Propósito |
|---|---|
| `users` | Cuentas del panel, contraseña con PBKDF2-SHA256 |
| `devices` | Herramientas, token, última posición y estado de geocerca |
| `positions` | Historial de fixes GPS |
| `geofences` | Una geocerca circular por dispositivo |
| `alerts` | Salidas de geocerca, con `acknowledged_at` y `resolved_at` |

Las claves foráneas usan `ON DELETE CASCADE`: borrar una herramienta elimina su historial, geocerca y alertas. Las tablas se crean al arrancar (`create_all`); para producción conviene migrar a **Alembic**.

Fechas: se almacenan en **UTC** y la API las devuelve como ISO 8601 con sufijo `Z`.

---

## Configuración

Todas las variables se leen de `.env` o del entorno.

| Variable | Por defecto | Uso |
|---|---|---|
| `DB_HOST` / `DB_PORT` | `127.0.0.1` / `3306` | Conexión MySQL |
| `DB_USER` / `DB_PASSWORD` | `obratrack` / `obratrack_dev` | Credenciales |
| `DB_NAME` | `obratrack` | Base de datos |
| `DATABASE_URL` | — | Cadena completa; tiene prioridad |
| `JWT_SECRET` | valor de desarrollo | **Cámbialo**; mínimo 32 bytes |
| `JWT_EXPIRE_MINUTES` | `720` | Vigencia del JWT |
| `ALLOW_REGISTRATION` | `true` | Permite crear cuentas desde la API |
| `CORS_ORIGINS` | `*` | Orígenes permitidos, separados por coma |
| `TELEMETRY_REJECT_NULL_ISLAND` | `true` | Rechaza fixes `(0,0)` |
| `ENVIRONMENT` | `development` | En `production` exige un `JWT_SECRET` fuerte |

---

## Probar el sistema

### Sin hardware

1. Crea una herramienta en el panel y copia su token.
2. Define una geocerca (por ejemplo, radio de 150 m).
3. Ejecuta el simulador con el mismo centro:

```bash
.venv/bin/python scripts/simulate_device.py \
  --token ot_tu_token \
  --lat 4.609710 --lon -74.081750 --radius 150 \
  --interval 2 --count 40
```

El simulador recorre una órbita que entra y sale de la geocerca, así que verás alertas crearse y resolverse en el panel. `--count 0` envía indefinidamente.

### Con el celular como GPS (sin ESP32)

La app **GPSLogger for Android** puede publicar cada fix directo a `/api/telemetry`, con el mismo payload y la misma autenticación que la ESP32. Instálala desde [F-Droid](https://f-droid.org/packages/com.mendhak.gpslogger/) o un APK de [GitHub Releases](https://github.com/mendhak/gpslogger/releases) (ya no está en Play Store).

En la PC:

1. Arranca la API con `make dev` (ya escucha en `0.0.0.0`).
2. Averigua tu IP local: `hostname -I` (ejemplo: `192.168.1.42`).
3. Si usas UFW, abre el puerto: `sudo ufw allow 8000/tcp`.

En el celular (misma red WiFi que la PC), en GPSLogger:

1. *Logging details*: intervalo de 10 s, filtro de distancia y precisión en 0. En *Performance* deja solo el proveedor GPS activo (desactiva el de red para que no lleguen saltos de antena celular).
2. *Auto Upload & Send → Custom URL*:

   | Campo | Valor |
   |---|---|
   | Log to custom URL | activado |
   | URL | `http://192.168.1.42:8000/api/telemetry` |
   | HTTP Method | `POST` |
   | HTTP Body | `{"lat":%lat,"lon":%lon,"speed_kmh":%spd_kph,"accuracy_m":%acc,"satellites":%sat,"battery_pct":%batt}` |
   | HTTP Headers | `X-Device-Token: ot_tu_token` y `Content-Type: application/json` (una línea cada uno) |

3. Vuelve a la pantalla principal y pulsa el botón de iniciar registro.

Notas: `%spd_kph` va en km/h (`%spd` sería m/s). Si el celular pierde la conexión, GPSLogger encola los envíos; activa *Discard offline locations* para no recibir una ráfaga de puntos viejos. Con pantalla bloqueada Android puede pausar la app (Doze); mientras pruebes, deja el celular desbloqueado o desactiva la optimización de batería para GPSLogger. Para validar conectividad antes de iniciar, abre `http://192.168.1.42:8000/api/health` en el navegador del celular.

### Con ESP32 + NEO-6M

Sigue la guía **[docs/hardware-test.md](docs/hardware-test.md)**. Propone tres etapas para aislar fallas:

| Etapa | Sketch | Qué comprueba |
|---|---|---|
| 1. GPS solo | `firmware/01_gps_passthrough/` | Cableado, baudios, antena y fix |
| 2. WiFi + API | `firmware/02_api_test/` | Red, IP, firewall y token |
| 3. Integración | `firmware/obratrack_esp32.ino` | Flujo completo GPS → API → panel |

El sketch final usa `TinyGPS++`, publica cada 10 segundos y omite `recorded_at` para que el servidor asigne la hora.

---

## Pruebas

```bash
make test
# 16 passed
```

Las pruebas usan SQLite temporal para no depender de MySQL y cubren registro/login, aislamiento entre usuarios, CRUD de dispositivos y geocercas, telemetría, alertas, historial, overview, rotación de token y borrado en cascada.

Para probar contra MySQL, arranca el servidor con `DATABASE_URL` apuntando a tu instancia y ejecuta el flujo del simulador; el arranque crea el esquema automáticamente.

---

## Estructura

```text
ObraTrack/
├── app/
│   ├── main.py              # FastAPI, CORS, health, frontend estático
│   ├── config.py            # Settings desde .env
│   ├── database.py          # Engine y sesiones SQLAlchemy
│   ├── models.py            # users, devices, positions, geofences, alerts
│   ├── schemas.py           # Contratos Pydantic
│   ├── security.py          # PBKDF2, JWT, tokens de dispositivo
│   ├── geo.py               # Haversine y punto en círculo
│   ├── deps.py              # Sesión, JWT y autenticación de dispositivos
│   ├── seed.py              # Datos de demostración
│   └── routers/             # auth, devices, geofences, telemetry, alerts, overview
├── static/                  # Panel demo (HTML + CSS + JS + Leaflet)
├── scripts/simulate_device.py
├── docs/hardware-test.md    # Guía de montaje y pruebas por etapas
├── firmware/
│   ├── 01_gps_passthrough/  # Diagnóstico del NEO-6M
│   ├── 02_api_test/         # Diagnóstico de WiFi + API
│   └── obratrack_esp32.ino  # Sketch de integración
├── sql/create_database.sql
├── tests/
├── requirements.txt
└── .env.example
```

---

## Decisiones y límites del MVP

| Tema | Decisión actual | Siguiente paso sugerido |
|---|---|---|
| Tiempo real | Polling cada 5 s | SSE o WebSockets |
| Geocerca | Una circular por dispositivo | Varias y polígonos |
| Detección offline | No implementada | Alerta si `last_seen_at` supera un umbral |
| Tokens de dispositivo | Guardados en claro para poder copiarlos | Guardar hash y mostrarlos una sola vez |
| Migraciones | `create_all` al arrancar | Alembic |
| Rate limiting | No implementado | `slowapi` en login y telemetría |
| Roles | Un usuario dueño por herramienta | Equipos y herramientas compartidas |
| Transporte | HTTP en red local | HTTPS/TLS obligatorio fuera de la LAN |
| Registro | Abierto por defecto | `ALLOW_REGISTRATION=false` en producción |

**Seguridad para la sustentación:** las contraseñas usan PBKDF2-SHA256 con sal; el JWT expira; cada dispositivo tiene su propio token revocable; las consultas siempre filtran por `owner_id` para evitar acceso cruzado. Aun así, un MVP universitario no debe exponerse a internet sin HTTPS, rate limiting y tokens hasheados.

---

## Problemas comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `Access denied for user 'obratrack'` | La base o el usuario no existen | Ejecutar `sudo mysql < sql/create_database.sql` |
| `Can't connect to MySQL server` | MySQL detenido | `sudo systemctl start mysql` |
| `401` en `/api/telemetry` | Token incorrecto o dispositivo inactivo | Copiar el token actual del panel; revisar `active` |
| `422` con `(0,0)` | El NEO-6M aún no tiene fix | Esperar señal, preferiblemente al aire libre |
| Mapa vacío en el panel | Sin internet para las teselas de OpenStreetMap | Conectar a internet o alojar teselas propias |
| CORS bloqueado | Panel servido desde otro origen | Ajustar `CORS_ORIGINS` y reiniciar |
| Error de autenticación MySQL 8 | Falta el plugin `caching_sha2_password` | `cryptography` ya viene en `requirements.txt` |

---

## Checklist para la demo

- [ ] Base de datos creada y `/api/health` devuelve `database: "ok"`.
- [ ] `python -m app.seed` cargó usuario, herramienta y geocerca.
- [ ] El panel muestra la herramienta y su token.
- [ ] Una telemetría dentro de la geocerca responde `inside_geofence: true`.
- [ ] Una telemetría fuera crea una alerta visible en el panel.
- [ ] El reingreso resuelve la alerta.
- [ ] `make test` pasa completo.
- [ ] La ESP32 (o el simulador) publica con `X-Device-Token`.

## Siguiente paso

Prueba el flujo completo con `make seed`, `make dev` y el simulador. Después, si quieres, puedo ayudarte con el despliegue (Docker/systemd), el endurecimiento de seguridad o la integración de WebSockets para actualizaciones en vivo.
