# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import os
import uuid
from base64 import b64encode
from secrets import token_bytes

import yaml
from cerberus import Validator, schema_registry
from flask import escape
from isardvdi_common.default_storage_pool import DEFAULT_STORAGE_POOL_ID

from api import app


class IsardValidator(Validator):
    def _normalize_coerce_sanitize(self, value):
        if type(value) == str:
            return escape(value)
        elif type(value) == list:
            new_list = []
            for item in value:
                if type(item) == str:
                    new_list.append(escape(item))
                elif type(item) == dict:
                    new_list.append(self._normalize_coerce_sanitize(item))
                else:
                    new_list.append(item)
            return new_list
        elif type(value) == dict:
            data = {
                key: (
                    escape(value)
                    if type(value) == str
                    else self._normalize_coerce_sanitize(value)
                )
                for key, value in value.items()
            }
            return data
        else:
            return value

    def _normalize_default_setter_storagepools(self):
        return DEFAULT_STORAGE_POOL_ID

    def _normalize_default_setter_genuuid(self, document):
        return str(uuid.uuid4())

    def _normalize_default_setter_mediaicon(self, document):
        if document["kind"] == "iso":
            return "fa-circle-o"
        else:
            return "fa-floppy-o"

    def _check_with_validate_vlan(self, field, value):
        """
        Value should be a string with a numeric value >= 1 and <= 4094
        """
        if not (value.isnumeric() and 1 <= int(value) <= 4094):
            self._error(
                field, "Value should be a string with a numeric value >= 1 and <= 4094"
            )

    def _check_with_validate_vlan_range(self, field, value):
        """
        Value should be a string with a numeric range like 55-33 and range should be >= 1 and <= 4094
        """
        range = value.split("-")
        if len(range) != 2 or not range[0].isnumeric() or not range[1].isnumeric():
            self._error(
                field, 'Value should be a string with a numeric range like "55-33"'
            )
        elif int(range[0]) > int(range[1]):
            self._error(
                field, "Last range number cannot be less than first range number"
            )
        elif not 1 <= int(range[0]) <= 4094 or not 1 <= int(range[1]) <= 4094:
            self._error(field, "Range limits should be >= 1 and <= 4094")

    def _check_with_validate_time_values(self, data):
        action = data.get("op", "shutdown")
        max_time = data[action]["max"]
        warning_time = data[action]["notify_intervals"][1]["time"]
        danger_time = data[action]["notify_intervals"][0]["time"]
        if (
            max_time <= 0
            or warning_time >= 0
            or danger_time >= 0
            or warning_time >= max_time
            or danger_time >= max_time
            or danger_time <= warning_time
        ):
            self._error("bad_request", "Incorrect time values.")

    def _normalize_default_setter_gensecret(self, document):
        return b64encode(token_bytes(32)).decode()

    def _check_with_depends_if(self, field, value):
        """Conditional dependency validator.

        The ``depends_if`` meta is a list of condition dicts.  Each
        condition is evaluated independently.

        A condition has ``values`` (a list of check groups) and
        ``other_fields`` (fields to enforce when values match).

        Each check group in ``values`` is an object with ``and`` or
        ``or`` key containing a list of checks.  Each check can have:

        - ``path``: dotted sub-path within the field's value (for dicts).
          Omit to check the field's value directly.
        - ``value``: triggers when the checked value **equals** this.
        - ``not_value``: triggers when the checked value **does not
          equal** this.

        For ``and`` groups, all checks must match.  For ``or`` groups,
        at least one must match.  All groups in ``values`` must match
        for the condition to trigger.

        When triggered, the condition enforces:

        - ``other_fields.and``: every listed field must be **present
          and non-empty** in the document.
        - ``other_fields.or``: at least one of the listed fields must be
          **present and non-empty** in the document.

        Empty strings, empty lists, empty dicts and ``None`` are considered empty.

        Resolution contexts for paths:

        - ``path`` in value checks resolves relative to the **current
          field's value**.  For dict fields, ``path: enabled`` extracts
          ``field_value["enabled"]``.  For scalar fields, omit ``path``
          to check the field's value directly.
        - Paths in ``other_fields`` resolve relative to
          ``self.document``, the current Cerberus validation context.
          This is the document containing the current field and its
          siblings, not the field's own value.

        Example: when ``check_with`` is on ``saml_config`` in
        ``saml_config_update.yml``, ``self.document`` is
        ``{enabled, saml_config, migration}``.  So ``path: auto_register``
        in values resolves within ``saml_config``'s dict value, while
        ``other_fields: [saml_config.field_group]`` resolves from the
        top-level document, traversing into ``saml_config``.

        Field paths in ``other_fields`` support dotted notation for
        nested documents.

        Example without ``path``::

            # Checks the field's own value directly.
            my_field:
              type: string
              check_with: depends_if
              meta:
                depends_if:
                  # Condition 1: triggers when value is not empty.
                  - values:
                      - and:
                          - not_value: ''
                    other_fields:
                      and:
                        - required_sibling
                  # Condition 2: triggers when value is "a" or "b".
                  - values:
                      - or:
                          - value: a
                          - value: b
                    other_fields:
                      and:
                        - other_sibling

        Example with ``path`` (dict fields)::

            # ``path`` resolves within the field's own dict value.
            # ``other_fields`` paths resolve from self.document (the
            # parent containing this field and its siblings), supporting
            # dotted notation for nested access.
            my_dict_field:
              type: dict
              schema: my_snippet
              check_with: depends_if
              meta:
                depends_if:
                  # Condition 1: compound AND + OR on sub-paths.
                  # Triggers when enabled is true AND size is not
                  # "small" AND (source is "ldap" OR source is "saml").
                  - values:
                      - and:
                          - path: enabled
                            value: true
                          - path: size
                            not_value: small
                      - or:
                          - path: source
                            value: ldap
                          - path: source
                            value: saml
                    other_fields:
                      and:
                        - sibling_field.nested_field
                      or:
                        - option_a
                        - option_b
                  # Condition 2: evaluated independently.
                  - values:
                      - and:
                          - path: auto_register
                            value: true
                          - path: group_default
                            value: ''
                    other_fields:
                      and:
                        - my_dict_field.field_group
        """
        for condition in self.schema[field]["meta"]["depends_if"]:
            self._evaluate_depends_if(field, value, condition)

    def _evaluate_depends_if(self, field, value, condition):
        """Evaluate a single depends_if condition."""
        for group in condition.get("values", []):
            if not self._check_value_group(value, group):
                return

        other_fields = condition.get("other_fields", {})
        and_fields = other_fields.get("and", [])
        missing = [f for f in and_fields if not self._has_value(f)]
        if missing:
            self._error(
                field,
                f"fields {missing} are required" f" for field '{field}'",
            )
        or_fields = other_fields.get("or", [])
        if or_fields and not any(self._has_value(f) for f in or_fields):
            self._error(
                field,
                f"at least one of {or_fields} must be present" f" for field '{field}'",
            )

    def _check_value_group(self, value, group):
        """Check a value group (and/or) against the field value."""
        if "and" in group:
            return all(self._check_single_value(value, check) for check in group["and"])
        return any(self._check_single_value(value, check) for check in group["or"])

    def _check_single_value(self, value, check):
        """Check a single value condition against the field value."""
        check_value = value
        path = check.get("path")
        if path:
            obj = value
            for key in path.split("."):
                if not isinstance(obj, dict) or key not in obj:
                    return False
                obj = obj[key]
            check_value = obj
        if "value" in check:
            return check_value == check["value"]
        if "not_value" in check:
            return check_value != check["not_value"]
        return True

    def _has_value(self, path):
        """Check if a dotted field path exists and has a non-empty value in the document."""
        obj = self.document
        for key in path.split("."):
            if not isinstance(obj, dict) or key not in obj:
                return False
            obj = obj[key]
        return obj != "" and obj != [] and obj != {} and obj is not None


def _validate_depends_if_schemas(schema, path=""):
    """Validate depends_if definitions in a schema at startup."""
    if not isinstance(schema, dict):
        return
    for field_name, field_schema in schema.items():
        if not isinstance(field_schema, dict):
            continue
        field_path = f"{path}.{field_name}" if path else field_name
        depends_if = field_schema.get("meta", {}).get("depends_if")
        if depends_if:
            if not isinstance(depends_if, list):
                raise ValueError(f"depends_if must be a list in {field_path}")
            for i, condition in enumerate(depends_if):
                for j, group in enumerate(condition.get("values", [])):
                    if "and" not in group and "or" not in group:
                        raise ValueError(
                            f"depends_if value group must have 'and' or"
                            f" 'or' key in {field_path}[{i}].values[{j}]"
                        )
                    checks = group.get("and", group.get("or", []))
                    for k, check in enumerate(checks):
                        check_path = check.get("path")
                        if check_path is not None:
                            if not isinstance(check_path, str):
                                raise ValueError(
                                    f"depends_if 'path' must be a string"
                                    f" in {field_path}[{i}].values"
                                    f"[{j}][{k}], got:"
                                    f" {type(check_path).__name__}"
                                )
                            if field_schema.get("type") != "dict":
                                raise ValueError(
                                    f"depends_if 'path' requires"
                                    f" type: dict in {field_path}"
                                )
        nested = field_schema.get("schema")
        if isinstance(nested, dict):
            _validate_depends_if_schemas(nested, field_path)


def load_validators(purge_unknown=True):
    snippets_path = os.path.join(app.root_path, "schemas/snippets")
    for snippets_filename in os.listdir(snippets_path):
        with open(os.path.join(snippets_path, snippets_filename)) as file:
            snippet_schema_yml = file.read()
            snippet_schema = yaml.safe_load(snippet_schema_yml)
            _validate_depends_if_schemas(snippet_schema, snippets_filename)
            schema_registry.add(snippets_filename.split(".")[0], snippet_schema)

    validators = {}
    schema_path = os.path.join(app.root_path, "schemas")
    for schema_filename in os.listdir(schema_path):
        try:
            with open(os.path.join(schema_path, schema_filename)) as file:
                schema_yml = file.read()
                schema = yaml.safe_load(schema_yml)
                _validate_depends_if_schemas(schema, schema_filename)
                validators[schema_filename.split(".")[0]] = IsardValidator(
                    schema, purge_unknown=purge_unknown
                )
                validators[schema_filename.split(".")[0] + ".schema"] = schema
        except IsADirectoryError:
            None
    return validators
