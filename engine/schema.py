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
    "required": ["title", "hook", "scenes", "end_question", "cards", "captions", "carousel", "thumbnail"],
    "properties": {
        "title": {"type": "string"},
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
        "thumbnail": {"type": "object", "additionalProperties": False, "required": ["name", "name_hi", "words", "words_hi", "scene"],
                      "properties": {"name": {"type": "string"}, "name_hi": {"type": "string"},
                                     "words": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
                                     "words_hi": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
                                     "scene": {"type": "string"}}},
    },
}

# Claude structured outputs reject these JSON-Schema keywords (a 400 for the whole request, 21 Oct 2026: maxItems);
# api_schema() drops them from what is sent and validate() still enforces them here.
UNSUPPORTED = {"maxItems", "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
               "multipleOf", "pattern", "uniqueItems", "minProperties", "maxProperties"}


def api_schema(sch):
    """A copy of the schema that Claude's output_config.format accepts: unsupported keywords removed, minItems kept only as 0 or 1."""
    if isinstance(sch, list):
        return [api_schema(s) for s in sch]
    if not isinstance(sch, dict):
        return sch
    out = {}
    for k, v in sch.items():
        if k in UNSUPPORTED or (k == "minItems" and v not in (0, 1)):
            continue
        out[k] = {pk: api_schema(pv) for pk, pv in v.items()} if k == "properties" else api_schema(v)
    return out


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
        if len(obj) < sch.get("minItems", 0) or len(obj) > sch.get("maxItems", len(obj)):
            errors.append(f"{path}: {len(obj)} items, allowed {sch.get('minItems', 0)}-{sch.get('maxItems', 'any')}")
        for i, item in enumerate(obj):
            errors += validate(item, sch["items"], f"{path}[{i}]")
    return errors
