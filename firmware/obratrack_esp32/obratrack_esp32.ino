/*
 * ObraTrack — ESP32 + NEO-6M
 * Envía la posición GPS por HTTP POST a la API de ObraTrack.
 *
 * Requisitos:
 *   - Placa ESP32 configurada en Arduino IDE.
 *   - Librería TinyGPS++ (Library Manager de Arduino).
 *   - NEO-6M: VCC a 3V3, GND, TX del módulo -> GPIO16, RX del módulo -> GPIO17.
 *   - Token del dispositivo copiado desde el panel web.
 *
 * Ajusta WIFI_SSID, WIFI_PASSWORD, API_URL y DEVICE_TOKEN antes de cargar.
 * Usa HTTP solo en red local; en producción el backend debe ir detrás de HTTPS.
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <TinyGPSPlus.h>

// ------------------------------ Configuración ------------------------------
const char* WIFI_SSID = "TU_WIFI";
const char* WIFI_PASSWORD = "TU_CLAVE";

// IP de tu computador en la red local y puerto de uvicorn.
const char* API_URL = "http://192.168.1.100:8000/api/telemetry";
const char* DEVICE_TOKEN = "ot_reemplaza_con_el_token_del_panel";

// Si tu placa es ESP32-WROVER (con PSRAM), GPIO16/17 pueden estar ocupados.
// En ese caso usa, por ejemplo, GPIO25 (RX) y GPIO26 (TX) y ajusta aquí.
static const int GPS_RX_PIN = 16;  // TX del NEO-6M
static const int GPS_TX_PIN = 17;  // RX del NEO-6M
static const uint32_t GPS_BAUD = 9600;
static const uint32_t SEND_INTERVAL_MS = 10000;

TinyGPSPlus gps;
HardwareSerial gpsSerial(2);
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
    Serial.printf("\nWiFi conectado, IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\nNo se pudo conectar; se reintentará.");
  }
}

bool sendPosition() {
  if (!gps.location.isValid() || gps.location.age() > 5000) {
    Serial.printf(
      "Sin fix GPS válido; esperando señal... sat=%lu hdop=%.1f\n",
      (unsigned long)gps.satellites.value(),
      gps.hdop.hdop()
    );
    return false;
  }

  Serial.printf(
    "Fix: %.6f, %.6f | sat=%lu hdop=%.1f\n",
    gps.location.lat(),
    gps.location.lng(),
    (unsigned long)gps.satellites.value(),
    gps.hdop.hdop()
  );

  // El servidor pone la hora de recepción; no hace falta RTC en la ESP32.
  String payload = "{\"lat\":" + String(gps.location.lat(), 6);
  payload += ",\"lon\":" + String(gps.location.lng(), 6);

  if (gps.speed.isValid()) {
    payload += ",\"speed_kmh\":" + String(gps.speed.kmph(), 2);
  }
  if (gps.satellites.isValid()) {
    payload += ",\"satellites\":" + String(gps.satellites.value());
  }
  payload += "}";

  WiFiClient client;
  HTTPClient http;
  http.setTimeout(8000);
  http.begin(client, API_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Token", DEVICE_TOKEN);

  int statusCode = http.POST(payload);
  String response = http.getString();
  http.end();

  Serial.printf("POST %s -> %d\n", payload.c_str(), statusCode);
  if (statusCode > 0) Serial.println(response);
  return statusCode == 201;
}

// --------------------------------- Sketch ---------------------------------
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\nObraTrack GPS iniciando...");

  gpsSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
  connectWiFi();
}

void loop() {
  // Alimentar el parser con todo lo que llega del NEO-6M.
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }

  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  if (millis() - lastSendMs >= SEND_INTERVAL_MS) {
    lastSendMs = millis();
    sendPosition();
  }
}
