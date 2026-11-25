#!/usr/bin/env python
# encoding: utf-8
'''
    Author: Huibean Luo <huibean.luo@vimdrones.com>
'''

import json
import os
from tempfile import TemporaryDirectory
from binding_info import binding_info
from common import get_primitive_kind, get_compound_kind, get_cast_mode
from dronecan_dsdljs_pack_generator import generate_pack_method
from dronecan_dsdljs_unpack_generator import generate_unpack_method

def field_constructor(t):
    if t.category == t.CATEGORY_PRIMITIVE:
        return f"new PrimitiveType(0, {get_primitive_kind(t)}, {t.bitlen}, {get_cast_mode(t)})"
    if t.category == t.CATEGORY_COMPOUND:
        name = t.full_name.replace('.', '_')
        return f"new CompoundType(new {name}(), {get_compound_kind(t)})"
    if t.category == t.CATEGORY_ARRAY:
        mode = 'MODE_DYNAMIC' if t.mode == t.MODE_DYNAMIC else 'MODE_STATIC'
        return f"new ArrayType({field_constructor(t.value_type)}, ArrayType.{mode}, {t.max_size})"
    raise ValueError(f"Unsupported field type: {t}")


def generate_js_class(message, fields, serviceTypeId=None):
    js_kind = get_compound_kind(message)
    union = getattr(message, serviceTypeId + '_union' if serviceTypeId else 'union')
    js_union = 'true' if union else 'false'

    if serviceTypeId == 'request':
        js_class_name = message.full_name.replace('.', '_') + "_Request"
    elif serviceTypeId == 'response':
        js_class_name = message.full_name.replace('.', '_') + "_Response"
    else:
        js_class_name = message.full_name.replace('.', '_')
    js_code = f"// JavaScript binding for {message.full_name}\n"
    js_code += "// Auto Generated Code, DO NOT MODIFY\n"
    constants = {}
    field_names = sorted((field.name for field in fields if field.name), key=len, reverse=True)
    for constant in getattr(message, serviceTypeId + '_constants' if serviceTypeId else 'constants'):
        for field_name in field_names:
            if len(fields) == 1 or constant.name.startswith(field_name.upper() + '_'):
                name = constant.name if len(fields) == 1 else constant.name[len(field_name) + 1:]
                value = constant.value
                # Match the Number/BigInt representation used by PrimitiveType.toObj().
                if isinstance(value, int) and abs(value) > 2**53 - 1:
                    literal = f"{value}n"
                else:
                    literal = json.dumps(value)
                constants.setdefault(field_name, []).append(f"{name!r}: {literal}")
                break

    js_code += f"const {js_class_name} = class {{\n"

    if message.default_dtid is not None:
        js_code += f"    static DTID = {message.default_dtid};\n"
    else:
        js_code += f"    static DTID = null;\n"
    js_code += f"    static FULL_NAME = '{message.full_name}';\n"
    groups = [f"{name!r}: {{{', '.join(values)}}}" for name, values in constants.items()]
    js_code += "    static CONSTANTS = {" + ", ".join(groups) + "};\n"

    if serviceTypeId == 'request':
        js_code += f"    static MAX_BIT_LEN = {message.get_max_bitlen_request()};\n"
        js_code += f"    static MIN_BIT_LEN = {message.get_min_bitlen_request()};\n"
    elif serviceTypeId == 'response':
        js_code += f"    static MAX_BIT_LEN = {message.get_max_bitlen_response()};\n"
        js_code += f"    static MIN_BIT_LEN = {message.get_min_bitlen_response()};\n"
    elif getattr(message, 'fields', None) is not None:
        # fields = message.fields
        js_code += f"    static MAX_BIT_LEN = {message.get_max_bitlen()};\n"
        js_code += f"    static MIN_BIT_LEN = {message.get_min_bitlen()};\n"
    else:
        raise ValueError("No fields found in message")

    js_code += f"    constructor() {{\n"

    js_code += f"        this.kind = {js_kind};\n"
    js_code += f"        this.union = {js_union};\n"
    js_code += f"        this.fields = {{}};\n"

    if union:
        union_size = max(1, (len(fields) - 1).bit_length())
        js_code += f"        this.unionFieldIndex = new PrimitiveType(0, PrimitiveType.KIND_UNSIGNED_INT, {union_size});\n"
        js_code += f"        this.unionFields = {json.dumps([field.name for field in fields])};\n"
    for field in fields:
        if field.name is not None:
            js_code += f"        this.fields['{field.name}'] = {field_constructor(field.type)};\n"
    js_code += "    }\n\n"
    js_code += generate_unpack_method(fields, union)
    js_code += generate_pack_method(fields, union)

    js_code += "    toObj() {\n"
    js_code += "        const obj = {};\n"
    if union:
        js_code += "        const name = this.unionFields[this.unionFieldIndex.value];\n"
        js_code += "        obj[name] = this.fields[name].toObj(name !== 'name' && name !== 'text');\n"
    else:
        for field in fields:
            if field.name is None:
                continue
            arg = ''
            if field.type.category == field.type.CATEGORY_ARRAY:
                arg = 'false' if field.name in ('name', 'text') else 'true'
            js_code += f"        obj['{field.name}'] = this.fields['{field.name}'].toObj({arg});\n"
    js_code += f"        obj.getConstant = function(fieldName) {{\n"
    js_code += f"            const constants = {js_class_name}.CONSTANTS;\n"
    js_code += f"            const value = this[fieldName];\n"
    js_code += f"            if (constants[fieldName]) {{\n"
    js_code += f"                for (const [key, val] of Object.entries(constants[fieldName])) {{\n"
    js_code += f"                    if (val === value) return key;\n"
    js_code += f"                }}\n"
    js_code += f"            }}\n"
    js_code += f"            return '';\n"
    js_code += f"        }}\n"
    js_code += f"        return obj;\n"
    js_code += f"    }}\n\n"

    js_code += f"    get unionField() {{\n"
    js_code += f"        if (!this.unionFieldIndex) return null;\n"
    js_code += f"        const unionField = this.unionFields[this.unionFieldIndex.value];\n"
    js_code += f"        return this.fields[unionField];\n"
    js_code += f"    }}\n\n"

    js_code += f"    get dataTypeId() {{\n"
    js_code += f"        return {js_class_name}.DTID;\n"
    js_code += f"    }}\n\n"

    js_code += f"    get name() {{\n"
    js_code += f"        return {js_class_name}.FULL_NAME;\n"
    js_code += f"    }}\n\n"

    js_code += f"    get fieldNames() {{\n"
    js_code += f"        return [\n"
    for field in fields:
        if field.name is None:
            continue
        js_code += f"            '{field.name}',\n"
    js_code += f"        ];\n"
    js_code += f"    }}\n\n"

    js_code += f"    static sampleMessage() {{\n"
    js_code += f"        const msg = new {js_class_name}();\n"
    js_code += f"        // Initialize fields with sample values\n"
    js_code += f"        return msg;\n"
    js_code += f"    }}\n\n"

    js_code += f"    static calculateBufferSize() {{\n"
    js_code += f"        return Math.ceil(this.MAX_BIT_LEN / 8);\n"
    js_code += f"    }}\n\n"

    js_code += f"    getDsdlSignature() {{ return {message.get_dsdl_signature()}n; }}\n"
    source = json.dumps(message.get_dsdl_signature_source_definition())
    js_code += f"    getDsdlSignatureSourceDefinition() {{ return {source}; }}\n\n"

    js_code += f"    static getDataTypeSignature() {{\n"
    js_code += f"        return {message.get_data_type_signature()}n;\n"
    js_code += f"    }}\n\n"

    js_code += f"    getDataTypeSignature() {{\n"
    js_code += f"        return {message.get_data_type_signature()}n;\n"
    js_code += f"    }}\n\n"

    js_code += f"}};\n"
    js_code += f"module.exports.{js_class_name} = {js_class_name};\n"

    return js_code

def generate_dronecan_js(output_dir, messages, *, uses_default_dsdl=False):
    messages = list(messages)
    js_code = "// DroneCAN Generated JavaScript bindings via dronecan_dsdljs\n\n"
    info = binding_info(messages)
    info['usesDefaultDsdl'] = uses_default_dsdl
    metadata = json.dumps(info, ensure_ascii=True, indent=2)
    # Keep Object.keys(DSDL) compatible with consumers that enumerate types and registries.
    js_code += f'Object.defineProperty(module.exports, "bindingInfo", {{ value: {metadata} }});\n'
    js_code += """
const Type = require('./type');
const PrimitiveType = require('./primitive_type');
const ArrayType = require('./array_type');
const CompoundType = require('./compound_type');
const VoidType = require('./void_type');
var Buffer = require('buffer').Buffer;

Buffer.prototype.getBit = function (bitOffset) {
    const byteIndex = Math.floor(bitOffset / 8);
    const bitPosition = bitOffset % 8;

    if (byteIndex >= this.length) {
        throw new RangeError("getBit: bitOffset out of range");
    }

    return (this[byteIndex] >> (7 - bitPosition)) & 1;
};

Buffer.prototype.getBitsString = function (bitOffset, bitlen) {
    if (bitlen <= 0 || bitlen > 64) {
        throw new RangeError("getBits: bitlen out of range, must be 1-64");
    }
    let bitsString = "";

    for (let i = 0; i < bitlen; i++) {
        bitsString += this.getBit(bitOffset + i).toString();
    }

    return bitsString;
};

Buffer.prototype.getBits = function (bitOffset, bitlen) {
    if (bitlen <= 0 || bitlen > 64) {
        throw new RangeError("getBits: bitlen out of range, must be 1-64");
    }
    let bits = new Uint8Array(bitlen);

    for (let i = 0; i < bitlen; i++) {
        bits[i] = this.getBit(bitOffset + i);
    }
    return bits;
}

function skipBits(data, msg, count) {
    if (msg.bitOffset + count > data.length * 8) throw new RangeError('Truncated DSDL field');
    msg.bitOffset += count;
}

function readPrimitive(data, msg, kind, width, mode) {
    const bits = data.getBits(msg.bitOffset, width);
    msg.bitOffset += width;
    return PrimitiveType.unpack(kind, bits, width, mode);
}

function readCompound(data, msg, Message, kind, tao) {
    const child = Message.unpack(data, tao, msg.bitOffset);
    msg.bitOffset = child.bitOffset;
    return new CompoundType(child, kind);
}

function appendTag(bits, tag, width) {
    for (let i = width - 1; i >= 0; i--) bits.push(Math.floor(tag / 2 ** i) % 2);
}

function readTag(data, msg, width) {
    let tag = 0;
    for (const bit of data.getBits(msg.bitOffset, width)) tag = tag * 2 + bit;
    msg.bitOffset += width;
    return tag;
}

function packArray(bits, items, maxSize, countWidth, minElementBits, tao) {
    if (items.length > maxSize || (countWidth === 0 && items.length !== maxSize)) {
        throw new RangeError('Array length outside DSDL bounds');
    }
    const implicitLength = countWidth > 0 && tao && minElementBits >= 8;
    if (countWidth > 0 && !implicitLength) {
        const length = new PrimitiveType(items.length, PrimitiveType.KIND_UNSIGNED_INT, countWidth);
        bits.push(...length.pack());
    }
    for (let i = 0; i < items.length; i++) {
        const elementTao = tao && !implicitLength && i === items.length - 1;
        for (const bit of items[i].pack(elementTao)) bits.push(bit);
    }
}

function readArray(data, msg, maxSize, countWidth, minElementBits, tao, readElement) {
    const items = [];
    if (countWidth > 0 && tao && minElementBits >= 8) {
        // Omitted-length elements carry their own lengths. Up to seven final pad bits remain.
        while (data.length * 8 - msg.bitOffset >= 8) {
            if (items.length >= maxSize) throw new RangeError('Array exceeds DSDL maximum length');
            items.push(readElement(false));
        }
    } else {
        const count = countWidth === 0 ? maxSize : readPrimitive(data, msg,
            PrimitiveType.KIND_UNSIGNED_INT, countWidth, PrimitiveType.CAST_MODE_SATURATED).value;
        if (count > maxSize) throw new RangeError('Array exceeds DSDL maximum length');
        for (let i = 0; i < count; i++) items.push(readElement(tao && i === count - 1));
    }
    return items;
}
"""

    for message in messages:
        if getattr(message, 'fields', None) is not None:
            fields = message.fields
            class_code = generate_js_class(message, fields)
            js_code += class_code + "\n"
        else:
            request_fields = getattr(message, 'request_fields', None)   
            response_fields = getattr(message, 'response_fields', None)
            if (request_fields is None or response_fields is None):
                print(request_fields)
                print(response_fields)
                raise ValueError(f"Message {message.full_name} has no fields")

            class_code = generate_js_class(message, request_fields, 'request')
            js_code += class_code + "\n"
            class_code = generate_js_class(message, response_fields, 'response')
            js_code += class_code + "\n"

    js_code += "const messages = {};\n"
    for message in messages:
        if message.default_dtid is None:
            continue
        if not hasattr(message, 'fields'):
            continue
        js_class_name = message.full_name.replace('.', '_')
        js_code += f"messages[{message.default_dtid}] = {js_class_name};\n"
    js_code += "module.exports.messages = messages;\n"

    js_code += "const services = {};\n"
    for message in messages:
        if message.default_dtid is None:
            continue
        if not hasattr(message, 'response_fields'):
            continue
        js_class_name = message.full_name.replace('.', '_')
        js_code += f"services[{message.default_dtid}] = {{'request': {js_class_name}_Request, 'response': {js_class_name}_Response}};\n"
    js_code += "module.exports.services = services;\n"

    output_file = os.path.join(output_dir, "dsdl.js")
    with TemporaryDirectory(dir=output_dir) as staging:
        staged_file = os.path.join(staging, 'dsdl.js')
        with open(staged_file, 'w', encoding='utf-8') as f:
            f.write(js_code)
        os.replace(staged_file, output_file)
    print(f"Generated {output_file}")
