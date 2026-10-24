#include <board.h>

esp_err_t board_keep_pin_in_sleep(gpio_num_t gpio)
{
    return gpio_sleep_sel_dis(gpio);
}

esp_err_t board_init_rf_switch(void)
{
    const gpio_config_t config = {
        .pin_bit_mask = BIT64(BOARD_RF_SWITCH_ENABLE_GPIO) | BIT64(BOARD_RF_ANTENNA_SELECT_GPIO),
        .mode = GPIO_MODE_OUTPUT,
    };

    esp_err_t err = gpio_config(&config);
    if (err != ESP_OK)
    {
        return err;
    }

    err = gpio_set_level(BOARD_RF_SWITCH_ENABLE_GPIO, 0);
    if (err == ESP_OK)
    {
        err = gpio_set_level(BOARD_RF_ANTENNA_SELECT_GPIO, 0);
    }
    if (err == ESP_OK)
    {
        err = board_keep_pin_in_sleep(BOARD_RF_SWITCH_ENABLE_GPIO);
    }
    if (err == ESP_OK)
    {
        err = board_keep_pin_in_sleep(BOARD_RF_ANTENNA_SELECT_GPIO);
    }
    return err;
}
