/*
 * ObraTrack — Prueba 1: verificar el NEO-6M por separado.
 *
 * Conexiones:
 *   NEO-6M VCC -> ESP32 3V3
 *   NEO-6M GND -> ESP32 GND
 *   NEO-6M TX  -> ESP32 GPIO16  (RX2)
 *   NEO-6M RX  -> ESP32 GPIO17  (TX2, opcional para esta prueba)
 *
 * Monitor Serie: 115200 baudios. El GPS habla a 9600.
 * Antena al aire libre. El primer fix puede tardar varios minutos.
 *
 * Qué revisar en el monitor:
 *   chars=0                  -> no llegan datos: TX, GND, alimentación o baudios.
 *   checksum_fail creciendo  -> ruido o baudios incorrectos.
 *   sat=0 sin fix            -> falta cielo abierto o antena.
 *   fix=SI                   -> el GPS ya entrega coordenadas válidas.
 */

#include <TinyGPSPlus.h>

static const int GPS_RX_PIN = 16;
static const int GPS_TX_PIN = 17;
static const uint32_t GPS_BAUD = 9600;

TinyGPSPlus gps;
HardwareSerial gpsSerial(2);
uint32_t lastSummaryMs = 0;

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("=== Prueba NEO-6M ===");
  Serial.println("Monitor a 115200. GPS a 9600. Antena al aire libre.");
  gpsSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
}

void loop() {
  while (gpsSerial.available() > 0) {
    char c = gpsSerial.read();
    gps.encode(c);
    Serial.write(c);  // Tramas NMEA crudas para comprobar que hay datos.
  }

  if (millis() - lastSummaryMs >= 2000) {
    lastSummaryMs = millis();

    Serial.println();
    Serial.printf(
      "chars=%lu frases=%lu checksum_fail=%lu | sat=%lu hdop=%.1f | fix=%s\n",
      (unsigned long)gps.charsProcessed(),
      (unsigned long)gps.sentencesWithFix(),
      (unsigned long)gps.failedChecksum(),
      (unsigned long)gps.satellites.value(),
      gps.hdop.hdop(),
      gps.location.isValid() ? "SI" : "NO"
    );

    if (gps.location.isValid()) {
      Serial.printf(
        "lat=%.6f lon=%.6f edad=%lums\n",
        gps.location.lat(),
        gps.location.lng(),
        (unsigned long)gps.location.age()
      );
    } else {
      Serial.println("Esperando fix... coloca la antena con vista directa al cielo.");
    }
  }
}
