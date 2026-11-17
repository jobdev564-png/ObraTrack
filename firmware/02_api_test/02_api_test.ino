/*
 * ObraTrack — Prueba 2: WiFi y API sin GPS.
 *
 * Envía una posición fija a la API cada 10 segundos. Sirve para comprobar,
 * antes de conectar el GPS: red WiFi, IP del servidor, firewall y token.
 *
 * Antes de cargar, ajusta:
 *   WIFI_SSID, WIFI_PASSWORD, SERVER_IP y DEVICE_TOKEN.
 *
 * Monitor Serie: 115200.
 *
 * Resultados esperados:
 *   GET /api/health -> 200   (hay red y el servidor responde)
 *   POST /api/telemetry -> 201 (token válido y posición guardada)
 */

#include <WiFi.h>
#include <HTTPClient.h>

// ------------------------------ Configuración ------------------------------
const char* WIFI_SSID = "TU_WIFI";
const char* WIFI_PASSWORD = "TU_CLAVE";

// IP local de tu computador (en Linux: hostname -I). Sin barra final.
const char* SERVER_IP = "";
const uint16_t SERVER_PORT = 8000;

const char* DEVICE_TOKEN = "ot_reemplaza_con_el_token_del_panel";

static const double TEST_LAT = 4.609710;
static const double TEST_LON = -74.081750;
static const uint32_t SEND_INTERVAL_MS = 10000;

uint32_t lastSendMs = 0;

// ------------------------------- Funciones --------------------------------
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.printf("Conectando a %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\nWiFi OK. IP=%s RSSI=%d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.println("\nERROR: no se pudo conectar al WiFi (¿red de 2.4 GHz?).");
  }
}

void checkHealth() {
  String url = String("http://") + SERVER_IP + ":" + SERVER_PORT + "/api/health";

  WiFiClient client;
  HTTPClient http;
  http.setTimeout(8000);
  http.begin(client, url);

  int code = http.GET();
  if (code > 0) {
    Serial.printf("GET %s -> %d\n", url.c_str(), code);
    Serial.println(http.getString());
  } else {
    Serial.printf("GET %s -> ERROR %s\n", url.c_str(),
                  http.errorToString(code).c_str());
    Serial.println("Revisa IP, que uvicorn escuche en 0.0.0.0 y el firewall.");
  }
  http.end();
}

void sendTestPosition() {
  String url = String("http://") + SERVER_IP + ":" + SERVER_PORT + "/api/telemetry";
  String payload = "{\"lat\":" + String(TEST_LAT, 6) +
                   ",\"lon\":" + String(TEST_LON, 6) +
                   ",\"satellites\":7}";

  WiFiClient client;
  HTTPClient http;
  http.setTimeout(8000);
  http.begin(client, url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Token", DEVICE_TOKEN);

  int code = http.POST(payload);
  if (code > 0) {
    Serial.printf("POST /api/telemetry -> %d\n", code);
    Serial.println(http.getString());
    if (code == 401) Serial.println("Token inválido: cópialo de nuevo desde el panel.");
    if (code == 403) Serial.println("Dispositivo desactivado en el panel.");
    if (code == 422) Serial.println("Datos rechazados: revisa lat/lon.");
  } else {
    Serial.printf("POST /api/telemetry -> ERROR %s\n",
                  http.errorToString(code).c_str());
  }
  http.end();
}

// --------------------------------- Sketch ---------------------------------
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== Prueba WiFi + API (sin GPS) ===");
  connectWiFi();
  checkHealth();
  sendTestPosition();
  lastSendMs = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();

  if (millis() - lastSendMs >= SEND_INTERVAL_MS) {
    lastSendMs = millis();
    sendTestPosition();
  }
}
