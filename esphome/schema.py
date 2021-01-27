import json
import voluptuous as vol

import esphome.config_validation as cv

schema_registry = {}


def get_ref(definition):
    return {"$ref": "#/definitions/" + definition}


def schema_info(description):
    def decorate(func):
        schema_registry[func] = get_ref(description)
        return func

    return decorate


JSC_PROPERTIES = "properties"


class JsonSchema:
    def __init__(self):
        from esphome.automation import validate_potentially_and_condition
        schema_registry[validate_potentially_and_condition] = get_ref('condition_list')
        schema_registry[cv.boolean] = {"type": "boolean"}

        self.base_props = {}
        self.actions = []
        self.conditions = []
        self.output = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "definitions": {
                "condition": {"anyOf": self.conditions},
                "condition_list":
                {"type": "array", "items": {"$ref": "#/definitions/condition"}},
                "action": {"anyOf": self.actions},
                "automation":
                {"oneOf": [
                    {
                        "type": "array",
                        "items": {"$ref": "#/definitions/action"}
                    },
                    {
                        "type": "object",
                        "properties": {
                            "then": {
                                "type": "array",
                                "items": {"$ref": "#/definitions/action"}
                            }
                        }
                    }
                ]},
            },
            "type": "object",
            "properties": self.base_props}

    def add_core(self):
        from esphome.core_config import CONFIG_SCHEMA

        self.base_props["esphome"] = self.get_schema(CONFIG_SCHEMA.schema)

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
                    self.base_props[domain] = self.get_schema(c.config_schema)
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

                    for platform in dir_names:
                        p = get_platform(domain, platform)
                        if (p is not None):
                            # this is a platform element, e.g.
                            #   - platform: gpio
                            schema = self.get_schema(p.config_schema)
                            platform_schema.append({
                                "if": {
                                    JSC_PROPERTIES: {"platform": {"const": platform}}},
                                "then": schema})

        return

    def dump(self):
        return json.dumps(self.output)

    def get_entry(self, value):
        if value in schema_registry:
            entry = schema_registry[value]
        else:
            # everything else just accept string and let ESPHome validate
            entry = self.default_schema()

        # annotate schema validator info
        entry["description"] = str(value)
        return entry

    def default_schema(self):
        # Accept anything
        return {"type": ["null", "object", "string", "array", "number"]}

    def get_schema(self, input):
        # analyze input key, if it is not a Required or Optional, then it is an array
        output = {}

        # When schema contains all, all also has a schema which points
        # back to the containing schema
        while hasattr(input, 'schema') and not hasattr(input, 'validators'):
            input = input.schema

        if hasattr(input, 'validators'):
            for v in input.validators:
                # we should take the valid schema,
                # commonly all is used to validate a schema, and then a function which
                # is not a schema es also given, get_schema will then return a default_schema()
                val_schema = self.get_schema(v)
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
            return self.get_entry(input)

        key = list(input.keys())[0]

        # used for platformio_options in core_config

        # pylint: disable=comparison-with-callable
        if key == cv.string_strict:
            output["type"] = "object"
            return output

        p = output[JSC_PROPERTIES] = {}
        output["type"] = ["object", "null"]

        for k in input:
            # if (str(k) == 'fast_connect'):
            #     breakpoint()

            v = input[k]

            if isinstance(v, vol.Schema):
                p[str(k)] = self.get_schema(v.schema)
            else:
                p[str(k)] = self.get_entry(v)

            if isinstance(k, cv.Required):
                p[str(k)]["required"] = True

        return output

    def add_actions(self):
        from esphome.automation import ACTION_REGISTRY
        for name in ACTION_REGISTRY.keys():
            schema = self.get_schema(ACTION_REGISTRY[name].schema)
            if not schema:
                schema = {"type": "string"}
            action_schema = {"type": "object", "properties": {
                name: schema
            }}
            self.actions.append(action_schema)

    def add_conditions(self):
        from esphome.automation import CONDITION_REGISTRY
        for name in CONDITION_REGISTRY.keys():
            schema = self.get_schema(CONDITION_REGISTRY[name].schema)
            if not schema:
                schema = {"type": "string"}
            condition_schema = {"type": "object", "properties": {
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
