import esphome.config_validation as cv
import json
import voluptuous as vol

JSC_DESCRIPTION = "description"
JSC_PROPERTIES = "properties"
JSC_ACTION = "automation.ACTION_REGISTRY"
JSC_CONDITION = "automation.CONDITION_REGISTRY"
JSC_ANYOF = "anyOf"
JSC_ONEOF = "oneOf"
SIMPLE_AUTOMATION = "simple_automation"

schema_names = {}
schema_registry = {}
schema_extend_registry = {}
schema_list_registry = {}
schema_registry_registry = {}
components = {}
modules = {}
registries = []
pending_refs = []

automation_schemas = []  # actually only one
definitions = {}
base_props = {}


def get_ref(definition):
    return {"$ref": "#/definitions/" + definition}


def is_ref(jschema):
    return "$ref" in jschema


def add_definition_array_or_single_object(ref):
    return {JSC_ANYOF: [
        {
            "type": "array",
            "items": ref
        },
        ref
    ]}


def extended_schema(func):
    def decorate(*args, **kwargs):
        ret = func(*args, **kwargs)
        assert(len(args) == 2)
        schema_extend_registry[str(ret)] = args
        return ret
    return decorate


def list_schema(func):
    def decorate(*args, **kwargs):
        ret = func(*args, **kwargs)
        schema_list_registry[str(ret)] = args
        return ret
    return decorate


def schema_registry_validator(registry):
    def decorator(func):
        schema_registry_registry[str(func)] = registry
        return func
    return decorator


def automation_schema():
    def decorate(func):
        automation_schemas.append(func)
        return func
    return decorate


def add_core():
    from esphome.core_config import CONFIG_SCHEMA
    base_props["esphome"] = get_jschema("esphome", CONFIG_SCHEMA.schema)


def add_registries():
    from esphome.util import Registry
    for domain, module in modules.items():
        for c in dir(module):
            m = getattr(module, c)
            if isinstance(m, Registry):
                add_registry(domain + '.' + c, m)


def add_registry(registry_name, registry):
    validators = []
    registries.append((registry, registry_name))
    for name in registry.keys():
        schema = get_jschema(str(name), registry[name].schema, create_return_ref=False)
        if not schema:
            schema = {"type": "string"}
        o_schema = {"type": "object", JSC_PROPERTIES: {
            name: schema
        }}
        validators.append(o_schema)
    definitions[registry_name] = {JSC_ANYOF: validators}


def get_registry_ref(registry):
    # we don't know yet
    ref = {"$ref": "pending"}
    pending_refs.append((ref, registry))
    return ref


def solve_pending_refs():
    for ref, registry in pending_refs:
        for registry_match, name in registries:
            if registry == registry_match:
                ref["$ref"] = '#/definitions/' + name


def add_module_schemas(name, module):
    for c in dir(module):
        v = getattr(module, c)
        if isinstance(v, cv.Schema):
            get_jschema(name + '.' + c, v)


def get_dirs():
    import os
    from esphome.config import CORE_COMPONENTS_PATH
    dir_names = [d for d in os.listdir(CORE_COMPONENTS_PATH) if
                 not d.startswith('__') and
                 os.path.isdir(os.path.join(CORE_COMPONENTS_PATH, d))]

    dir_names = ['binary_sensor', 'gpio']
    return dir_names


def load_components():
    from esphome.config import get_component

    from esphome import config_validation
    modules["cv"] = config_validation
    from esphome import automation
    modules["automation"] = automation

    for domain in get_dirs():
        components[domain] = get_component(domain)
        modules[domain] = components[domain].module


def add_components():
    from esphome.config import get_platform

    for domain, c in components.items():
        if ((c.config_schema is not None) or c.is_platform_component):
            if c.is_platform_component:
                # this is a platform_component, e.g. binary_sensor
                platform_schema = []
                base_props[domain] = {"type": "array",
                                      "items": {"type": "object",
                                                JSC_PROPERTIES: {
                                                    "platform": {"type": "string"},
                                                },
                                                "allOf": platform_schema}}

                if domain == 'sensor':
                    domain = domain
                add_module_schemas(domain, c.module)

                for platform in get_dirs():
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

                schema = create_ref(domain, c.config_schema, get_jschema(domain, c.config_schema))
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
            simple_automation[JSC_ANYOF].append(get_jschema(AUTOMATION_SCHEMA.__module__, AUTOMATION_SCHEMA))

            definitions[schema_names[str(AUTOMATION_SCHEMA)]][JSC_PROPERTIES]["then"] = add_definition_array_or_single_object(
                get_ref(JSC_ACTION))
            definitions[SIMPLE_AUTOMATION] = simple_automation

        return get_ref(SIMPLE_AUTOMATION)

    schema = add_definition_array_or_single_object(get_ref(JSC_ACTION))
    schema[JSC_ANYOF].append(get_ref(extended_key))
    return schema


def get_entry(parent_key, value):
    if parent_key == "AUTOMATION.AUTOMATION_SCHEMA-then":
        parent_key = parent_key

    if value in schema_registry:
        entry = schema_registry[value]
    elif str(value) in schema_registry_registry:
        entry = get_registry_ref(schema_registry_registry[str(value)])
    elif str(value) in schema_list_registry:
        ref = get_jschema(parent_key, schema_list_registry[str(value)])
        entry = {JSC_ANYOF: [ref, {"type": "array", "items": ref}]}

    elif value in automation_schemas:
        entry = get_automation_schema(parent_key, value)
    else:
        # everything else just accept string and let ESPHome validate
        entry = default_schema()

    # annotate schema validator info
    entry[JSC_DESCRIPTION] = 'entry: ' + parent_key + '/' + str(value)

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

    jschema = convert_schema(path, vschema)

    if not create_return_ref:
        return jschema

    return create_ref("schema_" + path, vschema, jschema)


def create_ref(name, vschema, jschema):
    if name in schema_names:
        n = 1
        while True:
            name = "schema_{}_{}".format(path, n)
            if name not in schema_names.values():
                break
            n += 1

    schema_names[str(vschema)] = name
    definitions[name] = jschema
    return get_ref(name)


def convert_schema(path, vschema):
    if 'binary_sensor.BINARY_SENSOR_SCHEMA' == path:
        path = path

    # analyze input key, if it is not a Required or Optional, then it is an array
    output = {}

    extended = schema_extend_registry.get(str(vschema))
    if extended:
        lhs = get_jschema(path, extended[0], False)
        rhs = get_jschema(path, extended[1], False)
        if is_ref(rhs):
            lhs, rhs = rhs, lhs
        output = {JSC_ANYOF: [lhs, rhs]}
        return output

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
            if JSC_PROPERTIES in val_schema:
                # name will be weird here
                val_schema = create_ref("schema__" + path, v, val_schema)

            if is_ref(val_schema):
                output = val_schema

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
    output["description"] = 'converted: ' + str(vschema)

    for k in vschema:
        if (str(k) == 'discovery'):
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


def dump_schema():
    from esphome import automation
    from esphome.automation import validate_potentially_and_condition

    schema_registry[cv.boolean] = {"type": "boolean"}

    for v in [cv.int_, cv.int_range, cv.float_, cv.positive_float, cv.positive_float, cv.positive_not_null_int, cv.negative_one_to_one_float, cv.port]:
        schema_registry[v] = {"type": "number"}

    for v in [cv.string_strict, cv.valid_name, cv.hex_int, cv.hex_int_range,
              cv.ssid,
              cv.positive_time_period, cv.positive_time_period_microseconds, cv.positive_time_period_milliseconds, cv.positive_time_period_minutes,
              cv.positive_time_period_seconds]:
        schema_registry[v] = {"type": "string"}
    schema_registry[validate_potentially_and_condition] = get_ref('condition_list')

    add_module_schemas("CONFIG", cv)
    add_module_schemas("AUTOMATION", automation)

    load_components()
    add_registries()

    definitions["condition_list"] = {JSC_ONEOF: [{"type": "array", "items": get_ref(JSC_CONDITION)}, get_ref(JSC_CONDITION)
                                                 ]}

    output = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "definitions": definitions,
        JSC_PROPERTIES: base_props}

    add_core()
    add_components()

    solve_pending_refs()

    print(json.dumps(output))

    # esphome . schema > ..\esphome_devices\schema.json
    # $PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
