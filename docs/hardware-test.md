# Probar ObraTrack con ESP32 + NEO-6M

Prueba el hardware **por etapas**: GPS solo, luego WiFi + API, y al final todo junto. Así, si algo falla, sabes exactamente qué parte revisar. Tiempo estimado: 30–45 minutos, más el tiempo que tarde el GPS en obtener el primer fix.

## Antes de empezar

- [ ] Servidor corriendo con `make dev` (escucha en `0.0.0.0:8000`).
- [ ] ESP32 y computador en la **misma red WiFi de 2.4 GHz**.
- [ ] IP local del computador: `hostname -I` (por ejemplo `192.168.3.220`).
- [ ] Panel abierto en <http://127.0.0.1:8000> con una herramienta creada.
- [ ] Token de la herramienta copiado desde el panel.
- [ ] Arduino IDE con la placa ESP32 y la librería **TinyGPS++** instaladas.
- [ ] Antena del NEO-6M conectada y con vista al cielo.

Comprueba la red desde el **navegador del celular**, usando la misma WiFi:

```text
http://192.168.3.220:8000/api/health
```

Debe responder `{"status":"ok","database":"ok",...}`. Si el celular no puede abrirlo, la ESP32 tampoco podrá.

Si tienes firewall activo:

```bash
sudo ufw allow 8000/tcp
sudo ufw status
```

> La IP puede cambiar si el router la reasigna. Si la ESP32 deja de conectar de un día para otro, vuelve a ejecutar `hostname -I` y actualiza `SERVER_IP`.

## Montaje

| NEO-6M | ESP32 | Obligatorio |
|---|---|---|
| `VCC` | `3V3` | Sí |
| `GND` | `GND` | Sí |
| `TX` | `GPIO16` (RX2) | Sí |
| `RX` | `GPIO17` (TX2) | Opcional |

```text
   NEO-6M                    ESP32
  ┌───────┐                ┌────────┐
  │ VCC ──┼────────────────┤ 3V3    │
  │ GND ──┼────────────────┤ GND    │
  │ TX  ──┼────────────────┤ GPIO16 │  RX2
  │ RX  ──┼────────────────┤ GPIO17 │  TX2
  └───────┘                └────────┘
```

Recomendaciones:

- No conectes la salida del GPS a 5 V: el ESP32 tolera **3.3 V** en sus GPIO.
- Une siempre las tierras (`GND`) de ambos módulos.
- La antena debe quedar plana, hacia el cielo y lejos de metal, motores o fuentes de alimentación.
- Si tu placa es **ESP32-WROVER** (con PSRAM), GPIO16/17 pueden estar ocupados. Usa GPIO25 (RX) y GPIO26 (TX), y ajusta las constantes del sketch.
- En **ESP32-S3/C3** los números de GPIO cambian: usa pines UART válidos de tu placa y actualiza `GPS_RX_PIN` y `GPS_TX_PIN`.
- Muchas placas NEO-6M tienen un LED que parpadea a 1 Hz cuando ya tienen fix.

## Prueba 1: GPS solo

**Sketch:** `firmware/01_gps_passthrough/01_gps_passthrough.ino`

1. Abre el sketch en Arduino IDE.
2. Selecciona tu placa (`ESP32 Dev Module` suele funcionar) y el puerto USB.
3. Carga y abre el **Monitor Serie a 115200 baudios**.
4. Llévalo al aire libre y espera.

Salida esperada:

```text
$GPGGA,...
$GPRMC,...
chars=1024 frases=3 checksum_fail=0 | sat=8 hdop=0.9 | fix=SI
lat=4.609710 lon=-74.081750 edad=210ms
```

Cómo interpretar:

| Observación | Significado | Qué hacer |
|---|---|---|
| `chars=0` | No llegan datos del GPS | Revisar TX→GPIO16, GND, alimentación y que el GPS esté a 9600 |
| `checksum_fail` aumenta | Datos corruptos o baudios incorrectos | Revisar cableado corto, GND común y baudios |
| `sat=0` y `fix=NO` | Sin satélites | Ir al aire libre; revisar antena |
| `sat>=4` y `fix=NO` | Ve satélites pero aún no fija | Esperar; primer fix en frío puede tardar hasta 12 minutos |
| `fix=SI` | GPS listo | Pasar a la prueba 2 |

> El NEO-6M puede tardar más la primera vez o si estuvo mucho tiempo sin energía. Después suele fijar en 30–60 segundos. **Bajo techo normalmente no habrá fix.**

## Prueba 2: WiFi + API sin GPS

**Sketch:** `firmware/02_api_test/02_api_test.ino`

Este sketch envía una posición fija cada 10 segundos. Comprueba red, IP, firewall y token sin depender del GPS.

Ajusta al inicio del archivo:

```cpp
const char* WIFI_SSID = "TU_WIFI";
const char* WIFI_PASSWORD = "TU_CLAVE";
const char* SERVER_IP = "192.168.3.220";  // tu IP local
const char* DEVICE_TOKEN = "ot_...";      // token del panel
```

Carga y abre el Monitor Serie:

```text
WiFi OK. IP=192.168.3.221 RSSI=-58 dBm
GET http://192.168.3.220:8000/api/health -> 200
{"status":"ok","database":"ok",...}
POST /api/telemetry -> 201
{"position_id":18,"inside_geofence":true,...}
```

| Código | Significado | Solución |
|---|---|---|
| `201` | Posición guardada | Continuar |
| `401` | Token inválido | Copiar de nuevo el token del panel |
| `403` | Dispositivo desactivado | Activar la herramienta en el panel |
| `422` | Datos rechazados | Revisar lat/lon |
| `-1` o error de conexión | No hay ruta al servidor | IP, puerto, firewall o uvicorn escuchando solo en 127.0.0.1 |
| GET `-1`, POST `-1` | WiFi conectado pero API inalcanzable | Probar la URL desde el celular |

En el panel debe aparecer la herramienta en `4.609710, -74.081750` y sumar una posición cada 10 segundos.

## Prueba 3: integración completa

**Sketch:** `firmware/obratrack_esp32.ino`

1. Ajusta WiFi, `SERVER_IP` y `DEVICE_TOKEN` (la URL ya se arma con esos valores si usas el sketch de ejemplo; si no, edita `API_URL`).
2. Carga el sketch y abre el Monitor Serie a 115200.
3. Espera un fix válido; verás:

```text
Fix: 4.609710, -74.081750 | sat=8 hdop=0.9
POST {"lat":4.609710,"lon":-74.081750,...} -> 201
{"position_id":19,...}
```

4. En el panel, selecciona la herramienta y verifica: marcador, “Visto hace …”, satélites y recorrido.

### Probar la geocerca

Hazlo caminando unos metros:

1. En el panel, pon el centro de la geocerca en tu ubicación actual (clic en el mapa) y un radio de **30–50 m**.
2. Espera la primera posición dentro. El servidor guarda el estado, **no genera alerta** (evita falsos positivos al instalar).
3. Aléjate más del radio y espera 10–20 segundos.
4. Debe aparecer la alerta `geofence_exit` y el marcador ponerse rojo.
5. Vuelve dentro; la alerta se resuelve automáticamente.
6. Revisa la pestaña **“Todas”** para ver el historial de alertas.

Notas:

- Un radio menor a 15 m puede disparar alertas falsas por la precisión del GPS. Usa 30–50 m para la demo.
- Si la primera posición ya cae fuera de la geocerca, no habrá alerta hasta que entres y vuelvas a salir. Es intencional.
- La geocerca debe estar **activa** y el centro debe corresponder al lugar real de la prueba.

### Alimentación

- Usa un power bank o una fuente estable; las transmisiones WiFi consumen picos de corriente.
- Si la ESP32 se reinicia al conectar WiFi, cambia el cable USB o la fuente.
- Para una prueba de campo, deja el conjunto en una caja con la antena mirando hacia arriba.

## Verificar en el servidor

```bash
# Últimas posiciones de la herramienta
mysql -uobratrack -pobratrack_dev -h127.0.0.1 obratrack -e "
SELECT id, lat, lon, inside_geofence, recorded_at
FROM positions ORDER BY id DESC LIMIT 10;"

# Alertas
mysql -uobratrack -pobratrack_dev -h127.0.0.1 obratrack -e "
SELECT id, type, message, created_at, resolved_at
FROM alerts ORDER BY id DESC LIMIT 10;"
```

También puedes usar `GET /api/devices/{id}/status` y `GET /api/alerts` desde `/docs`.

## Checklist de la prueba

- [ ] El Monitor Serie muestra tramas NMEA (llegan datos del GPS).
- [ ] El GPS obtiene `fix=SI` con al menos 4 satélites.
- [ ] `GET /api/health` responde `200` desde el celular.
- [ ] `POST /api/telemetry` responde `201` desde la ESP32.
- [ ] La herramienta aparece en el panel con posición y hora.
- [ ] Al salir de la geocerca se crea una alerta.
- [ ] Al regresar, la alerta se resuelve.
- [ ] El token no está escrito en el repositorio ni en capturas públicas.

## Problemas comunes

| Problema | Causa probable | Solución |
|---|---|---|
| Arduino no encuentra el puerto | Permisos USB | `sudo usermod -aG dialout $USER` y volver a iniciar sesión |
| Falla al cargar el sketch | Placa en modo incorrecto | Mantén `BOOT` al iniciar la carga; usa un cable de datos |
| Monitor Serie con basura | Baudios incorrectos | Monitor a **115200**; el GPS interno va a **9600** |
| No hay tramas NMEA | TX/GND mal conectados | Cruzar TX del GPS con RX del ESP32; GND común |
| NMEA sí, pero sin fix | Sin cielo o antena | Salir al aire libre; revisar antena; esperar |
| WiFi no conecta | Red de 5 GHz o captive portal | Usar 2.4 GHz WPA2; evitar redes con portal |
| `POST -> -1` | IP/firewall/puerto | Probar `/api/health` desde el celular; `sudo ufw allow 8000/tcp` |
| `POST -> 401` | Token incorrecto o rotado | Copiar el token actual del panel |
| `POST -> 201` pero no se ve el marcador | Panel desactualizado u otra herramienta seleccionada | Esperar 5 s, refrescar y revisar el dispositivo correcto |
| Alertas falsas | Radio muy pequeño o GPS con deriva | Subir el radio a 30–50 m |
| No se dispara la alerta | Ya estaba fuera, geocerca inactiva o centro incorrecto | Entrar primero, activar geocerca y revisar el centro |
| La ESP32 se reinicia | Fuente insuficiente | Power bank o fuente de 5 V estable |

## Evidencia para el informe

Guarda:

1. Foto del montaje con la ESP32 y el NEO-6M.
2. Captura del Monitor Serie con un `POST ... -> 201`.
3. Captura del panel con la herramienta, la geocerca y una alerta.
4. Salida de las consultas SQL de `positions` y `alerts`.
5. Resultado de `make test` (16 pruebas).

Con eso puedes demostrar el flujo completo: GPS → ESP32 → WiFi → API → MySQL → panel web → alerta.
