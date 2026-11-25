const assert = require('node:assert/strict');
const test = require('node:test');
const {
    uavcan_protocol_file_Read_Request: ReadRequest,
    uavcan_protocol_file_Read_Response: ReadResponse,
} = require('../dronecan/dsdl');
const PrimitiveType = require('../dronecan/primitive_type');

test('File.Read uses distinct request and response bit lengths', () => {
    assert.equal(ReadRequest.MIN_BIT_LEN, 40);
    assert.equal(ReadRequest.MAX_BIT_LEN, 1648);
    assert.equal(ReadResponse.MIN_BIT_LEN, 16);
    assert.equal(ReadResponse.MAX_BIT_LEN, 2073);
});

test('File.Read encodes an empty EOF response and short final chunks', () => {
    const response = new ReadResponse();
    response.fields.error.msg.fields.value.value = 0;
    assert.equal(response.pack().length, 16);
    for (const size of [1, 2]) {
        response.fields.data.push(new PrimitiveType(size, PrimitiveType.KIND_UNSIGNED_INT, 8));
        assert.equal(response.pack().length, 16 + size * 8);
    }
});
