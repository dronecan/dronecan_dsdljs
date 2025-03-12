#!/usr/bin/env python
# encoding: utf-8
'''
    Author: Huibean Luo <huibean.luo@vimdrones.com>
'''

from common import get_cast_mode

def generate_primitive_type_pack(value_type, field_name):
    if value_type.kind == value_type.KIND_BOOLEAN:
        return f"PrimitiveType.pack(PrimitiveType.KIND_BOOLEAN, this.{field_name}, {value_type.bitlen})"
    elif value_type.kind == value_type.KIND_UNSIGNED_INT:
        return f"PrimitiveType.pack(PrimitiveType.KIND_UNSIGNED_INT, this.{field_name}, {value_type.bitlen}, {get_cast_mode(value_type)})"
    elif value_type.kind == value_type.KIND_SIGNED_INT:
        return f"PrimitiveType.pack(PrimitiveType.KIND_SIGNED_INT, this.{field_name}, {value_type.bitlen}, {get_cast_mode(value_type)})"
    elif value_type.kind == value_type.KIND_FLOAT:
        return f"PrimitiveType.pack(PrimitiveType.KIND_FLOAT, this.{field_name}, {value_type.bitlen})"
    else:
        raise NotImplementedError(f"Unsupported kind: {value_type.kind}")

def generate_pack_method(message, fields):
    js_code = "    pack(tao=true) {\n"
    js_code += "        let bits = [];\n"

    if getattr(message, 'union', None) is True:
        js_code += f"        let unionFieldLength = {len(message.fields).bit_length()};\n"
        js_code += f"        let unionFieldBits = arrayLengthToBits(this.unionFieldIndex.value, unionFieldLength);\n"
        js_code += f"        bits = bits.concat(unionFieldBits);\n"
        js_code += f"        switch (this.unionFieldIndex.value) {{\n"
        for index, field in enumerate(fields):
            if field.type.category == field.type.CATEGORY_ARRAY:
                # Array type
                if field.type.mode == field.type.MODE_STATIC:
                    # Static array
                    value_type = field.type.value_type 
                    js_code += f"        case {index}:\n"
                    js_code += f"            const {field.name}_length = {field.type.max_size};\n"
                    js_code += f"            for (let i = 0; i < {field.name}_length; i++) {{\n"
                    if value_type.category == value_type.CATEGORY_PRIMITIVE:
                        js_code += f"                let {field.name}_bits = this.fields.{field.name}.items[i].pack();\n"
                        js_code += f"                bits = bits.concat({field.name}_bits);\n"
                    elif value_type.category == value_type.CATEGORY_COMPOUND:
                        js_code += f"                let {field.name}Msg_bits = this.fields.{field.name}.items[i].pack();\n"
                        js_code += f"                bits = bits.concat({field.name}Msg_bits);\n"
                    else:
                        raise ValueError(f"Unsupported value category: {vars(value_type)}")
                    js_code += f"            }}\n\n"
                elif field.type.mode == field.type.MODE_DYNAMIC:
                    value_type = field.type.value_type 
                    # Dynamic array
                    js_code += f"        case {index}:\n"
                    js_code += f"            const {field.name}_length = this.fields.{field.name}.length;\n"
                    array_length_bitlen = field.type.max_size.bit_length()
                    js_code += f"            if (this.fields.{field.name}.length > {field.name}_length) {{\n"
                    js_code += f"                throw new Error(`Array length of {field.name} exceeds maximum length of {field.name}_length`);\n"
                    js_code += f"            }}\n"
                    if index != len(fields) - 1:
                        js_code += f"            let {field.name}_length_bits = arrayLengthToBits(this.fields.{field.name}.length, {array_length_bitlen});\n"
                        js_code += f"            bits = bits.concat({field.name}_length_bits);\n"
                    else:
                        js_code += f"            if (!tao) {{\n"
                        js_code += f"                let {field.name}_length_bits = arrayLengthToBits(this.fields.{field.name}.length, {array_length_bitlen});\n"
                        js_code += f"                bits = bits.concat({field.name}_length_bits);\n"
                        js_code += f"            }}\n"

                    js_code += f"            for (let i = 0; i < {field.name}_length; i++) {{\n"
                    if value_type.category == value_type.CATEGORY_PRIMITIVE:
                        bitlen = value_type.bitlen
                        js_code += f"                let {field.name}_bits = this.fields.{field.name}.items[i].pack();\n"
                        js_code += f"                bits = bits.concat({field.name}_bits);\n"
                    elif value_type.category == value_type.CATEGORY_COMPOUND:
                        js_code += f"                let {field.name}Msg_bits = this.fields.{field.name}.items[i].pack();\n"
                        js_code += f"                bits = bits.concat({field.name}Msg_bits);\n"
                    else:
                        raise ValueError(f"Unsupported value category: {vars(value_type)}")
                    js_code += f"            }}\n\n"
                else:
                    raise ValueError(f"Unsupported array mode: {field.type.mode}")
            elif field.type.category == field.type.CATEGORY_COMPOUND:
                js_code += f"        case {index}:\n"
                js_code += f"            let {field.name}Msg_bits = this.fields.{field.name}.pack();\n"
                js_code += f"            bits = bits.concat({field.name}Msg_bits);\n"
            elif field.type.category == field.type.CATEGORY_PRIMITIVE:
                value_type = field.type 
                js_code += f"        case {index}:\n"
                js_code += f"            let {field.name}_bits = this.fields.{field.name}.pack();\n"
                js_code += f"            bits = bits.concat({field.name}_bits);\n"
            elif field.type.category == field.type.CATEGORY_VOID:
                js_code += f"        case {index}:\n"
                js_code += f"            for (let j = 0; j < {field.type.bitlen}; j++) {{\n"
                js_code += f"                bits.push(0);\n"
                js_code += f"            }}\n"
            else:
                raise ValueError(f"Unsupported category: {field.type.category}")

            js_code += f"                break;\n"
        js_code += f"        default:\n"
        js_code += f"            throw new Error(`Invalid union field index: ${{this.unionFieldIndex.value}}`);\n"
        js_code += f"        }}\n"
    else:
        for index, field in enumerate(fields):
            if field.type.category == field.type.CATEGORY_ARRAY:
                # Array type
                if field.type.mode == field.type.MODE_STATIC:
                    # Static array
                    value_type = field.type.value_type 
                    js_code += f"        // Encode static array field {field.name}\n"
                    js_code += f"        const {field.name}_length = {field.type.max_size};\n"
                    js_code += f"        for (let i = 0; i < {field.name}_length; i++) {{\n"
                    if value_type.category == value_type.CATEGORY_PRIMITIVE:
                        js_code += f"            let {field.name}_bits = this.fields.{field.name}.items[i].pack();\n"
                        js_code += f"            bits = bits.concat({field.name}_bits);\n"
                    elif value_type.category == value_type.CATEGORY_COMPOUND:
                        js_code += f"            let {field.name}Msg_bits = this.fields.{field.name}.items[i].pack();\n"
                        js_code += f"            bits = bits.concat({field.name}Msg_bits);\n"
                    else:
                        raise ValueError(f"Unsupported value category: {vars(value_type)}")
                    js_code += f"        }}\n\n"

                elif field.type.mode == field.type.MODE_DYNAMIC:
                    value_type = field.type.value_type 
                    # Dynamic array
                    js_code += f"        // Encode dynamic array field {field.name}\n"
                    js_code += f"        const {field.name}_length = this.fields.{field.name}.length;\n"
                    array_length_bitlen = field.type.max_size.bit_length()
                    js_code += f"        if (this.fields.{field.name}.length > {field.name}_length) {{\n"
                    js_code += f"            throw new Error(`Array length of {field.name} exceeds maximum length of {field.name}_length`);\n"
                    js_code += f"        }}\n"
                    if index != len(fields) - 1:
                        js_code += f"        let {field.name}_length_bits = arrayLengthToBits(this.fields.{field.name}.length, {array_length_bitlen});\n"
                        js_code += f"        bits = bits.concat({field.name}_length_bits);\n"
                    else:
                        js_code += f"        if (!tao) {{\n"
                        js_code += f"           let {field.name}_length_bits = arrayLengthToBits(this.fields.{field.name}.length, {array_length_bitlen});\n"
                        js_code += f"           bits = bits.concat({field.name}_length_bits);\n"
                        js_code += f"        }}\n"

                    js_code += f"        for (let i = 0; i < {field.name}_length; i++) {{\n"
                    if value_type.category == value_type.CATEGORY_PRIMITIVE:
                        bitlen = value_type.bitlen
                        js_code += f"            let {field.name}_bits = this.fields.{field.name}.items[i].pack();\n"
                        js_code += f"            bits = bits.concat({field.name}_bits);\n"
                    elif value_type.category == value_type.CATEGORY_COMPOUND:
                        js_code += f"            let {field.name}Msg_bits = this.fields.{field.name}.items[i].pack();\n"
                        js_code += f"            bits = bits.concat({field.name}Msg_bits);\n"
                    else:
                        raise ValueError(f"Unsupported value category: {vars(value_type)}")
                    js_code += f"        }}\n\n"
                else:
                    raise ValueError(f"Unsupported array mode: {field.type.mode}")

            elif field.type.category == field.type.CATEGORY_COMPOUND:
                if index != len(fields) - 1: 
                    js_code += f"        let {field.name}Msg_bits = this.fields.{field.name}.pack(false);\n"
                else:
                    js_code += f"        let {field.name}Msg_bits = this.fields.{field.name}.pack();\n"
                js_code += f"        bits = bits.concat({field.name}Msg_bits);\n"
            elif field.type.category == field.type.CATEGORY_PRIMITIVE:
                value_type = field.type 
                js_code += f"        let {field.name}_bits = this.fields.{field.name}.pack();\n"
                js_code += f"        bits = bits.concat({field.name}_bits);\n"
            elif field.type.category == field.type.CATEGORY_VOID:
                js_code += f"        for (let j = 0; j < {field.type.bitlen}; j++) {{\n"
                js_code += f"            bits.push(0);\n"
                js_code += f"        }}\n"
            else:
                raise ValueError(f"Unsupported category: {field.type.category}")
        
        js_code += f"        if (bits.length <= this.constructor.MAX_BIT_LEN && bits.length >= this.constructor.MIN_BIT_LEN ) {{\n"
        js_code += f"            if (this.constructor.MAX_BIT_LEN === this.constructor.MIN_BIT_LEN && this.constructor.MAX_BIT_LEN !== bits.length) {{\n"
        js_code += f"                throw new Error(`Encoded message length is not equal to the fixed length of ${{this.constructor.MAX_BIT_LEN}}`);\n"
        js_code += f"            }}\n"
        js_code += f"        }} else if (this.constructor.MAX_BIT_LEN > 0 && bits.length <= this.constructor.MAX_BIT_LEN) {{\n"
        js_code += f"            throw new Error(`Encoded message length is less than minimum length of ${{this.constructor.MIN_BIT_LEN}}`);\n"
        js_code += f"        }}\n"
    js_code += f"        return bits;\n"
    js_code += "    }\n"
    js_code += "\n"
    return js_code