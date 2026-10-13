#pragma once

#include <sdkconfig.h>

// The ESP32 platform has no Kconfig option for the product name, so the
// variant's AQS_PRODUCT_NAME reaches the Basic Information cluster through here.
#define CHIP_DEVICE_CONFIG_DEVICE_PRODUCT_NAME CONFIG_AQS_PRODUCT_NAME

// Per message and per report progress lines. Under OTA or subscription traffic
// they outrun the USB console, which then drops output, including the lines
// worth reading. Errors from these modules are still logged.
#define CHIP_CONFIG_LOG_MODULE_ExchangeManager_PROGRESS 0
#define CHIP_CONFIG_LOG_MODULE_InteractionModel_PROGRESS 0
#define CHIP_CONFIG_LOG_MODULE_DataManagement_PROGRESS 0
#define CHIP_CONFIG_LOG_MODULE_Inet_PROGRESS 0
