import esphome.config_validation as cv
import json
import voluptuous as vol

JSC_DESCRIPTION = "description"
JSC_PROPERTIES = "properties"
JSC_ACTION = "action"
SIMPLE_AUTOMATION = "simple_automation"

schema_names = {}
schema_registry = {}
schema_extend_registry = {}
schema_list_registry = {}

automation_schemas = []  # actually only one
conditions = []
actions = []
definitions = {}
base_props = {}


def get_ref(definition):
    return {"$ref": "#/definitions/" + definition}


def add_definition_array_or_single_object(ref):
    return {"anyOf": [
        {
            "type": "array",
            "items": ref
        },
        ref
    ]}


def extended_schema(func):
    def decorate(*args, **kwargs):

        ret = func(*args, **kwargs)
        schema_extend_registry[str(ret)] = args
        return ret
    return decorate


def list_schema(func):
    def decorate(*args, **kwargs):

        ret = func(*args, **kwargs)
        schema_list_registry[str(ret)] = args
        return ret
    return decorate


def automation_schema():
    def decorate(func):
        automation_schemas.append(func)
        return func
    return decorate


def add_core():
    from esphome.core_config import CONFIG_SCHEMA
    base_props["esphome"] = get_jschema("esphome", CONFIG_SCHEMA.schema)


def add_module_schemas(name, module):
    for c in dir(module):
        v = getattr(module, c)
        if isinstance(v, cv.Schema):
            get_jschema(name, v)


def add_components():
    import os
    from esphome.config import CORE_COMPONENTS_PATH
    from esphome.config import get_component
    from esphome.config import get_platform

    dir_names = [d for d in os.listdir(CORE_COMPONENTS_PATH) if
                 not d.startswith('__') and
                 os.path.isdir(os.path.join(CORE_COMPONENTS_PATH, d))]

    for domain in dir_names:
        c = get_component(domain)
        if ((c.config_schema is not None) or c.is_platform_component):
            if c.is_platform_component:
                # this is a platform_component, e.g. binary_sensor
                platform_schema = []
                base_props[domain] = {"type": "array",
                                      "items": {"type": "object",
                                                JSC_PROPERTIES: {
                                                    "platform": {"type": "string"},
                                                    "id": {"type": "string"},
                                                    "name": {"type": "string"}
                                                },
                                                "allOf": platform_schema}}

                if domain == 'sensor':
                    domain = domain
                add_module_schemas(domain, c.module)

                for platform in dir_names:
                    p = get_platform(domain, platform)
                    if (p is not None):
                        # this is a platform element, e.g.
                        #   - platform: gpio
                        schema = get_jschema(platform, p.config_schema, create_return_ref=False)
                        platform_schema.append({
                            "if": {
                                JSC_PROPERTIES: {"platform": {"const": platform}}},
                            "then": schema})

            elif c.config_schema is not None:
                # adds root components which are not platforms, e.g. api: logger:
                if (domain == 'wifi'):
                    domain = domain
                definitions[domain] = get_jschema(domain, c.config_schema)
                schema = get_ref(domain)
                if c.is_multi_conf:
                    schema = add_definition_array_or_single_object(schema)
                if domain in base_props:
                    domain = domain
                base_props[domain] = schema


def get_automation_schema(name, value):
    from esphome.automation import AUTOMATION_SCHEMA

    # get the schema from the automation schema
    schema = value(automation_schema)

    extra_schema = None
    if AUTOMATION_SCHEMA == schema_extend_registry[str(schema)][0]:
        extra_schema = schema_extend_registry[str(schema)][1]

    if extra_schema:
        # add as property
        automation_definition = get_jschema(name, extra_schema)
        extended_key = schema_names[str(extra_schema)]
        # automations can be either
        #   * a single action,
        #   * an array of action,
        #   * an object with automation's schema and a then key
        #        with again a single action or an array of actions

        automation_definition = definitions[extended_key]
        automation_definition[JSC_PROPERTIES]["then"] = add_definition_array_or_single_object(
            get_ref(JSC_ACTION))

    else:
        if SIMPLE_AUTOMATION not in definitions:
            simple_automation = add_definition_array_or_single_object(get_ref(JSC_ACTION))
            simple_automation["anyOf"].append(get_jschema(AUTOMATION_SCHEMA.__module__, AUTOMATION_SCHEMA))

            definitions[schema_names[str(AUTOMATION_SCHEMA)]][JSC_PROPERTIES]["then"] = add_definition_array_or_single_object(
                get_ref(JSC_ACTION))
            definitions[SIMPLE_AUTOMATION] = simple_automation

        return get_ref(SIMPLE_AUTOMATION)

    schema = add_definition_array_or_single_object(get_ref(JSC_ACTION))
    schema["anyOf"].append(get_ref(extended_key))
    return schema


def get_entry(parent_key, value):
    if value in schema_registry:
        entry = schema_registry[value]
    elif str(value) in schema_list_registry:
        entry = {"type": "array", "items": get_jschema(parent_key, schema_list_registry[str(value)])}
    elif value in automation_schemas:
        entry = get_automation_schema(parent_key, value)
    else:
        # everything else just accept string and let ESPHome validate
        entry = default_schema()

    # annotate schema validator info
    entry[JSC_DESCRIPTION] = str(value)
    return entry


def default_schema():
    # Accept anything
    return {"type": ["null", "object", "string", "array", "number"]}


def is_default_schema(schema):
    return schema["type"] == default_schema()["type"]


def get_jschema(path, vschema, create_return_ref=True):
    name = schema_names.get(str(vschema))
    if name:
        return get_ref(name)

    schema = convert_schema(path, vschema)
    if not create_return_ref:
        return schema

    name = "schema_" + path
    if name in schema_names:
        n = 1
        while True:
            name = "schema_{}_{}".format(path, n)
            if name not in schema_names.values():
                break
            n += 1

    schema_names[str(vschema)] = name
    definitions[name] = schema
    return get_ref(name)


def convert_schema(path, vschema):
    if 'priority' in path:
        path = path

    # analyze input key, if it is not a Required or Optional, then it is an array
    output = {}

    if isinstance(vschema, tuple):
        vschema = vschema[0]

    # When schema contains all, all also has a schema which points
    # back to the containing schema
    while hasattr(vschema, 'schema') and not hasattr(vschema, 'validators'):
        vschema = vschema.schema

    if hasattr(vschema, 'validators'):
        for v in vschema.validators:
            # we should take the valid schema,
            # commonly all is used to validate a schema, and then a function which
            # is not a schema es also given, get_schema will then return a default_schema()
            val_schema = get_jschema(path, v, False)
            if JSC_PROPERTIES not in val_schema:
                continue
            if JSC_PROPERTIES not in output:
                output = val_schema
            else:
                output = {**output, **val_schema}
        return output

    if not vschema:
        return output

    if not hasattr(vschema, 'keys'):
        return get_entry(path, vschema)

    key = list(vschema.keys())[0]

    # used for platformio_options in core_config
    # pylint: disable=comparison-with-callable
    if key == cv.string_strict:
        output["type"] = "object"
        return output

    p = output[JSC_PROPERTIES] = {}
    output["type"] = ["object", "null"]

    for k in vschema:
        if (str(k) == 'priority'):
            k = k

        v = vschema[k]

        if isinstance(v, vol.Schema):
            p[str(k)] = get_jschema(path + '-' + str(k), v.schema)
        else:
            p[str(k)] = get_entry(path + '-' + str(k), v)

        # TODO: see required to check if completion shows before
        # if isinstance(k, cv.Required):
        #     p[str(k)]["required"] = True

    return output


def add_actions():
    from esphome.automation import ACTION_REGISTRY
    for name in ACTION_REGISTRY.keys():
        schema = get_jschema(str(name), ACTION_REGISTRY[name].schema)
        if not schema:
            schema = {"type": "string"}
        action_schema = {"type": "object", JSC_PROPERTIES: {
            name: schema
        }}
        actions.append(action_schema)


def add_conditions():
    from esphome.automation import CONDITION_REGISTRY
    for name in CONDITION_REGISTRY.keys():
        schema = get_jschema(str(name), CONDITION_REGISTRY[name].schema)
        if not schema:
            schema = {"type": "string"}
        condition_schema = {"type": "object", JSC_PROPERTIES: {
            name: schema
        }}
        conditions.append(condition_schema)


def dump_schema():
    from esphome import automation
    from esphome.automation import validate_potentially_and_condition
    schema_registry[validate_potentially_and_condition] = get_ref('condition_list')

    schema_registry[cv.boolean] = {"type": "boolean"}

    for v in [cv.int_, cv.int_range, cv.float_, cv.positive_float, cv.positive_float, cv.positive_not_null_int, cv.negative_one_to_one_float, cv.port]:
        schema_registry[v] = {"type": "number"}

    for v in [cv.string_strict, cv.valid_name, cv.hex_int, cv.hex_int_range,
              cv.ssid,
              cv.positive_time_period, cv.positive_time_period_microseconds, cv.positive_time_period_milliseconds, cv.positive_time_period_minutes,
              cv.positive_time_period_seconds]:
        schema_registry[v] = {"type": "string"}

    definitions = {
        "condition": {"anyOf": conditions},
        "condition_list": {"type": "array", "items": {"$ref": "#/definitions/condition"}},
        JSC_ACTION: {"anyOf": actions},
    }

    output = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "definitions": definitions,
        JSC_PROPERTIES: base_props}

    add_module_schemas("AUTOMATION", automation)
    add_module_schemas("CONDIG", cv)
    add_core()
    add_components()
    add_actions()
    add_conditions()

    print(json.dumps(output))

    # esphome . schema > ..\esphome_devices\schema.json
    # $PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
