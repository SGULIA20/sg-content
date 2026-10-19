"""The piece JSON schema the writer must return, and a small validator (no jsonschema dependency)."""

CARD = {"type": "object", "additionalProperties": False, "required": ["big_number", "line", "source"],
        "properties": {"big_number": {"type": "string"}, "line": {"type": "string"}, "source": {"type": "string"}}}

VISUAL = {"type": "object", "additionalProperties": False, "required": ["type", "prompt", "card"],
          "properties": {"type": {"type": "string", "enum": ["avatar", "art", "card", "photo"]},
                         "prompt": {"type": "string"},
                         "card": {"anyOf": [CARD, {"type": "null"}]}}}

SCENE = {"type": "object", "additionalProperties": False, "required": ["vo", "visual", "facts_used", "label"],
         "properties": {"vo": {"type": "string"}, "visual": VISUAL,
                        "facts_used": {"type": "array", "items": {"type": "integer"}},
                        "label": {"anyOf": [{"type": "string"}, {"type": "null"}]}}}

PIECE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["hook", "scenes", "end_question", "cards", "captions", "carousel"],
    "properties": {
        "hook": {"type": "string"},
        "scenes": {"type": "array", "items": SCENE},
        "end_question": {"type": "string"},
        "cards": {"type": "array", "items": CARD},
        "captions": {"type": "object", "additionalProperties": False, "required": ["youtube", "instagram", "threads"],
                     "properties": {
                         "youtube": {"type": "object", "additionalProperties": False, "required": ["title", "description", "tags", "chapters"],
                                     "properties": {"title": {"type": "string"}, "description": {"type": "string"},
                                                    "tags": {"type": "array", "items": {"type": "string"}},
                                                    "chapters": {"type": "array", "items": {"type": "string"}}}},
                         "instagram": {"type": "object", "additionalProperties": False, "required": ["caption", "hashtags"],
                                       "properties": {"caption": {"type": "string"}, "hashtags": {"type": "array", "items": {"type": "string"}}}},
                         "threads": {"type": "object", "additionalProperties": False, "required": ["text"],
                                     "properties": {"text": {"type": "string"}}}}},
        "carousel": {"type": "boolean"},
    },
}

_TYPES = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}


def validate(obj, sch: dict = PIECE_SCHEMA, path: str = "$") -> list:
    """Returns a list of problems (empty = valid). Supports the subset used in PIECE_SCHEMA."""
    if "anyOf" in sch:
        options = [validate(obj, s, path) for s in sch["anyOf"]]
        return [] if any(not e for e in options) else [f"{path}: matches none of the allowed shapes"]
    t = sch.get("type")
    if t and not isinstance(obj, _TYPES[t]) or (t == "integer" and isinstance(obj, bool)):
        return [f"{path}: expected {t}"]
    if "enum" in sch and obj not in sch["enum"]:
        return [f"{path}: '{obj}' not one of {sch['enum']}"]
    errors = []
    if t == "object":
        props = sch.get("properties", {})
        for key in sch.get("required", []):
            if key not in obj:
                errors.append(f"{path}.{key}: missing")
        for key, val in obj.items():
            if key in props:
                errors += validate(val, props[key], f"{path}.{key}")
            elif not sch.get("additionalProperties", True):
                errors.append(f"{path}.{key}: unexpected key")
    if t == "array":
        for i, item in enumerate(obj):
            errors += validate(item, sch["items"], f"{path}[{i}]")
    return errors
