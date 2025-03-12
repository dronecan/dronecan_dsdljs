#!/usr/bin/env python
# encoding: utf-8
'''
    Author: Huibean Luo <huibean.luo@vimdrones.com>
'''

from common import get_compound_kind, generate_primitive_type_instance, get_tao

def generate_unpack_method(message, fields):
    js_code = "    static unpack(buf, tao=true, bitOffset=0) {\n"
    js_code += "        const data = new Buffer.from(buf)\n"
    js_code += "        const msg = new this();\n"
    js_code += "        msg.bitOffset = bitOffset;\n"

    if getattr(message, 'union', None) is True:
        union_size = len(message.fields).bit_length()
        js_code += f"        msg.unionFieldIndex = PrimitiveType.unpack(PrimitiveType.KIND_UNSIGNED_INT, data.getBits(msg.bitOffset, {union_size}), {union_size}, PrimitiveType.CAST_MODE_SATURATED);\n"
        js_code += f"        msg.bitOffset += {union_size};\n"
        js_code += f"        switch(msg.unionFieldIndex.value) {{\n"
        for index, field in enumerate(fields):
            js_code += f"            case {index}:\n"
            if field.type.category == field.type.CATEGORY_PRIMITIVE:
                js_code += f"                msg.fields['{field.name}'] = {generate_primitive_type_instance(field.type, field.type.bitlen)};\n"
                js_code += f"                msg.bitOffset += {field.type.bitlen};\n"
            elif field.type.category == field.type.CATEGORY_COMPOUND:
                js_code += f"                msg.fields['{field.name}'] = {field.type.full_name.replace('.', '_')}.unpack(data, false, msg.bitOffset);\n"
                js_code += f"                msg.bitOffset = msg.fields['{field.name}'].bitOffset;\n"
            elif field.type.category == field.type.CATEGORY_VOID:
                js_code += f"                msg.bitOffset += {field.type.bitlen}; //field.type.CATEGORY_VOID {field.type} for Reserved space\n"
            elif field.type.category == field.type.CATEGORY_ARRAY:
                if field.type.mode == field.type.MODE_STATIC:
                    # Static array
                    bitlen = field.type.value_type.bitlen
                    js_code += f"                msg.fields['{field.name}'] = new ArrayType([]);\n"
                    js_code += f"                for (let i = 0; i < {field.type.max_size}; i++) {{\n"
                    js_code += f"                    msg.fields['{field.name}'].items.push({generate_primitive_type_instance(field.type.value_type, bitlen)});\n"
                    js_code += f"                    msg.bitOffset += {bitlen};\n"
                    js_code += f"                }}\n"
                elif field.type.mode == field.type.MODE_DYNAMIC:
                    if index == len(fields) - 1:
                        # Last field of dynamic array, no len bytes, use the remaining bytes
                        js_code += f"                let {field.name}_length = 0;\n"
                        js_code += f"                if (tao) {{\n"
                        js_code += f"                    {field.name}_length = Math.floor((data.byteLength * 8 - msg.bitOffset) / {field.type.value_type.bitlen});\n"
                        js_code += f"                }} else {{\n"
                        js_code += f"                    {field.name}_length = bitsToArrayLength(data.getBits(msg.bitOffset, {field.type.max_size.bit_length()}));\n"
                        js_code += f"                }}\n"
                    else:
                        js_code += f"                let {field.name}_length = bitsToArrayLength(data.getBits(msg.bitOffset, {field.type.max_size.bit_length()}));\n"
                    js_code += f"                msg.bitOffset += {field.type.max_size.bit_length()};\n"
                    js_code += f"                if ({field.name}_length > {field.type.max_size}) {{\n"
                    js_code += f"                    throw new RangeError('{field.name}_length length exceeds maximum size: {field.type.max_size}');\n"
                    js_code += f"                }}\n"
                    js_code += f"                msg.fields['{field.name}'] = new ArrayType([]);\n"
                    js_code += f"                for (let i = 0; i < {field.name}_length; i++) {{\n"
                    if field.type.value_type.category == field.type.value_type.CATEGORY_PRIMITIVE:
                        js_code += f"                    msg.fields['{field.name}'].items.push({generate_primitive_type_instance(field.type.value_type, field.type.value_type.bitlen)});\n"
                        js_code += f"                    msg.bitOffset += {field.type.value_type.bitlen};\n"
                    elif field.type.value_type.category == field.type.value_type.CATEGORY_COMPOUND:
                        js_code += f"                    let {field.name}Msg = {field.type.value_type.full_name.replace('.', '_')}.unpack(data, {get_tao(index, fields)}, msg.bitOffset)\n"
                        js_code += f"                    msg.fields['{field.name}'].items.push(new CompoundType({field.name}Msg, null));\n"
                        js_code += f"                    msg.bitOffset = {field.name}Msg.bitOffset;\n"
                    else:
                        raise ValueError(f"Unsupported value category: {vars(field.type.value_type)}")
                    js_code += f"                }}\n"
                else:
                    raise ValueError(f"Unsupported array mode: {field.type.mode}")
            else:
                raise ValueError(f"Unsupported category: {field.type.category}")
            js_code += f"                break;\n"
        js_code += f"            default:\n"
        js_code += f"                throw new Error(`Invalid union field value: ${{msg.unionField.value}}`);\n"
        js_code += f"        }}\n"
    else:
        for index, field in enumerate(fields):
            if field.type.category == field.type.CATEGORY_ARRAY:
                # Array type
                value_type = field.type.value_type 
                if field.type.mode == field.type.MODE_STATIC:
                    # Static array
                    bitlen = value_type.bitlen
                    js_code += f"        // Decode static array field {field.name}\n"
                    js_code += f"        const {field.name}_length = {field.type.max_size};\n"
                    js_code += f"        for (let i = 0; i < {field.name}_length; i++) {{\n"
                    if value_type.category == value_type.CATEGORY_PRIMITIVE:
                        js_code += f"            msg.fields['{field.name}'].items.push({generate_primitive_type_instance(value_type, bitlen)});\n" 
                        js_code += f"            msg.bitOffset += {bitlen};\n"
                    elif value_type.category == value_type.CATEGORY_COMPOUND:
                        js_code += f"            let {field.name}Msg = {value_type.full_name.replace('.', '_')}.unpack(data, {get_tao(index, fields)}, msg.bitOffset)\n"
                        js_code += f"            msg.fields['{field.name}'].items.push(new CompoundType({field.name}Msg, {get_compound_kind(value_type)}, null));\n"
                        js_code += f"            msg.bitOffset = {field.name}Msg.bitOffset;\n"
                    else:
                        raise ValueError(f"Unsupported value category: {vars(value_type)}")
                    js_code += f"        }}\n\n"
                elif field.type.mode == field.type.MODE_DYNAMIC:
                    # Dynamic array
                    js_code += f"        // Decode dynamic array field {field.name}\n"
                    js_code += f"        let {field.name}_length = 0;\n"
                    if index == len(fields) - 1:
                        js_code += f"        if (tao) {{\n"
                        # Last field of dynamic array, no len bytes, use the remaining bytes
                        if value_type.category == value_type.CATEGORY_PRIMITIVE:
                            js_code += f"            {field.name}_length = Math.floor((data.byteLength * 8 - msg.bitOffset) / {value_type.bitlen});\n"
                        elif value_type.category == value_type.CATEGORY_COMPOUND:
                            if value_type.get_max_bitlen() == value_type.get_min_bitlen():
                                js_code += f"            {field.name}_length = Math.floor((data.byteLength * 8 - msg.bitOffset) / {value_type.get_max_bitlen()});\n"
                            else:
                                js_code += f"            {field.name}_length = (data.byteLength - msg.bitOffset) / 8;\n"
                        else:
                            js_code += f"            {field.name}_length = (data.byteLength - msg.bitOffset) / 8;\n"
                        js_code += f"        }} else {{\n"
                        array_length_bitlen = field.type.max_size.bit_length()
                        js_code += f"            if (Math.floor(msg.bitOffset / 8) < buf.length) {{\n"
                        js_code += f"                {field.name}_length = bitsToArrayLength(data.getBits(msg.bitOffset, {array_length_bitlen}));\n"
                        js_code += f"                msg.bitOffset += {array_length_bitlen};\n"
                        js_code += f"            }} else {{\n"
                        js_code += f"                throw new RangeError('Array length exceeds maximum size: {field.type.max_size}');\n"
                        js_code += f"            }}\n"
                        js_code += f"        }}\n"
                    else:
                        array_length_bitlen = field.type.max_size.bit_length()
                        js_code += f"        if (Math.floor(msg.bitOffset / 8) < buf.length) {{\n"
                        js_code += f"            {field.name}_length = bitsToArrayLength(data.getBits(msg.bitOffset, {array_length_bitlen}));\n"
                        js_code += f"            msg.bitOffset += {array_length_bitlen};\n"
                        js_code += f"        }} else {{\n"
                        js_code += f"            throw new RangeError('Array length exceeds maximum size: {field.type.max_size}');\n"
                        js_code += f"        }}\n"
                    js_code += f"        if ({field.name}_length > {field.type.max_size}) {{\n"
                    js_code += f"            throw new RangeError('{field.name}_length length exceeds maximum size: {field.type.max_size}');\n"
                    js_code += f"        }}\n"

                    js_code += f"        for (let i = 0; i < {field.name}_length; i++) {{\n"
                    if value_type.category == value_type.CATEGORY_PRIMITIVE:
                        bitlen = value_type.bitlen
                        js_code += f"            msg.fields['{field.name}'].items.push({generate_primitive_type_instance(value_type, bitlen)});\n" 
                        js_code += f"            msg.bitOffset += {bitlen};\n"
                    elif value_type.category == value_type.CATEGORY_COMPOUND:
                        js_code += f"            let {field.name}Msg = {value_type.full_name.replace('.', '_')}.unpack(data, false, msg.bitOffset)\n"
                        js_code += f"            msg.fields['{field.name}'].items.push(new CompoundType({field.name}Msg, null));\n"
                        js_code += f"            msg.bitOffset = {field.name}Msg.bitOffset;\n"
                    else:
                        raise ValueError(f"Unsupported value category: {vars(value_type)}")
                    js_code += f"        }}\n\n"
                else:
                    raise ValueError(f"Unsupported array mode: {field.type.mode}")
            elif field.type.category == field.type.CATEGORY_COMPOUND:
                js_code += f"        let {field.name}Msg = {field.type.full_name.replace('.', '_')}.unpack(data, {get_tao(index, fields)}, msg.bitOffset)\n"
                # js_code += f"        msg.fields['{field.name}'] = new CompoundType({field.name}Msg, null);\n"
                js_code += f"        msg.fields['{field.name}'].msg = {field.name}Msg;\n"
                js_code += f"        msg.bitOffset = {field.name}Msg.bitOffset;\n"
            elif field.type.category == field.type.CATEGORY_PRIMITIVE:
                value_type = field.type 
                bitlen = value_type.bitlen
                js_code += f"        let {field.name}_field = {generate_primitive_type_instance(value_type, bitlen)};\n"
                js_code += f"        msg.fields['{field.name}'].value = {field.name}_field.value\n"
                js_code += f"        msg.bitOffset += {bitlen};\n"
            elif field.type.category == field.type.CATEGORY_VOID:
                js_code += f"        msg.bitOffset += {field.type.bitlen}; //field.type.CATEGORY_VOID {field.type} for Reserved space\n"
            else:
                raise ValueError(f"Unsupported category: {field.type.category}")
    js_code += "        return msg;\n"
    js_code += "    }\n"
    js_code += "\n"
    return js_code