"""Emit the DSDL pack method for a message or one half of a service."""


def pack_field(field, tao):
    t = field.type
    value = f"this.fields['{field.name}']"
    if t.category == t.CATEGORY_VOID:
        return f"bits.push(...Array({t.bitlen}).fill(0));"
    if t.category == t.CATEGORY_ARRAY:
        count_bits = t.max_size.bit_length() if t.mode == t.MODE_DYNAMIC else 0
        return (f"packArray(bits, {value}.items, {t.max_size}, {count_bits}, "
                f"{t.value_type.get_min_bitlen()}, {tao});")
    if t.category == t.CATEGORY_COMPOUND:
        return f"for (const bit of {value}.pack({tao})) bits.push(bit);"
    return f"bits.push(...{value}.pack());"


def generate_pack_method(fields, union):
    lines = ["    pack(tao=true) {", "        const bits = [];"]
    if union:
        width = max(1, (len(fields) - 1).bit_length())
        lines.extend(["        const tag = this.unionFieldIndex.value;",
                      f"        appendTag(bits, tag, {width});",
                      "        switch (tag) {"])
        for index, field in enumerate(fields):
            lines.extend([f"            case {index}:",
                          "                " + pack_field(field, "tao"),
                          "                break;"])
        lines.extend(["            default: throw new RangeError('Invalid union tag');",
                      "        }"])
    else:
        for i, field in enumerate(fields):
            tao = "tao" if i == len(fields) - 1 else "false"
            lines.append("        " + pack_field(field, tao))
    lines.extend(["        if (bits.length < this.constructor.MIN_BIT_LEN || bits.length > this.constructor.MAX_BIT_LEN) {",
                  "            throw new RangeError('Encoded message length outside DSDL bounds');",
                  "        }", "        return bits;", "    }", ""])
    return "\n".join(lines)
