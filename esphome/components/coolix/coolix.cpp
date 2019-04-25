#include "coolix.h"
#include "esphome/core/log.h"

namespace esphome {
namespace coolix {

static const char *TAG = "coolix.climate";

const uint32_t COOLIX_OFF = 0xB27BE0;
// On, 25C, Mode: Auto, Fan: Auto, Zone Follow: Off, Sensor Temp: Ignore.
const uint32_t COOLIX_DEFAULT_STATE =  0xB2BFC8; 
const uint32_t COOLIX_DEFAULT_STATE_AUTO_FAN = 0xB21FC8;
const uint8_t COOLIX_COOL = 0b00;
const uint8_t kCoolixDry = 0b01;
const uint8_t kCoolixAuto = 0b10;
const uint8_t COOLIX_HEAT = 0b11;
const uint8_t kCoolixFan = 4;                                 // Synthetic.
const uint32_t COOLIX_MODE_MASK = 0b000000000000000000001100;  // 0xC

// Temperature
const uint8_t COOLIX_TEMP_MIN = 17;  // Celsius
const uint8_t COOLIX_TEMP_MAX = 30;  // Celsius
const uint8_t kCoolixTempRange = COOLIX_TEMP_MAX - COOLIX_TEMP_MIN + 1;
const uint8_t kCoolixFanTempCode = 0b1110;  // Part of Fan Mode.
const uint32_t COOLIX_TEMP_MASK = 0b11110000;
const uint8_t COOLIX_TEMP_MAP[kCoolixTempRange] = {
    0b0000,  // 17C
    0b0001,  // 18c
    0b0011,  // 19C
    0b0010,  // 20C
    0b0110,  // 21C
    0b0111,  // 22C
    0b0101,  // 23C
    0b0100,  // 24C
    0b1100,  // 25C
    0b1101,  // 26C
    0b1001,  // 27C
    0b1000,  // 28C
    0b1010,  // 29C
    0b1011   // 30C
};

// Constants
// Pulse parms are *50-100 for the Mark and *50+100 for the space
// First MARK is the one after the long gap
// pulse parameters in usec
const uint16_t COLLIX_TICK = 560;  // Approximately 21 cycles at 38kHz
const uint16_t COOLIX_BIT_MARKTicks = 1;
const uint16_t COOLIX_BIT_MARK = COOLIX_BIT_MARKTicks * COLLIX_TICK;
const uint16_t COOLIX_ONE_SPACETicks = 3;
const uint16_t COOLIX_ONE_SPACE = COOLIX_ONE_SPACETicks * COLLIX_TICK;
const uint16_t COOLIX_ZERO_SPACETicks = 1;
const uint16_t COOLIX_ZERO_SPACE = COOLIX_ZERO_SPACETicks * COLLIX_TICK;
const uint16_t COOLIX_HEADER_MARK_TICKS = 8;
const uint16_t COOLIX_HEADER_MARK = COOLIX_HEADER_MARK_TICKS * COLLIX_TICK;
const uint16_t COOLIX_HEADER_SPACETicks = 8;
const uint16_t COOLIX_HEADER_SPACE = COOLIX_HEADER_SPACETicks * COLLIX_TICK;
const uint16_t COOLIX_MIN_GAP_TICKS = COOLIX_HEADER_MARK_TICKS + COOLIX_ZERO_SPACETicks;
const uint16_t COOLIX_MIN_GAP = COOLIX_MIN_GAP_TICKS * COLLIX_TICK;

const uint16_t COOLIX_BITS = 24;

climate::ClimateTraits CoolixClimate::traits() {
  auto traits = climate::ClimateTraits();
  traits.set_supports_current_temperature(true);
  traits.set_supports_auto_mode(true);
  traits.set_supports_cool_mode(this->supports_cool_);
  traits.set_supports_heat_mode(this->supports_heat_);
  traits.set_supports_two_point_target_temperature(false);
  traits.set_supports_away(false);
  return traits;
}

void CoolixClimate::setup() {
  // restore set points
  auto restore = this->restore_state_();
  if (restore.has_value()) {
    restore->to_call(this).perform();
  } else {
    // restore from defaults, change_away handles those for us
    this->mode = climate::CLIMATE_MODE_AUTO;
  }
}

void CoolixClimate::control(const climate::ClimateCall &call) {
  if (call.get_mode().has_value())
    this->mode = *call.get_mode();
  if (call.get_target_temperature().has_value())
    this->target_temperature = *call.get_target_temperature();

  this->current_temperature = NAN;
  this->transmit_state_();
  this->publish_state();
}

void CoolixClimate::transmit_state_() {
  uint32_t remote_state;

  switch (this->mode) {
    case climate::CLIMATE_MODE_COOL:
      remote_state = (COOLIX_DEFAULT_STATE & ~COOLIX_MODE_MASK) | (COOLIX_COOL << 2);
      break;
    case climate::CLIMATE_MODE_HEAT:
      remote_state = (COOLIX_DEFAULT_STATE & ~COOLIX_MODE_MASK) | (COOLIX_HEAT << 2);
      break;
    case climate::CLIMATE_MODE_AUTO:
      remote_state = COOLIX_DEFAULT_STATE_AUTO_FAN;
      break;
    case climate::CLIMATE_MODE_OFF:
    default:
      remote_state = COOLIX_OFF;
      break;
  }
  if (this->mode != climate::CLIMATE_MODE_OFF)
  {
    uint8_t temp = std::min((uint8_t)this->target_temperature, COOLIX_TEMP_MAX);
    temp = std::max((uint8_t)this->target_temperature, COOLIX_TEMP_MIN);
    remote_state &= ~COOLIX_TEMP_MASK;  // Clear the old temp.
    remote_state |= (COOLIX_TEMP_MAP[temp - COOLIX_TEMP_MIN] << 4);
  }

  ESP_LOGD(TAG, "Sending coolix code: %u", remote_state);

  auto transmit = this->transmitter_->transmit();
  auto data = transmit.get_data();

  data->set_carrier_frequency(38000);
  uint16_t repeat = 1;
  for (uint16_t r = 0; r <= repeat; r++) {
    // Header
    data->mark(COOLIX_HEADER_MARK);
    data->space(COOLIX_HEADER_SPACE);

    // Data
    //   Break data into byte segments, starting at the Most Significant
    //   Byte. Each byte then being sent normal, then followed inverted.
    for (uint16_t i = 8; i <= COOLIX_BITS; i += 8) {
      // Grab a bytes worth of data.
      uint8_t segment = (remote_state >> (COOLIX_BITS - i)) & 0xFF;
      // Normal
      send_data_(data, COOLIX_BIT_MARK, COOLIX_ONE_SPACE, COOLIX_BIT_MARK,
                 COOLIX_ZERO_SPACE, segment, 8, true);
      // Inverted.
      send_data_(data, COOLIX_BIT_MARK, COOLIX_ONE_SPACE, COOLIX_BIT_MARK,
                 COOLIX_ZERO_SPACE, segment ^ 0xFF, 8, true);
    }

    // Footer
    data->mark(COOLIX_BIT_MARK);
    data->space(COOLIX_MIN_GAP);  // Pause before repeating
  }

  transmit.perform();
}

// Generic method for sending data that is common to most protocols.
// Will send leading or trailing 0's if the nbits is larger than the number
// of bits in data.
//
// Args:
//   onemark:    Nr. of usecs for the led to be pulsed for a '1' bit.
//   onespace:   Nr. of usecs for the led to be fully off for a '1' bit.
//   zeromark:   Nr. of usecs for the led to be pulsed for a '0' bit.
//   zerospace:  Nr. of usecs for the led to be fully off for a '0' bit.
//   data:       The data to be transmitted.
//   nbits:      Nr. of bits of data to be sent.
//   MSBfirst:   Flag for bit transmission order. Defaults to MSB->LSB order.
void CoolixClimate::send_data_(remote_base::RemoteTransmitData *transmit_data, 
                                        uint16_t onemark, uint32_t onespace, uint16_t zeromark,
                                        uint32_t zerospace, uint64_t data, uint16_t nbits,
                                        bool msb_first) {
  if (nbits == 0)  // If we are asked to send nothing, just return.
    return;
  if (msb_first) {  // Send the MSB first.
    // Send 0's until we get down to a bit size we can actually manage.
    while (nbits > sizeof(data) * 8) {
      transmit_data->mark(zeromark);
      transmit_data->space(zerospace);
      nbits--;
    }
    // Send the supplied data.
    for (uint64_t mask = 1ULL << (nbits - 1); mask; mask >>= 1)
      if (data & mask) {  // Send a 1
        transmit_data->mark(onemark);
        transmit_data->space(onespace);
      } else {  // Send a 0
        transmit_data->mark(zeromark);
        transmit_data->space(zerospace);
      }
  } else {  // Send the Least Significant Bit (LSB) first / MSB last.
    for (uint16_t bit = 0; bit < nbits; bit++, data >>= 1)
      if (data & 1) {  // Send a 1
        transmit_data->mark(onemark);
        transmit_data->space(onespace);
      } else {  // Send a 0
        transmit_data->mark(zeromark);
        transmit_data->space(zerospace);
      }
  }
}

}  // namespace climate
}  // namespace esphome
