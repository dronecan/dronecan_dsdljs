const assert = require('node:assert/strict');
const dgram = require('node:dgram');
const { EventEmitter } = require('node:events');
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

function startExample(t) {
    const socket = new EventEmitter();
    const outgoing = [];
    socket.bind = () => {};
    socket.send = (bytes, offset, length) => outgoing.push(bytes.subarray(offset, offset + length));
    t.mock.method(dgram, 'createSocket', () => socket);

    delete require.cache[require.resolve('../examples/node_test')];
    require('../examples/node_test');
    const server = global.localNode;
    clearInterval(server.nodeStatusIntervalID);
    return { socket, outgoing, server };
}

test('the MAVLink example processes a heartbeat following a parser diagnostic', t => {
    const { socket, outgoing } = startExample(t);
    const { mavlink20, MAVLink20Processor } = require('../examples/mavlink');
    const diagnostic = new mavlink20.messages.bad_data(Buffer.alloc(0), 'Unrecognized message');
    const heartbeat = { _header: { msgId: mavlink20.MAVLINK_MSG_ID_HEARTBEAT, srcSystem: 42, srcComponent: 3 } };
    t.mock.method(MAVLink20Processor.prototype, 'parseBuffer', () => [diagnostic, heartbeat], { times: 1 });
    socket.emit('message', Buffer.alloc(0), { address: '127.0.0.1', port: 10000 });

    assert.equal(outgoing.length, 1);
    const decoder = new MAVLink20Processor(null, 42, 3);
    const [command] = decoder.parseBuffer(outgoing[0]);
    assert.equal(command.command, mavlink20.MAV_CMD_CAN_FORWARD);
    assert.equal(command.target_system, 42);
    assert.equal(command.target_component, 3);
});

test('the MAVLink example forwards addressed Classic and FD requests on the selected bus', t => {
    const { socket, outgoing, server } = startExample(t);
    const { mavlink20, MAVLink20Processor } = require('../examples/mavlink');
    const { Node, DSDL } = require('..');
    const client = new Node({ nodeId: 42 });
    clearInterval(client.nodeStatusIntervalID);
    const bus = 1;
    server.setBus(bus);
    client.setBus(bus);

    const encoder = new MAVLink20Processor(null, 1, 1);
    const decoder = new MAVLink20Processor(null, 42, 1);
    for (const canfd of [false, true]) {
        const Message = canfd ? mavlink20.messages.canfd_frame : mavlink20.messages.can_frame;
        const messageId = canfd ? mavlink20.MAVLINK_MSG_ID_CANFD_FRAME : mavlink20.MAVLINK_MSG_ID_CAN_FRAME;
        outgoing.length = 0;
        client.once('sendFrame', (id, data, len) => {
            for (const inputBus of [0, bus]) {
                const frame = new Message(255, 0, inputBus, len, id, data.toString('binary'));
                const packet = Buffer.from(frame.pack(encoder));
                const sender = { address: '127.0.0.1', port: 10000 };
                if (inputBus === bus) {
                    // The parser retains an incomplete header until the next datagram.
                    socket.emit('message', packet.subarray(0, 2), sender);
                    assert.equal(outgoing.length, 0);
                    socket.emit('message', packet.subarray(2), sender);
                } else {
                    socket.emit('message', packet, sender);
                }
                if (inputBus !== bus) assert.equal(outgoing.length, 0, 'answered on another bus');
            }
        });
        let response;
        const request = client.request({
            req: new DSDL.uavcan_protocol_GetNodeInfo_Request(),
            destNodeId: server.nodeId, canfd, callback: transfer => { response = transfer; }
        });
        assert.ok(outgoing.length > 0);
        for (const packet of outgoing) {
            const [frame] = decoder.parseBuffer(new Uint8Array(packet));
            assert.equal(frame._header.msgId, messageId);
            assert.equal(frame.bus, bus);
            client.emit('can-frame', frame.id, frame.data, frame.len, frame.bus, canfd);
        }
        assert.ok(response, 'the replying frames must complete the GetNodeInfo request');
        assert.equal(response.payload.fields.name.toString(), server.name);
        assert.equal(response.transferId, request.transferId);
        assert.equal(response.canfd, canfd);
    }
});
