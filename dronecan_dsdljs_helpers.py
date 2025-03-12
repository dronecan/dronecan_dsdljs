#!/usr/bin/env python
# encoding: utf-8
'''
    Author: Huibean Luo <huibean.luo@vimdrones.com>
'''

import os
from common import get_primitive_kind, get_compound_kind
from dronecan_dsdljs_pack_generator import generate_pack_method
from dronecan_dsdljs_unpack_generator import generate_unpack_method

STRING_FIELDS = ['name']

def generate_js_class(message, fields, serviceTypeId=None):
    if (message.default_dtid is None):
        js_kind = 'CompoundType.KIND_SERVICE'
    else:
        js_kind = 'CompoundType.KIND_MESSAGE'

    union = getattr(message, 'union', None) is True
    if (union):
        js_union = 'true'
    else:
        js_union = 'false'

    if serviceTypeId == 'request':
        js_class_name = message.full_name.replace('.', '_') + "_Request"
    elif serviceTypeId == 'response':
        js_class_name = message.full_name.replace('.', '_') + "_Response"
    else:
        js_class_name = message.full_name.replace('.', '_')
    js_code = f"// JavaScript binding for {message.full_name}\n"
    js_code += "// Auto Generated Code, DO NOT MODIFY\n"
    constants = {}
    if hasattr(message, 'constants'):
        for constant in message.constants:
            field_name = None 
            if len(message.fields) == 1:
                field_name = message.fields[0].name.lower()
                constant_name = constant.name 
            else:
                for field in message.fields:
                    if field.name is None:
                        continue
                    if constant.name.startswith(field.name.upper()):
                        field_name = field.name
                        constant_name = constant.name[len(field_name + '_'):]

            if field_name:
                if constants.get(field_name, None) is None:
                    constants[field_name] = {}
                constants[field_name][constant_name] = constant.value

    js_code += f"const {js_class_name} = class {{\n"

    if message.default_dtid is not None:
        js_code += f"    static DTID = {message.default_dtid};\n"
    else:
        js_code += f"    static DTID = null;\n"
    js_code += f"    static FULL_NAME = '{message.full_name}';\n"
    js_code += f"    static CONSTANTS = {constants};\n"

    if getattr(message, 'request_fields', None) is not None:
        # fields = message.request_fields
        js_code += f"    static MAX_BIT_LEN = {message.get_max_bitlen_request()};\n"
        js_code += f"    static MIN_BIT_LEN = {message.get_min_bitlen_request()};\n"
    elif getattr(message, 'response_fields', None) is not None:
        # fields = message.response_fields
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
        union_size = len(message.fields).bit_length() 
        js_code += f"        this.unionFieldIndex = new PrimitiveType(0, PrimitiveType.KIND_UNSIGNED_INT, {union_size} );\n"
        union_fields = [] 
        for field in fields:
            union_fields.append(f"'{field.name}'")
        js_code += f"        this.unionFields = [{(',').join(union_fields)}];\n"
    else:
        for field in fields:
            if field.name is None:
                continue
            if (field.type.category == field.type.CATEGORY_PRIMITIVE):
                js_code += f"        this.fields['{field.name}'] = new PrimitiveType(null, {get_primitive_kind(field.type)}, {field.type.bitlen});\n"
            elif (field.type.category == field.type.CATEGORY_COMPOUND):
                js_code += f"        this.fields['{field.name}'] = new CompoundType({field.type.full_name.replace('.', '_')}.sampleMessage(), {get_compound_kind(field.type)}, null);\n"
            elif (field.type.category == field.type.CATEGORY_ARRAY):
                value_type = field.type.value_type
                if (field.type.mode == field.type.MODE_STATIC):
                    if value_type.category == value_type.CATEGORY_PRIMITIVE:
                        js_code += f"        this.fields['{field.name}'] = new ArrayType(new PrimitiveType(null, {get_primitive_kind(value_type)}, {value_type.bitlen}), ArrayType.MODE_STATIC, {field.type.max_size} );\n"
                    elif value_type.category == value_type.CATEGORY_COMPOUND:
                        js_code += f"        this.fields['{field.name}'] = new ArrayType(new CompoundType({value_type.full_name.replace('.', '_')}.sampleMessage(), ArrayType.MODE_DYNAMIC, {field.type.max_size}, ArrayType.MODE_STATIC, {field.type.max_size});\n"
                    else:
                        raise ValueError(f"Unsupported value category: {vars(value_type)}")
                elif (field.type.mode == field.type.MODE_DYNAMIC):
                    if value_type.category == value_type.CATEGORY_PRIMITIVE:
                        js_code += f"        this.fields['{field.name}'] = new ArrayType(new PrimitiveType(null, {get_primitive_kind(value_type)}, {value_type.bitlen}), ArrayType.MODE_DYNAMIC, {field.type.max_size} );\n"
                    elif value_type.category == value_type.CATEGORY_COMPOUND:
                        js_code += f"        this.fields['{field.name}'] = new ArrayType({value_type.full_name.replace('.', '_')}.sampleMessage(), ArrayType.MODE_DYNAMIC, {field.type.max_size});\n"
                    else:
                        raise ValueError(f"Unsupported value category: {vars(value_type)})")
                else:
                    raise ValueError(f"Unsupported array mode: {field.type.mode}")
            # js_code += f"        this.{field.name} = new ArrayType(new PrimitiveType(null, {get_primitive_kind(value_type)}, {value_type.bitlen}), ArrayType.MODE_STATIC, {field.type.max_size} );\n"
            else:
                js_code += f"        this.fields['{field.name}'] = null; // {field.type}\n"

    js_code += f"    }}\n\n"
    js_code += generate_unpack_method(message, fields)
    js_code += generate_pack_method(message, fields)

    js_code += f"    toObj() {{\n"
    js_code += f"        const obj = {{}};\n"
    for field in fields:
        if field.type.category == field.type.CATEGORY_PRIMITIVE:
            js_code += f"        obj['{field.name}'] = Number(this.fields['{field.name}'].value);\n"
        elif field.type.category == field.type.CATEGORY_COMPOUND:
            js_code += f"        obj['{field.name}'] = this.fields['{field.name}'].toObj();\n"
        elif field.type.category == field.type.CATEGORY_ARRAY:
            if (field.name == 'name' or field.name == 'text'): 
                force_array = 'false'
            else:
                force_array = 'true' 
            js_code += f"        obj['{field.name}'] = this.fields['{field.name}'].toObj({force_array});\n"
        elif field.type.category == field.type.CATEGORY_VOID:
            continue
        else:
            raise ValueError(f"Unsupported category: {field.type.category}")
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
    js_code += f"        if (this.unionFieldIndex === null) return null;\n"
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

    js_code += f"    static getDataTypeSignature() {{\n"
    js_code += f"        return {message.get_data_type_signature()}n;\n"
    js_code += f"    }}\n\n"

    js_code += f"    getDataTypeSignature() {{\n"
    js_code += f"        return {message.get_data_type_signature()}n;\n"
    js_code += f"    }}\n\n"

    js_code += f"}};\n"
    js_code += f"module.exports.{js_class_name} = {js_class_name};\n"

    return js_code

def generate_dronecan_js(output_dir, messages):
    js_code = "// DroneCAN Generated JavaScript bindings via dronecan_dsdljs\n\n"
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

function bitsToArrayLength(bits) {
    let length = 0;
    for (let i = 0; i < bits.length; i++) {
        length = (length << 1) | bits[i];
    }
    return length;
}

function arrayLengthToBits(length, bitlen) {
    let bits = [];
    for (let i = 0; i < bitlen; i++) {
        bits[bitlen - i - 1] = (length >> i) & 1;
    }
    return bits;
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
        if not hasattr(message, 'response_fields') and not hasattr(message, 'response_fields'):
            continue
        js_class_name = message.full_name.replace('.', '_')
        js_code += f"services[{message.default_dtid}] = {{'request': {js_class_name}_Request, 'response': {js_class_name}_Response}};\n"
    js_code += "module.exports.services = services;\n"

    output_file = os.path.join(output_dir, "dsdl.js")
    with open(output_file, 'w') as f:
        f.write(js_code)
    print(f"Generated {output_file}")