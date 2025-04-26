#include <Wire.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>

// Cấu hình WiFi
const char* ssid = "KawaII";
const char* password = "dmcayvcl";

// Địa chỉ của MQTT broker
const char* mqtt_server = "172.20.10.2";  // Thay đổi với địa chỉ IP của server Node.js

WiFiClient espClient;
PubSubClient client(espClient);

// Thông tin của cảm biến MPU6050
const int MPU_addr = 0x68;
int16_t AcX, AcY, AcZ;

int minVal = 265;
int maxVal = 402;

double x, y, z;

void setup_wifi() {
  delay(10);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("WiFi connected");
}

void reconnect() {
  // Vòng lặp khi chưa kết nối được
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    // Kết nối với broker MQTT, cung cấp username và password
    if (client.connect("ESP8266Client", "hiep", "1234")) {  // Tên người dùng và mật khẩu
      Serial.println("MQTT connected");
    } else {
      Serial.print("Failed, rc=");
      Serial.print(client.state());
      Serial.println(" trying again in 5 seconds...");
      delay(5000);
    }
  }
}

void setup() {
  // Khởi tạo giao tiếp I2C và cảm biến MPU6050
  Wire.begin();
  Wire.beginTransmission(MPU_addr);
  Wire.write(0x6B);  // Wake up the MPU6050
  Wire.write(0);
  Wire.endTransmission(true);

  Serial.begin(9600);
  setup_wifi();

  // Cấu hình server MQTT và cổng (1883 là cổng mặc định của MQTT)
  client.setServer(mqtt_server, 1883);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();  // Kiểm tra các kết nối và tin nhắn đến từ MQTT broker

  // Đọc dữ liệu từ cảm biến MPU6050
  Wire.beginTransmission(MPU_addr);
  Wire.write(0x3B);  // Bắt đầu từ register 0x3B (ACCEL_XOUT_H)
  Wire.endTransmission(false);
  Wire.requestFrom(MPU_addr, 14, true);

  AcX = Wire.read() << 8 | Wire.read();
  AcY = Wire.read() << 8 | Wire.read();
  AcZ = Wire.read() << 8 | Wire.read();

  // Chuyển đổi giá trị gia tốc thành góc
  int xAng = map(AcX, minVal, maxVal, -90, 90);
  int yAng = map(AcY, minVal, maxVal, -90, 90);
  int zAng = map(AcZ, minVal, maxVal, -90, 90);

  x = RAD_TO_DEG * (atan2(-yAng, -zAng) + PI);
  y = RAD_TO_DEG * (atan2(-xAng, -zAng) + PI);
  z = RAD_TO_DEG * (atan2(-yAng, -xAng) + PI);

  // Tạo payload dưới dạng JSON
  char payload[100];
  snprintf(payload, sizeof(payload), "{\"x\":%.2f,\"y\":%.2f,\"z\":%.2f}", x, y, z);
  // Gửi dữ liệu tới topic "mpu6050/data"
  client.publish("mpu6050/data", payload);

  // In dữ liệu ra màn hình Serial
  Serial.println(payload);

  delay(1000);  // Delay 1s giữa các lần gửi dữ liệu
}
