#ifndef ECE140_MQTT_h
#define ECE140_MQTT_h

#include <Arduino.h>
#include <PubSubClient.h>
#include <WiFi.h>

/**
 * @brief This is the class to handle MQTT communications with a public broker.
 *
 * This class needs to be initialized with client ID and topic prefix.
 * These parameters will be used for MQTT connection and message publishing.
 */
class ECE140_MQTT {
public:
    /**
     * @brief Construct a new ECE140_MQTT object
     *
     * @param clientId Unique identifier for this MQTT client
     * @param topicPrefix Prefix for all topics published by this client
     */
    ECE140_MQTT(String clientId, String topicPrefix);

    /**
     * @brief Connect to the MQTT broker
     *
     * @param port The port number (default: 1883 for non-TLS)
     * @return true if connection successful
     * @return false if connection failed
     */
    bool connectToBroker(int port = 1883);

    /**
     * @brief Publish a message to a specific topic
     *
     * @param subtopic The subtopic to publish to (will be appended to topicPrefix)
     * @param message The message to publish
     * @return true if publish successful
     * @return false if publish failed
     */
    bool publishMessage(String subtopic, String message);

    /**
     * @brief Subscribe to a specific topic
     *
     * @param subtopic The subtopic to subscribe to
     * @return true if subscription successful
     * @return false if subscription failed
     */
    bool subscribeTopic(String subtopic);

    /**
     * @brief Set callback for receiving messages
     *
     * @param callback Function to be called when message is received
     */
    void setCallback(void (*callback)(char*, uint8_t*, unsigned int));

    /**
     * @brief Handle MQTT loop
     * Must be called regularly to maintain connection and process messages
     */
    void loop();

private:
    WiFiClient _wifiClient;
    PubSubClient* _mqttClient;
    String _clientId;
    String _topicPrefix;
    const char* _broker = "broker.emqx.io";
    bool _isTLS;

    void _setupMQTTClient(int port);
};

#endif
