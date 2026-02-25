/**
 * ESP32-C6 BLE HID Mouse using MPU6050
 
 */

#define PIN_SDA     6
#define PIN_SCL     7
#define PIN_BUTTON  10

#define SENSITIVITY   0.08f
#define SMOOTH_FACTOR 0.70f
#define MAX_DELTA     20
#define CALIB_SAMPLES 200
#define DEBOUNCE_MS   50

#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <NimBLEDevice.h>
#include <NimBLEServer.h>
#include <NimBLEUtils.h>
#include <NimBLEHIDDevice.h>
#include <HIDTypes.h>

// ── HID descriptor – NO Report ID tag, so host uses implicit ID 0 ──
static const uint8_t hidReportDescriptor[] = {
  0x05, 0x01,  0x09, 0x02,  0xA1, 0x01,
  0x09, 0x01,  0xA1, 0x00,
  0x05, 0x09,  0x19, 0x01,  0x29, 0x03,
  0x15, 0x00,  0x25, 0x01,  0x95, 0x03,
  0x75, 0x01,  0x81, 0x02,
  0x95, 0x01,  0x75, 0x05,  0x81, 0x03,
  0x05, 0x01,  0x09, 0x30,  0x09, 0x31,
  0x15, 0x81,  0x25, 0x7F,
  0x75, 0x08,  0x95, 0x02,  0x81, 0x06,
  0xC0, 0xC0
};

Adafruit_MPU6050      mpu;
NimBLEHIDDevice*      hid        = nullptr;
NimBLECharacteristic* inputMouse = nullptr;
NimBLEServer*         pServer    = nullptr;
bool bleConnected = false;

float gyroOffsetX = 0, gyroOffsetY = 0;
float smoothX = 0, smoothY = 0;
bool           lastRawButton    = HIGH;
bool           stableButton     = HIGH;
unsigned long  lastDebounceTime = 0;

// ── FIX 4: updated onConnect signature for NimBLE v2.x / arduino-esp32 v3.x ──
class ServerCallbacks : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer* pSrv, NimBLEConnInfo& connInfo) override {
    bleConnected = true;
    Serial.println("[BLE] Client connected");
  }
  void onDisconnect(NimBLEServer* pSrv, NimBLEConnInfo& connInfo, int reason) override {
    bleConnected = false;
    Serial.printf("[BLE] Disconnected (reason %d) – restarting advertising\n", reason);
    NimBLEDevice::startAdvertising();
  }
};

void sendMouseReport(int8_t dx, int8_t dy, uint8_t buttons) {
  if (!bleConnected || !inputMouse) return;
  uint8_t report[3] = { buttons, (uint8_t)dx, (uint8_t)dy };
  inputMouse->setValue(report, sizeof(report));
  inputMouse->notify();
}

int8_t clampDelta(float v) {
  if (v >  MAX_DELTA) v =  MAX_DELTA;
  if (v < -MAX_DELTA) v = -MAX_DELTA;
  return (int8_t)v;
}

void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(PIN_BUTTON, INPUT_PULLUP);

  Wire.begin(PIN_SDA, PIN_SCL);
  if (!mpu.begin()) {
    Serial.println("[ERROR] MPU6050 not found!");
    while (true) delay(500);
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  Serial.println("[CAL] Keep still for 2 seconds...");
  delay(500);
  double sumX = 0, sumY = 0;
  for (int i = 0; i < CALIB_SAMPLES; i++) {
    sensors_event_t a, g, t;
    mpu.getEvent(&a, &g, &t);
    sumX += g.gyro.x;
    sumY += g.gyro.y;  // using Y not Z for yaw on C6 orientation
    delay(10);
  }
  gyroOffsetX = (float)(sumX / CALIB_SAMPLES);
  gyroOffsetY = (float)(sumY / CALIB_SAMPLES);

  // ── FIX 2: no bonding for simple mouse; avoids auth-failure disconnects ──
  NimBLEDevice::init("ESP32-C6 Mouse");
  NimBLEDevice::setSecurityAuth(false, false, false);  // no bond, no MITM

  pServer = NimBLEDevice::createServer();
  pServer->setCallbacks(new ServerCallbacks());

  hid = new NimBLEHIDDevice(pServer);
  hid->setManufacturer("Espressif");
  hid->setPnp(0x02, 0x045E, 0x0040, 0x0110);
  hid->setHidInfo(0x00, 0x01);
  hid->setReportMap((uint8_t*)hidReportDescriptor, sizeof(hidReportDescriptor));

  // ── FIX 1: register Battery Service BEFORE startServices() ──
  hid->setBatteryLevel(100);   // mandatory for Windows/Android to complete connection

  // ── FIX 3: report ID 0 matches a descriptor with no REPORT_ID tag ──
  inputMouse = hid->getInputReport(0);

  hid->startServices();

  NimBLEAdvertising* pAdv = NimBLEDevice::getAdvertising();
  pAdv->setAppearance(HID_MOUSE);
  pAdv->addServiceUUID(hid->getHidService()->getUUID());
  NimBLEAdvertisementData scanData;
  pAdv->setScanResponseData(scanData);
  pAdv->start();

  Serial.println("[BLE] Advertising – pair now!");
}

void loop() {
  sensors_event_t a, g, t;
  mpu.getEvent(&a, &g, &t);

  float gx = g.gyro.x - gyroOffsetX;
  float gz = g.gyro.z - gyroOffsetY;

  float rawDX =  gz * (180.0f / M_PI) * SENSITIVITY;
  float rawDY = -gx * (180.0f / M_PI) * SENSITIVITY;

  smoothX = SMOOTH_FACTOR * smoothX + (1.0f - SMOOTH_FACTOR) * rawDX;
  smoothY = SMOOTH_FACTOR * smoothY + (1.0f - SMOOTH_FACTOR) * rawDY;

  int8_t dx = clampDelta(smoothX);
  int8_t dy = clampDelta(smoothY);

  bool reading = digitalRead(PIN_BUTTON);
  if (reading != lastRawButton) {
    lastDebounceTime = millis();
    lastRawButton = reading;
  }
  if ((millis() - lastDebounceTime) > DEBOUNCE_MS) {
    stableButton = reading;
  }
  uint8_t buttons = (stableButton == LOW) ? 0x01 : 0x00;

  if (bleConnected) {
    sendMouseReport(dx, dy, buttons);
  }

  delay(8);
}
