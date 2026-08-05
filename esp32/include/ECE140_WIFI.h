#ifndef ECE140_WIFI_h
#define ECE140_WIFI_h

#include <Arduino.h>
#include <WiFi.h>
#include "esp_wpa2.h"
#include "esp_wifi.h"
#include <lwip/dns.h>

/**
 * @brief This is the class to connect to a wifi network.
 *
 * You can either connect to a regular wifi network or a WPA Enterprise network.
 */
class ECE140_WIFI {
public:
  /**
   * @brief Construct a new ECE140_WIFI object
   */
  ECE140_WIFI();

  /**
   * @brief Connect to a regular WiFi network
   *
   * @param ssid The SSID of the WiFi network
   * @param password The password of the WiFi network
   */
  void connectToWiFi(String ssid, String password);

  /**
   * @brief Connect to a WPA Enterprise network
   *
   * @param ssid The SSID of the WiFi network
   * @param username The username for WPA Enterprise
   * @param password The password for WPA Enterprise
   */
  void connectToWPAEnterprise(String ssid, String username, String password);
};

#endif
