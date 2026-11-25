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
