#pragma once

#include "esphome/core/component.h"
#include "esphome/core/hal.h"
#include "esphome/components/one_wire/one_wire.h"

namespace esphome {
namespace dallas_gpio {

class DallasGPIOComponent : public PollingComponent, public one_wire::OneWireDevice {
 public:
  DallasGPIOComponent() = default;

  /// Check i2c availability and setup masks
  void setup() override;
  /// Poll for input changes periodically
  void loop() override;
  void update() override;
  /// Helper function to read the value of a pin.
  bool digital_read(uint8_t pin);
  /// Helper function to write the value of a pin.
  void digital_write(uint8_t pin, bool value);
  /// Helper function to set the pin mode of a pin.
  void pin_mode(uint8_t pin, gpio::Flags flags);

  // float get_setup_priority() const override;

  // float get_loop_priority() const override;

  void dump_config() override;

  void set_pin_count(size_t pin_count) { this->pin_count_ = pin_count; }

 protected:
  bool read_inputs_();

  bool write_register_(uint8_t reg, uint16_t value);
  uint16_t calculate_crc16_(const uint8_t *data, size_t length);

  /// number of bits the expander has
  size_t pin_count_{8};
  /// width of registers
  size_t reg_width_{1};
  /// Mask for the pin config - 1 means OUTPUT, 0 means INPUT
  uint16_t config_mask_{0x00};
  /// The mask to write as output state - 1 means HIGH, 0 means LOW
  uint16_t output_mask_{0x00};
  /// The state of the actual input pin states - 1 means HIGH, 0 means LOW
  uint16_t input_mask_{0x00};
  /// Flags to check if read previously during this loop
  bool was_previously_read_{false};

  bool setup_done_{false};
};

/// Helper class to expose a PCA9554 pin as an internal input GPIO pin.
class DallasGPIOPin : public GPIOPin {
 public:
  void setup() override;
  void pin_mode(gpio::Flags flags) override;
  bool digital_read() override;
  void digital_write(bool value) override;
  std::string dump_summary() const override;

  void set_parent(DallasGPIOComponent *parent) { parent_ = parent; }
  void set_pin(uint8_t pin) { pin_ = pin; }
  void set_inverted(bool inverted) { inverted_ = inverted; }
  void set_flags(gpio::Flags flags) { flags_ = flags; }

  gpio::Flags get_flags() const override { return this->flags_; }

 protected:
  DallasGPIOComponent *parent_;
  uint8_t pin_;
  bool inverted_;
  gpio::Flags flags_;
};

}  // namespace dallas_gpio
}  // namespace esphome
