const assert = require('node:assert/strict');
const test = require('node:test');
const DSDL = require('../dronecan/dsdl');

function wire(bits) {
    const bytes = Buffer.alloc(Math.ceil(bits.length / 8));
    bits.forEach((bit, i) => { bytes[i >> 3] |= bit << (7 - i % 8); });
    return bytes.toString('hex');
}

// Interoperability vectors produced independently by PyDroneCAN.
test('Fix2 consumes its optional ECEF solution including the element array lengths', () => {
    const payload = Buffer.from('00'.repeat(62) + '0b0000000160000000210000000000', 'hex');
    const fix = DSDL.uavcan_equipment_gnss_Fix2.unpack(payload);
    assert.equal(fix.bitOffset, payload.length * 8);
    assert.deepEqual(fix.toObj().ecef_position_velocity[0].position_xyz_mm, [11, 22, 33]);
    assert.equal(wire(fix.pack()), payload.toString('hex'));
});

test('explicit nine-bit array lengths use little-endian chunks and enforce capacity', () => {
    const Message = DSDL.ardupilot_gnss_MovingBaselineData;
    const msg = new Message();
    msg.fields.data.fromString('A');
    assert.equal(wire(msg.pack(false)), '012080');
    assert.deepEqual(Message.unpack(Buffer.from('012080', 'hex'), false).toObj().data, [65]);
    msg.fields.data.items = Array(301).fill(msg.fields.data.items[0]);
    assert.throws(() => msg.pack(), RangeError);
    assert.throws(() => Message.unpack(Buffer.alloc(301)), RangeError);
});

test('an explicit parent propagates TAO mode to its nested final path', () => {
    const Request = DSDL.uavcan_protocol_file_Read_Request;
    const req = new Request();
    req.fields.path.fields.path.fromString('A');
    assert.equal(wire(req.pack(false)), '00000000000141');
    assert.equal(wire(req.pack(true)), '000000000041');
    const decoded = Request.unpack(Buffer.from('00000000000141', 'hex'), false);
    assert.equal(decoded.fields.path.fields.path.toString(), 'A');
});

test('only the active parameter arm is converted, including a default empty parameter', () => {
    const Response = DSDL.uavcan_protocol_param_GetSet_Response;
    const empty = new Response();
    assert.ok(Object.hasOwn(empty.toObj().value, 'empty'));
    assert.doesNotThrow(() => empty.pack());
    const decoded = Response.unpack(Buffer.from('012a0000000000000000000041', 'hex'));
    assert.equal(decoded.toObj().value.integer_value, 42);
    assert.equal(decoded.toObj().value.empty, undefined);
    const Value = DSDL.uavcan_protocol_param_Value;
    const str = Value.unpack(Buffer.from('8820', 'hex'));
    assert.equal(str.unionField.toString(), 'A');
    assert.equal(str.bitOffset, 11);
    assert.equal(wire(str.pack()), '8820');
});
