from esphome import pins
import esphome.codegen as cg
from esphome.components import one_wire
import esphome.config_validation as cv
from esphome.const import (
    CONF_ID,
    CONF_INPUT,
    CONF_INVERTED,
    CONF_MODE,
    CONF_NUMBER,
    CONF_OUTPUT,
)

CODEOWNERS = ["@glmnet"]
DEPENDENCIES = ["one_wire"]
MULTI_CONF = True

dallas_gpio_ns = cg.esphome_ns.namespace("dallas_gpio")

DallasGPIOComponent = dallas_gpio_ns.class_(
    "DallasGPIOComponent", cg.PollingComponent, one_wire.OneWireDevice
)
DallasGPIOPin = dallas_gpio_ns.class_(
    "DallasGPIOPin", cg.GPIOPin, cg.Parented.template(DallasGPIOComponent)
)

CONF_DALLAS_GPIO = "dallas_gpio"
CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.Required(CONF_ID): cv.declare_id(DallasGPIOComponent),
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
    .extend(cv.polling_component_schema("60s"))
    .extend(one_wire.one_wire_device_schema())
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await one_wire.register_one_wire_device(var, config)


def validate_mode(value):
    if not (value[CONF_INPUT] or value[CONF_OUTPUT]):
        raise cv.Invalid("Mode must be either input or output")
    if value[CONF_INPUT] and value[CONF_OUTPUT]:
        raise cv.Invalid("Mode must be either input or output")
    return value


DALLA_GPIO_PIN_SCHEMA = pins.gpio_base_schema(
    DallasGPIOPin,
    cv.int_range(min=0, max=7),
    modes=[CONF_INPUT, CONF_OUTPUT],
    mode_validator=validate_mode,
).extend(
    {
        cv.Required(CONF_DALLAS_GPIO): cv.use_id(DallasGPIOComponent),
    }
)


@pins.PIN_SCHEMA_REGISTRY.register(CONF_DALLAS_GPIO, DALLA_GPIO_PIN_SCHEMA)
async def dallas_gpio_pin_to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    parent = await cg.get_variable(config[CONF_DALLAS_GPIO])

    cg.add(var.set_parent(parent))

    num = config[CONF_NUMBER]
    cg.add(var.set_pin(num))
    cg.add(var.set_inverted(config[CONF_INVERTED]))
    cg.add(var.set_flags(pins.gpio_flags_expr(config[CONF_MODE])))
    return var
