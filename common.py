#!/usr/bin/env python
# encoding: utf-8
'''
    Author: Huibean Luo <huibean.luo@vimdrones.com>
'''

def get_cast_mode(type):
    if type.cast_mode == type.CAST_MODE_TRUNCATED:
        return "PrimitiveType.CAST_MODE_TRUNCATED"
    elif type.cast_mode == type.CAST_MODE_SATURATED:
        return "PrimitiveType.CAST_MODE_SATURATED"
    else:
        raise ValueError(f"Unsupported cast mode: {type.cast_mode}")

def get_compound_kind(type):
    if type.kind == type.KIND_MESSAGE:
        return "CompoundType.KIND_MESSAGE"
    elif type.kind == type.KIND_SERVICE:
        return "CompoundType.KIND_SERVICE"
    else:
        raise ValueError(f"Unsupported compound kind: {type.kind}") 

def get_primitive_kind(type):
    if type.kind == type.KIND_BOOLEAN:
        return "PrimitiveType.KIND_BOOLEAN"
    elif type.kind == type.KIND_UNSIGNED_INT:
        return "PrimitiveType.KIND_UNSIGNED_INT"
    elif type.kind == type.KIND_SIGNED_INT:
        return "PrimitiveType.KIND_SIGNED_INT"
    elif type.kind == type.KIND_FLOAT:
        return "PrimitiveType.KIND_FLOAT"
    else:
        raise ValueError(f"Unsupported primitive kind: {type.kind}")

def generate_primitive_type_instance(value_type, bitlen):
    bits = f"data.getBits(msg.bitOffset, {bitlen})"
    if value_type.kind == value_type.KIND_BOOLEAN:
        return f"PrimitiveType.unpack(PrimitiveType.KIND_BOOLEAN, {bits}, {bitlen})" 
    elif value_type.kind == value_type.KIND_UNSIGNED_INT:
        return f"PrimitiveType.unpack(PrimitiveType.KIND_UNSIGNED_INT, {bits}, {bitlen}, {get_cast_mode(value_type)})"
    elif value_type.kind == value_type.KIND_SIGNED_INT:
        return f"PrimitiveType.unpack(PrimitiveType.KIND_SIGNED_INT, {bits}, {bitlen}, {get_cast_mode(value_type)})"
    elif value_type.kind == value_type.KIND_FLOAT:
        return f"PrimitiveType.unpack(PrimitiveType.KIND_FLOAT, {bits}, {bitlen})"
    else:
        raise NotImplementedError(f"Unsupported kind: {value_type.kind}")

def get_tao(index, fields):
    if index == len(fields) - 1:
        return 'true'
    else:
        return 'false'

