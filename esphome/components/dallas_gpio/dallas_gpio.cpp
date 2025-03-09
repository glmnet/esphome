#include "dallas_gpio.h"
#include "esphome/core/log.h"

namespace esphome {
namespace dallas_gpio {

const uint8_t DALLAS_DS2408_COMMAND_READ_PIO_REGISTERS = 0xF0;
const uint8_t DALLAS_DS2408_COMMAND_CHANNEL_ACCESS_WRITE = 0x5A;
const uint8_t DALLAS_DS2408_COMMAND_CHANNEL_ACCESS_READ = 0xF5;
const uint8_t DALLAS_DS2408_COMMAND_PIO_ACK_SUCCESS = 0xAA;
const char *const TAG = "dallas_gpio";

void DallasGPIOComponent::setup() {
  ESP_LOGCONFIG(TAG, "Setting up Dallas GPIO...");
  if (!this->check_address_())
    return;
  this->setup_done_ = true;
}

void DallasGPIOComponent::loop() {
  // The read_inputs_() method will cache the input values from the chip.
  // this->read_inputs_();
  // Clear all the previously read flags.
  this->was_previously_read_ = false;
}

void DallasGPIOComponent::update() {
  // The read_inputs_() method will cache the input values from the chip.
  // this->read_inputs_();
  // Clear all the previously read flags.
  //  this->was_previously_read_ = false;
}

void DallasGPIOComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "Dallas GPIO:");
  if (this->address_ == 0) {
    ESP_LOGW(TAG, "  Unable to select an address");
    return;
  }
  LOG_ONE_WIRE_DEVICE(this);
}

bool DallasGPIOComponent::digital_read(uint8_t pin) {
  if (!this->setup_done_)
    return false;
  // Note: We want to try and avoid doing any Dallas bus read transactions here
  // to conserve Dallas bus bandwidth. So what we do is check to see if we
  // have seen a read during the time esphome is running this loop. If we have,
  // we do an Dallas bus transaction to get the latest value. If we haven't
  // we return a cached value which was read at the time loop() was called.
  if (!this->was_previously_read_)
    this->read_inputs_();  // Force a read of a new value
  // Indicate we saw a read request for this pin in case a
  // read happens later in the same loop.
  this->was_previously_read_ = true;
  return this->input_mask_ & (1 << pin);
}

void DallasGPIOComponent::digital_write(uint8_t pin, bool value) {
  if (value) {
    this->output_mask_ |= (1 << pin);
  } else {
    this->output_mask_ &= ~(1 << pin);
  }
  // this->write_register_(OUTPUT_REG, this->output_mask_);
}

void DallasGPIOComponent::pin_mode(uint8_t pin, gpio::Flags flags) {
  if (flags == gpio::FLAG_INPUT) {
    // Clear mode mask bit
    this->config_mask_ &= ~(1 << pin);
  } else if (flags == gpio::FLAG_OUTPUT) {
    // Set mode mask bit
    this->config_mask_ |= 1 << pin;
  }
  // this->write_register_(CONFIG_REG, ~this->config_mask_);
}

// bool DallasGPIOComponent::read_inputs_() {
//   // Ref Dallas Semiconductor MAXIM DS2408.pdf
//   // PIO Logic State Register Bitmap
//   // ADDR  b7  b6  b5  b4  b3  b2  b1  b0
//   // 0x88  P7  P6  P5  P4  P3  P2  P1  P0
//   // PIO Output Latch State Register Bitmap
//   // ADDR  b7  b6  b5  b4  b3  b2  b1  b0
//   // 0x89  PL7 PL6 PL5 PL4 PL3 PL2 PL1 PL0
//   constexpr uint16_t target_address = 0x0088;
//   uint8_t data[8];
//   uint16_t crc_received = 0;

//   if (!this->bus_->reset()) {
//     ESP_LOGW(TAG, "Failed to reset One-Wire bus.");
//     this->status_set_warning();
//     return false;
//   }
//   {
//     InterruptLock lock;
//     this->send_command_(DALLAS_DS2408_COMMAND_READ_PIO_REGISTERS);
//     // LSB of the address to read from
//     this->bus_->write8(target_address & 0xFF);  // LSB
//     // MSB of the address to read from
//     this->bus_->write8((target_address >> 8) & 0xFF);  // MSB
//     for (unsigned char &i : data) {
//       i = this->bus_->read8();
//     }

//     crc_received = ~(this->bus_->read8() | (this->bus_->read8() << 8));
//   }

//   uint8_t crc_input[11];
//   crc_input[0] = DALLAS_DS2408_COMMAND_READ_PIO_REGISTERS;
//   crc_input[1] = target_address & 0xFF;
//   crc_input[2] = (target_address >> 8) & 0xFF;
//   memcpy(&crc_input[3], data, 8);  // Copy data to CRC table
//   uint16_t calculated_crc = crc16(crc_input, 11, 0);

//   if (crc_received != calculated_crc) {
//     ESP_LOGW(TAG,
//              "CRC check failed: received=0x%04X, expected=0x%04X "
//              "data=0x%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X",
//              crc_received, calculated_crc, crc_input[0], crc_input[1], crc_input[2], crc_input[3], crc_input[4],
//              crc_input[5], crc_input[6], crc_input[7], crc_input[8], crc_input[9], crc_input[10]);
//     return false;  // CRC invalid
//   }

//   this->input_mask_ = data[0];

//   return true;
// }

bool DallasGPIOComponent::read_inputs_() {
  // Ref Dallas Semiconductor MAXIM DS2408.pdf
  // PIO Logic State Register Bitmap
  // ADDR  b7  b6  b5  b4  b3  b2  b1  b0
  // 0x88  P7  P6  P5  P4  P3  P2  P1  P0
  // PIO Output Latch State Register Bitmap
  // ADDR  b7  b6  b5  b4  b3  b2  b1  b0
  // 0x89  PL7 PL6 PL5 PL4 PL3 PL2 PL1 PL0
  constexpr uint16_t target_address = 0x0088;
  uint8_t data[6];
  uint16_t crc_received = 0;

  if (!this->bus_->reset()) {
    ESP_LOGW(TAG, "Failed to reset One-Wire bus.");
    this->status_set_warning();
    return false;
  }
  {
    InterruptLock lock;
    this->send_command_(DALLAS_DS2408_COMMAND_CHANNEL_ACCESS_READ);
    for (unsigned char &i : data) {
      i = this->bus_->read8();
    }
  }
  crc_received = ~(data[4] | (data[5] << 8));

  uint8_t crc_input[5];
  crc_input[0] = DALLAS_DS2408_COMMAND_CHANNEL_ACCESS_READ;
  memcpy(&crc_input[1], data, 4);  // Copy data to CRC table
  uint16_t calculated_crc = crc16(crc_input, 5, 0);

  if (crc_received != calculated_crc) {
    ESP_LOGW(TAG,
             "CRC check failed: received=0x%04X, expected=0x%04X "
             "data=0x%02X%02X%02X%02X%02X cheksum %02X%02X",
             crc_received, calculated_crc, DALLAS_DS2408_COMMAND_CHANNEL_ACCESS_READ, data[0], data[1], data[2],
             data[3], data[4], data[5]);
    return false;  // CRC invalid
  }

  this->input_mask_ = data[0];

  return true;
}

bool DallasGPIOComponent::write_register_(uint8_t reg, uint16_t value) { return true; }

// float DallasGPIOComponent::get_setup_priority() const { return setup_priority::IO; }

// // Run our loop() method very early in the loop, so that we cache read values before
// // before other components call our digital_read() method.
// float DallasGPIOComponent::get_loop_priority() const { return 9.0f; }  // Just after WIFI

void DallasGPIOPin::setup() { pin_mode(flags_); }
void DallasGPIOPin::pin_mode(gpio::Flags flags) { this->parent_->pin_mode(this->pin_, flags); }
bool DallasGPIOPin::digital_read() { return this->parent_->digital_read(this->pin_) != this->inverted_; }
void DallasGPIOPin::digital_write(bool value) { this->parent_->digital_write(this->pin_, value != this->inverted_); }
std::string DallasGPIOPin::dump_summary() const {
  char buffer[32];
  snprintf(buffer, sizeof(buffer), "%u via DallasGPIO", pin_);
  return buffer;
}

}  // namespace dallas_gpio
}  // namespace esphome
