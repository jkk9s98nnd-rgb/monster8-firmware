#pragma once

#include "../../inc/MarlinConfig.h"

#if ENABLED(MKS_MINI_12864_V3) && ENABLED(NEOPIXEL_LED)

#include <stdint.h>

struct Mini12864LedChannel {
  uint8_t r, g, b, brightness;
};

class Mini12864IndividualLEDs {
public:
  static Mini12864LedChannel channel[3];

  static void defaults();
  static void apply(const uint8_t index);
  static void apply_all();
  static void update0();
  static void update1();
  static void update2();
  static bool save();
  static bool load();
};

extern Mini12864IndividualLEDs mini12864IndividualLEDs;

#endif
