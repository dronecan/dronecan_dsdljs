const assert = require('node:assert/strict');
const dgram = require('node:dgram');
const test = require('node:test');

test('importing the package exposes the library without starting the UDP example', t => {
    t.mock.method(dgram, 'createSocket', () => assert.fail('library import opened a UDP socket'));
    const { Node, DSDL, parseFrameMessage } = require('..');
    assert.equal(typeof Node, 'function');
    const status = parseFrameMessage(341, Buffer.from('78563412003412', 'hex'));
    assert.ok(status instanceof DSDL.uavcan_protocol_NodeStatus);
    assert.equal(status.toObj().uptime_sec, 0x12345678);
    assert.equal(status.toObj().vendor_specific_status_code, 0x1234);
});
