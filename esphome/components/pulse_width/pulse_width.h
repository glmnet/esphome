#pragma once

#include "esphome/core/component.h"
#include "esphome/core/esphal.h"
#include "esphome/components/sensor/sensor.h"

namespace esphome {
namespace pulse_width {

/// Store data in a class that doesn't use multiple-inheritance (vtables in flash)
class PulseWidthSensorStore {
 public:
  void setup(GPIOPin *pin) {
    pin->setup();
    this->pin_ = pin->to_isr();
    this->last_rise_ = micros();
    pin->attach_interrupt(&PulseWidthSensorStore::gpio_intr, this, CHANGE);
  }
  static void gpio_intr(PulseWidthSensorStore *arg);
  uint32_t get_pulse_width_us() const { return this->last_width_; }
  float get_pulse_width_s() const { return this->last_width_ / 1e6f; }

 protected:
  ISRInternalGPIOPin *pin_;
  volatile uint32_t last_width_{0};
  volatile uint32_t last_rise_{0};
};

class PulseWidthSensor : public sensor::PollingSensorComponent {
 public:
  PulseWidthSensor(const std::string &name, uint32_t update_interval) : PollingSensorComponent(name, update_interval) {}
  void set_pin(GPIOPin *pin) { pin_ = pin; }
  void setup() override { this->store_.setup(this->pin_); }
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }
  void update() override;

 protected:
  PulseWidthSensorStore store_;
  GPIOPin *pin_;
};

}  // namespace pulse_width
}  // namespace esphome
