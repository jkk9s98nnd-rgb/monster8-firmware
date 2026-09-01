/**
 * Custom LED menu for Mark's MKS Mini12864 V3
 * Adds independent control of the three addressable LEDs and persistent save.
 */

#include "../../inc/MarlinConfigPre.h"

#if HAS_MARLINUI_MENU && ANY(LED_CONTROL_MENU, CASE_LIGHT_MENU)

#include "menu_item.h"

#if ENABLED(LED_CONTROL_MENU)
  #include "../../feature/leds/leds.h"
  #include "../../feature/leds/mini12864_individual_leds.h"
#endif

#if ENABLED(CASE_LIGHT_MENU)
  #include "../../feature/caselight.h"
#endif

#if ENABLED(LED_CONTROL_MENU) && ENABLED(MKS_MINI_12864_V3) && ENABLED(NEOPIXEL_LED)

static void led_save() {
  ui.completion_feedback(mini12864IndividualLEDs.save());
}

static void led_reload() {
  ui.completion_feedback(mini12864IndividualLEDs.load());
}

static void led_all_white() {
  mini12864IndividualLEDs.defaults();
  mini12864IndividualLEDs.apply_all();
}

static void led_all_off() {
  for (uint8_t i = 0; i < 3; ++i)
    mini12864IndividualLEDs.channel[i].brightness = 0;
  mini12864IndividualLEDs.apply_all();
}

static void menu_led_0() {
  START_MENU();
  BACK_ITEM(MSG_LED_CONTROL);
  STATIC_ITEM_F(F("LED 1"), SS_DEFAULT|SS_INVERT);
  EDIT_ITEM_F(uint8, F("Red"),        &mini12864IndividualLEDs.channel[0].r,          0, 255, Mini12864IndividualLEDs::update0, true);
  EDIT_ITEM_F(uint8, F("Green"),      &mini12864IndividualLEDs.channel[0].g,          0, 255, Mini12864IndividualLEDs::update0, true);
  EDIT_ITEM_F(uint8, F("Blue"),       &mini12864IndividualLEDs.channel[0].b,          0, 255, Mini12864IndividualLEDs::update0, true);
  EDIT_ITEM_F(uint8, F("Brightness"), &mini12864IndividualLEDs.channel[0].brightness, 0, 255, Mini12864IndividualLEDs::update0, true);
  END_MENU();
}

static void menu_led_1() {
  START_MENU();
  BACK_ITEM(MSG_LED_CONTROL);
  STATIC_ITEM_F(F("LED 2"), SS_DEFAULT|SS_INVERT);
  EDIT_ITEM_F(uint8, F("Red"),        &mini12864IndividualLEDs.channel[1].r,          0, 255, Mini12864IndividualLEDs::update1, true);
  EDIT_ITEM_F(uint8, F("Green"),      &mini12864IndividualLEDs.channel[1].g,          0, 255, Mini12864IndividualLEDs::update1, true);
  EDIT_ITEM_F(uint8, F("Blue"),       &mini12864IndividualLEDs.channel[1].b,          0, 255, Mini12864IndividualLEDs::update1, true);
  EDIT_ITEM_F(uint8, F("Brightness"), &mini12864IndividualLEDs.channel[1].brightness, 0, 255, Mini12864IndividualLEDs::update1, true);
  END_MENU();
}

static void menu_led_2() {
  START_MENU();
  BACK_ITEM(MSG_LED_CONTROL);
  STATIC_ITEM_F(F("LED 3"), SS_DEFAULT|SS_INVERT);
  EDIT_ITEM_F(uint8, F("Red"),        &mini12864IndividualLEDs.channel[2].r,          0, 255, Mini12864IndividualLEDs::update2, true);
  EDIT_ITEM_F(uint8, F("Green"),      &mini12864IndividualLEDs.channel[2].g,          0, 255, Mini12864IndividualLEDs::update2, true);
  EDIT_ITEM_F(uint8, F("Blue"),       &mini12864IndividualLEDs.channel[2].b,          0, 255, Mini12864IndividualLEDs::update2, true);
  EDIT_ITEM_F(uint8, F("Brightness"), &mini12864IndividualLEDs.channel[2].brightness, 0, 255, Mini12864IndividualLEDs::update2, true);
  END_MENU();
}

static void menu_individual_leds() {
  START_MENU();
  BACK_ITEM(MSG_LED_CONTROL);
  SUBMENU_F(F("LED 1"), menu_led_0);
  SUBMENU_F(F("LED 2"), menu_led_1);
  SUBMENU_F(F("LED 3"), menu_led_2);
  ACTION_ITEM_F(F("All White"), led_all_white);
  ACTION_ITEM_F(F("All Off"), led_all_off);
  ACTION_ITEM_F(F("SAVE LED SETTINGS"), led_save);
  ACTION_ITEM_F(F("Reload Saved"), led_reload);
  END_MENU();
}

#endif

#if ENABLED(CASE_LIGHT_MENU)
  #define CASELIGHT_TOGGLE_ITEM() EDIT_ITEM(bool, MSG_CASE_LIGHT, (bool*)&caselight.on, caselight.update_enabled)

  #if CASELIGHT_USES_BRIGHTNESS
    void menu_case_light() {
      START_MENU();
      BACK_ITEM(MSG_CONFIGURATION);
      EDIT_ITEM(percent, MSG_CASE_LIGHT_BRIGHTNESS, &caselight.brightness, 0, 255, caselight.update_brightness, true);
      CASELIGHT_TOGGLE_ITEM();
      END_MENU();
    }
  #endif
#endif

void menu_led() {
  START_MENU();
  BACK_ITEM(MSG_MAIN_MENU);

  #if ENABLED(LED_CONTROL_MENU)
    #if ENABLED(MKS_MINI_12864_V3) && ENABLED(NEOPIXEL_LED)
      SUBMENU_F(F("Individual LEDs"), menu_individual_leds);
      ACTION_ITEM_F(F("SAVE LED SETTINGS"), led_save);
    #else
      SUBMENU(MSG_CUSTOM_LEDS, menu_led_custom);
    #endif
  #endif

  #if ENABLED(CASE_LIGHT_MENU)
    #if CASELIGHT_USES_BRIGHTNESS
      if (caselight.has_brightness())
        SUBMENU(MSG_CASE_LIGHT, menu_case_light);
      else
    #endif
        CASELIGHT_TOGGLE_ITEM();
  #endif

  END_MENU();
}

#endif
