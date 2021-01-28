import json
import voluptuous as vol

import esphome.config_validation as cv

schema_registry = {}
automation_schemas = []  # actually only one


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


schema_extend_tree = {}


def extended_schema(func):
    def decorate(*args, **kwargs):

        ret = func(*args, **kwargs)
        schema_extend_tree[str(ret)] = args
        return ret
    return decorate


def automation_schema():
    def decorate(func):
        automation_schemas.append(func)
        return func
    return decorate


JSC_DESCRIPTION = "description"
JSC_PROPERTIES = "properties"
JSC_ACTION = "action"


class JsonSchema:
    def __init__(self):
        from esphome.automation import validate_potentially_and_condition
        schema_registry[validate_potentially_and_condition] = get_ref('condition_list')

        schema_registry[cv.boolean] = {"type": "boolean"}

        for v in [cv.int_, cv.int_range, cv.float_, cv.positive_float, cv.positive_float, cv.positive_not_null_int, cv.negative_one_to_one_float, cv.port]:
            schema_registry[v] = {"type": "number"}

        for v in [cv.string_strict, cv.valid_name, cv.hex_int, cv.hex_int_range,
                  cv.positive_time_period, cv.positive_time_period_microseconds, cv.positive_time_period_milliseconds, cv.positive_time_period_minutes,
                  cv.positive_time_period_seconds]:
            schema_registry[v] = {"type": "string"}

        self.base_props = {}
        self.actions = []
        self.conditions = []
        self.definitions = {
            "condition": {"anyOf": self.conditions},
            "condition_list": {"type": "array", "items": {"$ref": "#/definitions/condition"}},
            JSC_ACTION: {"anyOf": self.actions},
        }

        self.output = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "definitions": self.definitions,
            JSC_PROPERTIES: self.base_props}

    def add_core(self):
        from esphome.core_config import CONFIG_SCHEMA

        self.base_props["esphome"] = self.get_schema("esphome", CONFIG_SCHEMA.schema)

    def add_components(self):
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
                if c.config_schema is not None:
                    # adds root components which are not platforms, e.g. api: logger:
                    if (domain == 'script'):
                        domain = domain
                    self.definitions[domain] = self.get_schema(domain, c.config_schema)
                    schema = get_ref(domain)
                    if c.is_multi_conf:
                        schema = add_definition_array_or_single_object(schema)
                    self.base_props[domain] = schema

                if c.is_platform_component:
                    # this is a platform_component, e.g. binary_sensor
                    platform_schema = []
                    self.base_props[domain] = {"type": "array",
                                               "items": {"type": "object",
                                                         JSC_PROPERTIES: {
                                                             "platform": {"type": "string"},
                                                             "id": {"type": "string"},
                                                             "name": {"type": "string"}
                                                         },
                                                         "allOf": platform_schema}}

                    #base_schema = self.get_schema(domain, c.config_schema)

                    for platform in dir_names:
                        p = get_platform(domain, platform)
                        if (p is not None):
                            # this is a platform element, e.g.
                            #   - platform: gpio
                            schema = self.get_schema(platform, p.config_schema)
                            platform_schema.append({
                                "if": {
                                    JSC_PROPERTIES: {"platform": {"const": platform}}},
                                "then": schema})

        return

    def dump(self):
        return json.dumps(self.output)

    def get_automation_schema(self, name, value):
        automation_definition = self.get_schema(name, value(automation_schema))
        # automations can be either
        #   * a single action,
        #   * an array of action,
        #   * an object with automation's schema and a then key
        #        with again a single action or an array of actions

        automation_definition[JSC_PROPERTIES]["then"] = add_definition_array_or_single_object(
            get_ref(JSC_ACTION))

        AUTOMATION_KEY = "automation-" + name
        self.definitions[AUTOMATION_KEY] = automation_definition

        schema = add_definition_array_or_single_object(get_ref(JSC_ACTION))
        schema["anyOf"].append(get_ref(AUTOMATION_KEY))
        # relax multiple matching error
        #schema["anyOf"] = schema.pop("oneOf")

        return schema

    def get_entry(self, parent_key, value):
        if value in schema_registry:
            entry = schema_registry[value]
        elif value in automation_schemas:
            entry = self.get_automation_schema(parent_key, value)
        else:
            # everything else just accept string and let ESPHome validate
            entry = self.default_schema()

        # annotate schema validator info
        entry[JSC_DESCRIPTION] = str(value)
        return entry

    def default_schema(self):
        # Accept anything
        return {"type": ["null", "object", "string", "array", "number"]}

    def is_default_schema(self, schema):
        return schema["type"] == self.default_schema()["type"]

    def get_schema(self, parent_key, input):
        from esphome.automation import AUTOMATION_SCHEMA
        # analyze input key, if it is not a Required or Optional, then it is an array
        output = {}

        if str(input) in schema_extend_tree:
            output = output

        # When schema contains all, all also has a schema which points
        # back to the containing schema
        while hasattr(input, 'schema') and not hasattr(input, 'validators'):
            input = input.schema

        if hasattr(input, 'validators'):
            for v in input.validators:
                # we should take the valid schema,
                # commonly all is used to validate a schema, and then a function which
                # is not a schema es also given, get_schema will then return a default_schema()
                val_schema = self.get_schema(parent_key, v)
                if JSC_PROPERTIES not in val_schema:
                    continue
                if JSC_PROPERTIES not in output:
                    output = val_schema
                else:
                    output = {**output, **val_schema}
            return output

        if not input:
            return output

        if not hasattr(input, 'keys'):
            return self.get_entry(parent_key, input)

        key = list(input.keys())[0]

        # used for platformio_options in core_config

        # pylint: disable=comparison-with-callable
        if key == cv.string_strict:
            output["type"] = "object"
            return output

        p = output[JSC_PROPERTIES] = {}
        output["type"] = ["object", "null"]

        for k in input:
            # if (str(k) == 'port'):
            #     breakpoint()

            v = input[k]

            if isinstance(v, vol.Schema):
                p[str(k)] = self.get_schema(str(k), v.schema)
            else:
                p[str(k)] = self.get_entry(str(k), v)

            # TODO: see required to check if completion shows before
            # if isinstance(k, cv.Required):
            #     p[str(k)]["required"] = True

        return output

    def add_actions(self):
        from esphome.automation import ACTION_REGISTRY
        for name in ACTION_REGISTRY.keys():
            schema = self.get_schema(str(name), ACTION_REGISTRY[name].schema)
            if not schema:
                schema = {"type": "string"}
            action_schema = {"type": "object", JSC_PROPERTIES: {
                name: schema
            }}
            self.actions.append(action_schema)

    def add_conditions(self):
        from esphome.automation import CONDITION_REGISTRY
        for name in CONDITION_REGISTRY.keys():
            schema = self.get_schema(str(name), CONDITION_REGISTRY[name].schema)
            if not schema:
                schema = {"type": "string"}
            condition_schema = {"type": "object", JSC_PROPERTIES: {
                name: schema
            }}
            self.conditions.append(condition_schema)


def dump_schema():
    schema = JsonSchema()
    schema.add_core()
    schema.add_components()
    schema.add_actions()
    schema.add_conditions()

    # $PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
    print(schema.dump())
