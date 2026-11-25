"""Emit the DSDL unpack method for a message or one half of a service."""

from common import get_primitive_kind, get_cast_mode, get_compound_kind


def read_value(t, tao):
    if t.category == t.CATEGORY_PRIMITIVE:
        return (f"readPrimitive(data, msg, {get_primitive_kind(t)}, {t.bitlen}, "
                f"{get_cast_mode(t)})")
    if t.category == t.CATEGORY_COMPOUND:
        name = t.full_name.replace('.', '_')
        return f"readCompound(data, msg, {name}, {get_compound_kind(t)}, {tao})"
    raise ValueError(f"Unsupported field type: {t}")


def unpack_field(field, tao):
    t = field.type
    value = f"msg.fields['{field.name}']"
    if t.category == t.CATEGORY_VOID:
        return f"skipBits(data, msg, {t.bitlen});"
    if t.category == t.CATEGORY_ARRAY:
        width = t.max_size.bit_length() if t.mode == t.MODE_DYNAMIC else 0
        return (f"{value}.items = readArray(data, msg, {t.max_size}, {width}, "
                f"{t.value_type.get_min_bitlen()}, {tao}, "
                f"elementTao => {read_value(t.value_type, 'elementTao')});")
    return f"{value} = {read_value(t, tao)};"


def generate_unpack_method(fields, union):
    lines = ["    static unpack(buf, tao=true, bitOffset=0) {",
             "        const data = Buffer.isBuffer(buf) ? buf : Buffer.from(buf);",
             "        const msg = new this();",
             "        msg.bitOffset = bitOffset;"]
    if union:
        width = max(1, (len(fields) - 1).bit_length())
        lines.extend([f"        const tag = readTag(data, msg, {width});",
                      "        msg.unionFieldIndex.value = tag;",
                      "        switch (tag) {"])
        for index, field in enumerate(fields):
            lines.extend([f"            case {index}:",
                          "                " + unpack_field(field, "tao"),
                          "                break;"])
        lines.extend(["            default: throw new RangeError('Invalid union tag');",
                      "        }",
                      "        const name = msg.unionFields[tag];",
                      "        msg.fields = { [name]: msg.fields[name] };"])
    else:
        for i, field in enumerate(fields):
            tao = "tao" if i == len(fields) - 1 else "false"
            lines.append("        " + unpack_field(field, tao))
    return "\n".join(lines + ["        return msg;", "    }", ""])
