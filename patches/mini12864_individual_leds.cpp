#include "mini12864_individual_leds.h"

#if ENABLED(MKS_MINI_12864_V3) && ENABLED(NEOPIXEL_LED)

#include "leds.h"
#include "../../HAL/shared/eeprom_api.h"
#include <stddef.h>
#include <string.h>

Mini12864LedChannel Mini12864IndividualLEDs::channel[3] = {
  { 255, 255, 255, 255 },
  { 255, 255, 255, 255 },
  { 255, 255, 255, 255 }
};

Mini12864IndividualLEDs mini12864IndividualLEDs;

namespace {
  constexpr uint32_t LED_STORE_MAGIC = 0x4D4B4C44UL; // "MKLD"
  constexpr uint8_t LED_STORE_VERSION = 1;
  constexpr size_t LED_STORE_RESERVED_BYTES = 64;

  #pragma pack(push, 1)
  struct StoredLEDSettings {
    uint32_t magic;
    uint8_t version;
    Mini12864LedChannel channel[3];
    uint16_t checksum;
  };
  #pragma pack(pop)

  uint8_t scaled_component(const uint8_t value, const uint8_t brightness) {
    return uint8_t((uint16_t(value) * uint16_t(brightness) + 127U) / 255U);
  }

  uint16_t calc_checksum(const StoredLEDSettings &s) {
    const uint8_t *p = reinterpret_cast<const uint8_t *>(&s);
    uint16_t c = 0x6D3A;
    for (size_t i = 0; i < offsetof(StoredLEDSettings, checksum); ++i) {
      c = uint16_t((c << 5) | (c >> 11));
      c ^= p[i];
    }
    return c;
  }

  int storage_address() {
    const size_t cap = persistentStore.capacity();
    if (cap < LED_STORE_RESERVED_BYTES) return -1;
    return int(cap - LED_STORE_RESERVED_BYTES);
  }

  void set_pixel(const uint8_t index) {
    if (index >= 3 || index >= neo.pixels()) return;
    const Mini12864LedChannel &c = Mini12864IndividualLEDs::channel[index];
    const uint8_t r = scaled_component(c.r, c.brightness),
                  g = scaled_component(c.g, c.brightness),
                  b = scaled_component(c.b, c.brightness);
    neo.set_pixel_color(index, neo.Color(r, g, b));
  }
}

void Mini12864IndividualLEDs::defaults() {
  for (uint8_t i = 0; i < 3; ++i)
    channel[i] = { 255, 255, 255, 255 };
}

void Mini12864IndividualLEDs::apply(const uint8_t index) {
  neo.set_brightness(255);
  set_pixel(index);
  neo.show();
}

void Mini12864IndividualLEDs::apply_all() {
  neo.set_brightness(255);
  for (uint8_t i = 0; i < 3; ++i) set_pixel(i);
  neo.show();
}

void Mini12864IndividualLEDs::update0() { apply(0); }
void Mini12864IndividualLEDs::update1() { apply(1); }
void Mini12864IndividualLEDs::update2() { apply(2); }

bool Mini12864IndividualLEDs::save() {
  const int pos = storage_address();
  if (pos < 0 || !persistentStore.access_start()) return false;

  StoredLEDSettings s;
  s.magic = LED_STORE_MAGIC;
  s.version = LED_STORE_VERSION;
  memcpy(s.channel, channel, sizeof(channel));
  s.checksum = calc_checksum(s);

  const bool write_error = persistentStore.write_data(pos, reinterpret_cast<const uint8_t *>(&s), sizeof(s));
  persistentStore.access_finish();
  return !write_error;
}

bool Mini12864IndividualLEDs::load() {
  const int pos = storage_address();
  if (pos < 0 || !persistentStore.access_start()) {
    defaults();
    apply_all();
    return false;
  }

  StoredLEDSettings s{};
  const bool read_error = persistentStore.read_data(pos, reinterpret_cast<uint8_t *>(&s), sizeof(s));
  persistentStore.access_finish();

  if (read_error || s.magic != LED_STORE_MAGIC || s.version != LED_STORE_VERSION || s.checksum != calc_checksum(s)) {
    defaults();
    apply_all();
    return false;
  }

  memcpy(channel, s.channel, sizeof(channel));
  apply_all();
  return true;
}

#endif
