#ifndef BOARD_H
#define BOARD_H

#include <driver/gpio.h>

#ifdef __cplusplus
extern "C" {
#endif

/** @brief Seeed XIAO ESP32-C6 pin assignments used by the carrier PCB */
#define BOARD_I2C_SDA_GPIO GPIO_NUM_22 /* D4 */
#define BOARD_I2C_SCL_GPIO GPIO_NUM_23 /* D5 */
#define BOARD_USER_LED_GPIO GPIO_NUM_15
#define BOARD_BOOT_BUTTON_GPIO GPIO_NUM_9
#define BOARD_RF_SWITCH_ENABLE_GPIO GPIO_NUM_3
#define BOARD_RF_ANTENNA_SELECT_GPIO GPIO_NUM_14

/**
 * @brief Keep a pin's configuration and level through light sleep
 *
 * By default every GPIO is switched to an isolated state while the chip light
 * sleeps. Pins that must hold a level across sleep - the RF switch, the LED,
 * the I2C lines, the button pull-up - opt out with this.
 *
 * @param gpio Pin to keep as configured
 * @return esp_err_t, ESP_OK if ok
 */
esp_err_t board_keep_pin_in_sleep(gpio_num_t gpio);

/**
 * @brief Route the radio to the onboard ceramic antenna
 *
 * The XIAO ESP32-C6 has an RF switch between the onboard and the U.FL antenna,
 * and it is unpowered out of reset. Must run before the 802.15.4 radio starts.
 *
 * @return esp_err_t, ESP_OK if ok
 */
esp_err_t board_init_rf_switch(void);

#ifdef __cplusplus
}
#endif

#endif // BOARD_H
