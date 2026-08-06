#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <Adafruit_AMG88xx.h>
#include <TensorFlowLite_ESP32.h>
#include "tensorflow/lite/micro/all_ops_resolver.h"
#include "tensorflow/lite/micro/micro_error_reporter.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "ECE140_MQTT.h"
#include "ECE140_WIFI.h"
#include "model_data.h"
#include "model_params.h"

ECE140_WIFI wifi;
Adafruit_AMG88xx amg;

const char* ucsdUsername = UCSD_USERNAME;
String ucsdPasswordStorage = String(UCSD_PASSWORD);
const char* ucsdPassword = ucsdPasswordStorage.c_str();
const char* wifiSsid = WIFI_SSID;
const char* nonEnterpriseWifiPassword = NON_ENTERPRISE_WIFI_PASSWORD;
const char* mqttBroker = MQTT_BROKER;
const char* mqttClientId = MQTT_CLIENT_ID;
const char* mqttTopicPrefix = MQTT_TOPIC;

ECE140_MQTT mqtt{String(mqttClientId), String(mqttTopicPrefix), String(mqttBroker)};

constexpr int kTensorArenaSize = 16 * 1024;
alignas(16) uint8_t tensorArena[kTensorArenaSize];

const tflite::Model* model = nullptr;
tflite::MicroInterpreter* interpreter = nullptr;
TfLiteTensor* inputTensor = nullptr;
TfLiteTensor* outputTensor = nullptr;

static bool continuous = false;
static unsigned long lastSendMs = 0;
static const unsigned long CONTINUOUS_INTERVAL_MS = 1000;
static float pixels[64];
static float features[N_FEATURES];

bool setupModel() {
    model = tflite::GetModel(model_tflite);
    if (model->version() != TFLITE_SCHEMA_VERSION) {
        Serial.printf("[TFLite] Schema mismatch: model=%d runtime=%d\n",
                      model->version(), TFLITE_SCHEMA_VERSION);
        return false;
    }

    static tflite::AllOpsResolver resolver;
    static tflite::MicroErrorReporter errorReporter;
    static tflite::MicroInterpreter staticInterpreter(
        model, resolver, tensorArena, kTensorArenaSize, &errorReporter);
    interpreter = &staticInterpreter;

    if (interpreter->AllocateTensors() != kTfLiteOk) {
        Serial.println("[TFLite] Tensor allocation failed");
        return false;
    }

    inputTensor = interpreter->input(0);
    outputTensor = interpreter->output(0);
    if (inputTensor->type != kTfLiteInt8 || outputTensor->type != kTfLiteInt8) {
        Serial.println("[TFLite] Expected INT8 input and output tensors");
        return false;
    }
    if (inputTensor->dims->data[inputTensor->dims->size - 1] != N_FEATURES) {
        Serial.println("[TFLite] Feature-count mismatch");
        return false;
    }

    Serial.printf("[TFLite] Ready: %d features, %d-byte model\n",
                  N_FEATURES, model_tflite_len);
    return true;
}

int largestHotRegion(float grid[8][8], float threshold) {
    bool visited[8][8] = {};
    int largest = 0;
    int queueRows[64];
    int queueColumns[64];

    for (int row = 0; row < 8; row++) {
        for (int column = 0; column < 8; column++) {
            if (visited[row][column] || grid[row][column] <= threshold) continue;

            int head = 0;
            int tail = 0;
            int size = 0;
            queueRows[tail] = row;
            queueColumns[tail++] = column;
            visited[row][column] = true;

            while (head < tail) {
                int currentRow = queueRows[head];
                int currentColumn = queueColumns[head++];
                size++;
                const int rowDelta[] = {-1, 1, 0, 0};
                const int columnDelta[] = {0, 0, -1, 1};
                for (int direction = 0; direction < 4; direction++) {
                    int nextRow = currentRow + rowDelta[direction];
                    int nextColumn = currentColumn + columnDelta[direction];
                    if (nextRow < 0 || nextRow >= 8 || nextColumn < 0 || nextColumn >= 8) continue;
                    if (visited[nextRow][nextColumn] || grid[nextRow][nextColumn] <= threshold) continue;
                    visited[nextRow][nextColumn] = true;
                    queueRows[tail] = nextRow;
                    queueColumns[tail++] = nextColumn;
                }
            }
            if (size > largest) largest = size;
        }
    }
    return largest;
}

void computeFeatures(const float* rawPixels, float* output) {
    float grid[8][8];
    float sorted[64];
    float mean = 0.0f;
    for (int index = 0; index < 64; index++) {
        grid[index / 8][index % 8] = rawPixels[index];
        sorted[index] = rawPixels[index];
        mean += rawPixels[index];
    }
    mean /= 64.0f;

    for (int index = 1; index < 64; index++) {
        float key = sorted[index];
        int previous = index - 1;
        while (previous >= 0 && sorted[previous] > key) {
            sorted[previous + 1] = sorted[previous];
            previous--;
        }
        sorted[previous + 1] = key;
    }

    float median = (sorted[31] + sorted[32]) / 2.0f;
    float threshold = median + 3.0f;
    float variance = 0.0f;
    float minimum = rawPixels[0];
    float maximum = rawPixels[0];
    int aboveThree = 0;
    int aboveFive = 0;
    float hotRowSum = 0.0f;
    float hotColumnSum = 0.0f;

    for (int index = 0; index < 64; index++) {
        float centered = rawPixels[index] - mean;
        variance += centered * centered;
        minimum = min(minimum, rawPixels[index]);
        maximum = max(maximum, rawPixels[index]);
        if (rawPixels[index] > threshold) {
            aboveThree++;
            hotRowSum += index / 8;
            hotColumnSum += index % 8;
        }
        if (rawPixels[index] > median + 5.0f) aboveFive++;
    }

    float standardDeviation = sqrtf(variance / 64.0f);
    if (standardDeviation < 0.1f) standardDeviation = 0.1f;
    for (int index = 0; index < 64; index++) {
        output[index] = (rawPixels[index] - median) / standardDeviation;
    }
    output[64] = maximum;
    output[65] = maximum - minimum;
    output[66] = aboveThree;
    output[67] = aboveFive;

    float horizontalSum = 0.0f;
    float verticalSum = 0.0f;
    for (int row = 0; row < 8; row++) {
        for (int column = 0; column < 7; column++) {
            horizontalSum += fabsf(grid[row][column + 1] - grid[row][column]);
        }
    }
    for (int row = 0; row < 7; row++) {
        for (int column = 0; column < 8; column++) {
            verticalSum += fabsf(grid[row + 1][column] - grid[row][column]);
        }
    }
    output[68] = (horizontalSum / 56.0f + verticalSum / 56.0f) / 2.0f;
    output[69] = largestHotRegion(grid, threshold);

    float quadrantMeans[4] = {};
    for (int row = 0; row < 8; row++) {
        for (int column = 0; column < 8; column++) {
            int quadrant = (row >= 4 ? 2 : 0) + (column >= 4 ? 1 : 0);
            quadrantMeans[quadrant] += grid[row][column] / 16.0f;
        }
    }
    float quadrantMean = 0.0f;
    for (float value : quadrantMeans) quadrantMean += value / 4.0f;
    float quadrantVariance = 0.0f;
    for (float value : quadrantMeans) quadrantVariance += powf(value - quadrantMean, 2) / 4.0f;
    output[70] = quadrantVariance;

    float centerSum = 0.0f;
    float edgeSum = 0.0f;
    int edgeCount = 0;
    for (int row = 0; row < 8; row++) {
        for (int column = 0; column < 8; column++) {
            if (row >= 2 && row < 6 && column >= 2 && column < 6) {
                centerSum += grid[row][column];
            } else {
                edgeSum += grid[row][column];
                edgeCount++;
            }
        }
    }
    output[71] = centerSum / 16.0f - edgeSum / edgeCount;

    float rowMaximums[8];
    float columnMaximums[8];
    float rowMaximumMean = 0.0f;
    float columnMaximumMean = 0.0f;
    for (int row = 0; row < 8; row++) {
        rowMaximums[row] = grid[row][0];
        for (int column = 1; column < 8; column++) rowMaximums[row] = max(rowMaximums[row], grid[row][column]);
        rowMaximumMean += rowMaximums[row] / 8.0f;
    }
    for (int column = 0; column < 8; column++) {
        columnMaximums[column] = grid[0][column];
        for (int row = 1; row < 8; row++) columnMaximums[column] = max(columnMaximums[column], grid[row][column]);
        columnMaximumMean += columnMaximums[column] / 8.0f;
    }
    float rowVariance = 0.0f;
    float columnVariance = 0.0f;
    for (int index = 0; index < 8; index++) {
        rowVariance += powf(rowMaximums[index] - rowMaximumMean, 2) / 8.0f;
        columnVariance += powf(columnMaximums[index] - columnMaximumMean, 2) / 8.0f;
    }
    output[72] = sqrtf(rowVariance);
    output[73] = sqrtf(columnVariance);

    if (aboveThree > 0) {
        float hotRow = hotRowSum / aboveThree;
        float hotColumn = hotColumnSum / aboveThree;
        output[74] = hypotf(hotRow - 3.5f, hotColumn - 3.5f);
    } else {
        output[74] = 0.0f;
    }
    output[75] = aboveThree / 64.0f;

    for (int index = 0; index < N_FEATURES; index++) {
        output[index] = (output[index] - SCALER_MEAN[index]) / SCALER_SCALE[index];
    }
}

bool predictPresence(const float* scaledFeatures, float* confidence) {
    const float inputScale = inputTensor->params.scale;
    const int inputZeroPoint = inputTensor->params.zero_point;
    for (int index = 0; index < N_FEATURES; index++) {
        int quantized = roundf(scaledFeatures[index] / inputScale) + inputZeroPoint;
        inputTensor->data.int8[index] = static_cast<int8_t>(constrain(quantized, -128, 127));
    }

    if (interpreter->Invoke() != kTfLiteOk) {
        Serial.println("[TFLite] Inference failed");
        return false;
    }

    *confidence = (outputTensor->data.int8[0] - outputTensor->params.zero_point)
                  * outputTensor->params.scale;
    *confidence = constrain(*confidence, 0.0f, 1.0f);
    return true;
}

String buildPayload(const float* frame, float thermistor, const char* prediction, float confidence) {
    String payload = "{";
    payload += "\"mac_address\":\"" + WiFi.macAddress() + "\",";
    payload += "\"pixels\":[";
    for (int index = 0; index < 64; index++) {
        payload += String(frame[index], 4);
        if (index < 63) payload += ",";
    }
    payload += "],";
    payload += "\"thermistor\":" + String(thermistor, 3) + ",";
    payload += "\"prediction\":\"" + String(prediction) + "\",";
    payload += "\"confidence\":" + String(confidence, 4);
    payload += "}";
    return payload;
}

void sendOneReading() {
    amg.readPixels(pixels);
    computeFeatures(pixels, features);
    float confidence = 0.0f;
    if (!predictPresence(features, &confidence)) return;

    const char* prediction = confidence >= 0.5f ? "PRESENT" : "EMPTY";
    String payload = buildPayload(pixels, amg.readThermistor(), prediction, confidence);
    mqtt.publishMessage("readings", payload);
    Serial.printf("[%s] confidence=%.3f\n", prediction, confidence);
}

void onMqttMessage(char* topic, uint8_t* payload, unsigned int length) {
    String message;
    message.reserve(length + 1);
    for (unsigned int index = 0; index < length; index++) message += static_cast<char>(payload[index]);
    message.trim();
    message.toLowerCase();

    if (message.indexOf("get_one") >= 0) {
        continuous = false;
        sendOneReading();
    } else if (message.indexOf("start_continuous") >= 0) {
        continuous = true;
    } else if (message.indexOf("stop") >= 0) {
        continuous = false;
    }
}

void setup() {
    Serial.begin(115200);
    delay(2000);

    if (strlen(nonEnterpriseWifiPassword) < 2) {
        wifi.connectToWPAEnterprise(wifiSsid, ucsdUsername, ucsdPassword);
    } else {
        wifi.connectToWiFi(wifiSsid, nonEnterpriseWifiPassword);
    }

    Wire.begin();
    if (!amg.begin()) {
        Serial.println("[AMG8833] Sensor not detected");
        while (true) delay(1000);
    }
    if (!setupModel()) {
        while (true) delay(1000);
    }

    mqtt.connectToBroker(1883);
    mqtt.setCallback(onMqttMessage);
    mqtt.subscribeTopic("command");
}

void loop() {
    mqtt.loop();

    static unsigned long lastSubscriptionCheck = 0;
    if (millis() - lastSubscriptionCheck > 5000) {
        lastSubscriptionCheck = millis();
        mqtt.setCallback(onMqttMessage);
        mqtt.subscribeTopic("command");
    }

    if (continuous && millis() - lastSendMs >= CONTINUOUS_INTERVAL_MS) {
        lastSendMs = millis();
        sendOneReading();
    }
    delay(5);
}
