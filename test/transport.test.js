const assert = require('node:assert/strict');
const test = require('node:test');
const { parseFrameMessage } = require('..');
const DSDL = require('../dronecan/dsdl');
const Frame = require('../dronecan/frame');
const Transfer = require('../dronecan/transfer');
const TransferManager = require('../dronecan/transfer_manager');

function logTransfer(size, canfd, sourceNodeId = 42, transferId = 7) {
    const payload = new DSDL.uavcan_protocol_debug_LogMessage();
    payload.fields.level.msg.fields.value.value = 2;
    payload.fields.source.fromString('A');
    payload.fields.text.fromString('x'.repeat(size));
    return new Transfer({ payload, sourceNodeId, transferId, transferPriority: 20, canfd });
}

// PyDroneCAN 1.0.27 reference frames for LogMessage(level=2, source="A", text="x"*size).
const seven = '78'.repeat(7);
const vectors = [
    [3, false, ['4141787878c7']],
    [33, false, ['4e8b414178787887', seven+'27', seven+'07', seven+'27', seven+'07', '787867']],
    [3, true, ['414106f0f0f0c7']],
    [33, true, ['414142'+'f0'.repeat(33)+'00'.repeat(11)+'c7']],
    [50, true, ['414164'+'f0'.repeat(50)+'00'.repeat(10)+'c7']],
    [70, true, ['f5d041418c'+'f0'.repeat(58)+'87', 'f0'.repeat(12)+'00000067']],
];

// Check transmitted wire bytes, then decode the independent reference frames.
function verifyWire(transfer, expectedId, wire) {
    const sent = transfer.toFrames();
    assert.deepEqual(sent.map(frame => frame.data.toString('hex')), wire);
    assert.ok(sent.every(frame => frame.id === expectedId && frame.canfd === transfer.canfd));

    const manager = new TransferManager();
    const received = wire.map(hex => manager.addFrame(
        new Frame(expectedId, Buffer.from(hex, 'hex'), true, transfer.canfd)
    ));
    assert.ok(received.slice(0, -1).every(result => result === null));
    const decoded = received.at(-1);
    assert.ok(decoded);
    assert.equal(decoded.canfd, transfer.canfd);
    assert.equal(decoded.transferId, transfer.transferId);
    return decoded;
}

test('standard Classic and FD frames match PyDroneCAN in both directions', () => {
    for (const [size, canfd, wire] of vectors) {
        const received = verifyWire(logTransfer(size, canfd), 0x143fff2a, wire);
        assert.equal(received.payload.fields.text.toString(), 'x'.repeat(size));
    }
});

test('parseFrameMessage decodes Classic and padded FD payloads with a tail array', () => {
    for (const [size, canfd, wire] of vectors.filter(([, , frames]) => frames.length === 1)) {
        const payload = Buffer.from(wire[0], 'hex').subarray(0, -1);
        assert.equal(parseFrameMessage(16383, payload, canfd).fields.text.toString(), 'x'.repeat(size));
        if (!canfd) {
            assert.equal(parseFrameMessage(16383, payload).fields.text.toString(), 'x'.repeat(size));
        }
    }
});

test('File.Read requests, binary chunks and EOF match PyDroneCAN service frames', () => {
    // PyDroneCAN 1.0.27, priority 17, TID 31, client 10, server 125.
    const cases = [
        {
            canfd: false, size: 8,
            request: ['c4a605040302019f', '612e62696e7f'],
            chunk: ['f347000000ffff9f', 'ffffffff807f'],
            eof: ['0000df'],
        },
        {
            canfd: true, size: 67,
            request: ['050403020105612e62696edf'],
            chunk: ['ce5c000043007f' + 'ff'.repeat(56) + '9f', 'ffffffffffffffffc000007f'],
            eof: ['00000000df'],
        },
    ];
    for (const { canfd, size, request, chunk, eof } of cases) {
        const common = { serviceNotMessage: true, transferPriority: 17, transferId: 31, canfd };
        const payload = new DSDL.uavcan_protocol_file_Read_Request();
        payload.fields.offset.value = 0x0102030405;
        payload.fields.path.fields.path.fromString('a.bin');
        const read = new Transfer({
            ...common, sourceNodeId: 10, destNodeId: 125, requestNotResponse: true, payload
        });
        const decoded = verifyWire(read, 0x1130fd8a, request);
        assert.equal(decoded.sourceNodeId, 10);
        assert.equal(decoded.destNodeId, 125);
        assert.equal(decoded.transferPriority, 17);
        assert.equal(decoded.payload.fields.offset.value, 0x0102030405);
        assert.equal(decoded.payload.fields.path.fields.path.toString(), 'a.bin');

        const bytes = Buffer.alloc(size, 0xff);
        bytes[0] = 0;
        bytes[size - 1] = 0x80;
        for (const [data, wire] of [[bytes, chunk], [Buffer.alloc(0), eof]]) {
            const response = new DSDL.uavcan_protocol_file_Read_Response();
            response.fields.data.fromBytes(data);
            const tx = new Transfer({ ...common, sourceNodeId: 125, destNodeId: 10, payload: response });
            const reply = verifyWire(tx, 0x11300afd, wire);
            assert.equal(reply.isResponseTo(decoded), true);
            assert.equal(reply.payload.fields.error.fields.value.value, 0);
            assert.deepEqual(reply.payload.fields.data.toBytes(), data);
        }
    }
});

test('CAN FD produces legal DLCs at all single/multiframe boundaries and preserves the payload', () => {
    for (let size = 0; size <= 90; size++) {
        const frames = logTransfer(size, true).toFrames();
        const lengths = frames.map(frame => frame.data.length);
        assert.ok(lengths.every(length => length <= 8 || [12,16,20,24,32,48,64].includes(length)));
        const rx = new Transfer();
        rx.fromFrames(frames);
        assert.equal(rx.payload.fields.text.toString(), 'x'.repeat(size));
    }
});

test('TIDs advance independently and cannot skip a blocked ID after wraparound', () => {
    const manager = new TransferManager();
    const descriptor = [42, 127, 48];
    assert.equal(manager.getNextTransferId(descriptor), 0);
    assert.equal(manager.getNextTransferId([42, 127, 11]), 0);
    for (let tid = 1; tid < 32; tid++) assert.equal(manager.getNextTransferId(descriptor), tid);
    assert.throws(() => manager.getNextTransferId(descriptor.slice(), tid => tid === 0), RangeError);
    assert.throws(() => manager.getNextTransferId(descriptor, tid => tid !== 1), RangeError);
    assert.equal(manager.getNextTransferId(descriptor, tid => tid === 1), 0);
    assert.equal(manager.getNextTransferId(descriptor), 1);
    manager.resetReceiveState();
    assert.equal(manager.getNextTransferId(descriptor), 2);
});

test('encoding failure keeps the next TID, while a transfer handed to the adapter consumes it', t => {
    const Node = require('../dronecan/node');
    const node = new Node({ nodeId: 11 });
    t.after(() => {
        clearInterval(node.nodeStatusIntervalID);
        node.resetSession();
    });
    const req = new DSDL.uavcan_protocol_param_GetSet_Request();
    const send = () => node.request({ req, destNodeId: 42 });
    const wireIds = [];
    node.on('sendFrame', (_id, data) => wireIds.push(data.at(-1) & 31));
    req.fields.index.value = 0.5;
    assert.throws(send, /whole numbers/);
    assert.deepEqual(wireIds, []);
    req.fields.index.value = 0;

    node.once('sendFrame', send);
    assert.equal(send().transferId, 0);
    assert.deepEqual(wireIds, [0, 1]);

    req.fields.name.fromString('a multi-frame request');
    node.once('sendFrame', () => { throw new Error('adapter disconnected'); });
    assert.throws(send, /adapter disconnected/);
    req.fields.name.fromString('');
    assert.equal(send().transferId, 3);
    assert.deepEqual(wireIds, [0, 1, 2, 3]);
});

test('broadcast TID wrap follows the descriptor across priority and link format changes', () => {
    for (const variation of ['priority', 'format']) {
        const manager = new TransferManager();
        for (let i = 0; i <= 32; i++) {
            const changed = i > 0 && i < 32;
            const tid = i % 32;
            const tx = logTransfer(1, variation === 'format' && changed, 42, tid);
            if (variation === 'priority' && changed) tx.transferPriority = 10;
            const [frame] = tx.toFrames();
            assert.equal(manager.addFrame(frame, i * 10)?.transferId, tid);
        }
    }
});

test('duplicates across priority and format are suppressed until timeout or reset', () => {
    const manager = new TransferManager();
    const [classic] = logTransfer(3, false).toFrames();
    const fd = logTransfer(3, true);
    fd.transferPriority = 10;
    const [different] = fd.toFrames();
    assert.equal(manager.addFrame(classic, 0)?.transferId, 7);
    assert.equal(manager.addFrame(different, 1999), null);
    assert.equal(manager.addFrame(different, 2000)?.transferId, 7);
    assert.equal(manager.addFrame(classic, 2001), null);
    manager.resetReceiveState();
    assert.equal(manager.addFrame(classic, 2002)?.transferId, 7);
});

test('continuation frames must match the exact priority and link format of the start frame', () => {
    const manager = new TransferManager();
    const [first, last] = logTransfer(8, false).toFrames();
    assert.equal(manager.addFrame(first), null);
    assert.equal(manager.addFrame(new Frame(last.id ^ 0x01000000, last.data)), null);
    assert.equal(manager.addFrame(new Frame(last.id, last.data, true, true)), null);
    assert.equal(manager.addFrame(last)?.transferId, 7);
});

test('a late fragment of a duplicate on another wire format or priority cannot redeliver an old TID', () => {
    for (const variation of ['priority', 'format']) {
        const manager = new TransferManager();
        const original = logTransfer(70, false, 42, 0);
        const duplicate = logTransfer(70, variation === 'format', 42, 0);
        if (variation === 'priority') duplicate.transferPriority = 10;
        const duplicateFrames = duplicate.toFrames();
        for (const frame of duplicateFrames.slice(0, -1)) assert.equal(manager.addFrame(frame), null);
        const received = original.toFrames().map(frame => manager.addFrame(frame));
        assert.equal(received.at(-1)?.transferId, 0);
        assert.equal(manager.addFrame(logTransfer(3, false, 42, 1).toFrames()[0])?.transferId, 1);
        assert.equal(manager.addFrame(duplicateFrames.at(-1)), null);
    }
});

test('interleaved sources with the same TID reassemble separately; late fragments cannot finish a superseded transfer', () => {
    const manager = new TransferManager();
    const a = logTransfer(8, false, 42, 31).toFrames();
    const b = logTransfer(8, false, 43, 31).toFrames();
    assert.equal(manager.addFrame(a[0]), null);
    assert.equal(manager.addFrame(b[0]), null);
    assert.equal(manager.addFrame(a[1]).sourceNodeId, 42);
    assert.equal(manager.addFrame(b[1]).sourceNodeId, 43);
    manager.resetReceiveState();
    const next = logTransfer(8, false, 42, 0).toFrames();
    assert.equal(manager.addFrame(a[0]), null);
    assert.equal(manager.addFrame(next[0]), null);
    assert.equal(manager.addFrame(a[1]), null);
    assert.equal(manager.addFrame(next[1]).transferId, 0);
    for (const frame of next) assert.equal(manager.addFrame(frame), null);
});

test('incomplete transfers expire and a receive reset discards partial frames', () => {
    const manager = new TransferManager();
    const [first, last] = logTransfer(8, false).toFrames();
    assert.equal(manager.addFrame(first, 0), null);
    assert.equal(manager.addFrame(last, 2001), null);
    assert.equal(manager.addFrame(first, 2100), null);
    manager.resetReceiveState();
    assert.equal(manager.addFrame(last, 2101), null);
    assert.equal(manager.addFrame(first, 2102), null);
    assert.equal(manager.addFrame(last, 2103).transferId, 7);
});

test('assembly timeout follows the last accepted fragment and duplicate reception does not extend it', () => {
    const [first, middle, last] = logTransfer(16, false).toFrames();
    const manager = new TransferManager();
    assert.equal(manager.addFrame(first, 0), null);
    assert.equal(manager.addFrame(middle, 1999), null);
    assert.equal(manager.addFrame(middle, 3000), null);
    assert.equal(manager.addFrame(last, 3998).payload.fields.text.toString(), 'x'.repeat(16));

    manager.resetReceiveState();
    assert.equal(manager.addFrame(first, 0), null);
    assert.equal(manager.addFrame(middle, 1999), null);
    assert.equal(manager.addFrame(middle, 3000), null);
    assert.equal(manager.addFrame(last, 3999), null);
    assert.equal(manager.addFrame(first, 4000), null);
    assert.equal(manager.addFrame(middle, 4001), null);
    assert.equal(manager.addFrame(last, 4002).transferId, 7);
});

test('CRC/DSDL errors, non-extended frames and invalid DLCs cannot deliver a partial transfer', () => {
    const [first, last] = logTransfer(8, false).toFrames();
    const manager = new TransferManager();
    assert.equal(manager.addFrame(new Frame(first.id, first.data, false)), null);
    assert.equal(manager.addFrame(last), null);
    for (const [size, fd] of [[0, false], [9, false], [40, true], [56, true]]) {
        assert.equal(Frame.isValidTransferFrame(new Frame(first.id, Buffer.alloc(size), true, fd)), false);
    }
    const checksumError = Buffer.from(first.data);
    checksumError[0] ^= 1;
    assert.equal(manager.addFrame(new Frame(first.id, checksumError)), null);
    assert.equal(manager.addFrame(last), null);
    const unknownType = new Frame((20 << 24) | (65000 << 8) | 42, Buffer.from([0xc7]));
    assert.equal(manager.addFrame(unknownType), null);
    assert.throws(() => new Transfer().fromFrames([first, new Frame(last.id, last.data, true, true)]));
    assert.equal(manager.addFrame(first), null);
    assert.equal(manager.addFrame(last).transferId, 7);
});

test('pending requests across a TID wrap can receive two distinct replies with the same TID in succession', () => {
    const Node = require('../dronecan/node');
    const node = new Node({ nodeId: 127 });
    const delivered = [];
    const request = () => node.request({
        req: new DSDL.uavcan_protocol_GetNodeInfo_Request(),
        destNodeId: 42,
        callback: transfer => delivered.push(transfer.transferId),
    });
    const frames = new Transfer({
        sourceNodeId: 42, destNodeId: 127, serviceNotMessage: true,
        transferId: 0, payload: DSDL.uavcan_protocol_GetNodeInfo_Response.sampleMessage(),
    }).toFrames();
    try {
        for (let i = 0; i < 32; i++) assert.equal(request().transferId, i);
        for (const frame of frames) node.handleFrame(frame);
        assert.equal(request().transferId, 0);
        for (const frame of frames) node.handleFrame(frame);
        assert.deepEqual(delivered, [0, 0]);
    } finally {
        clearInterval(node.nodeStatusIntervalID);
        node.resetSession();
    }
});

test('anonymous allocation fits one Classic or FD frame and derives the libcanard discriminator', () => {
    const cases = [
        [false, [1, 2, 3, 4, 5, 6], 0x14214500, '01010203040506c7'],
        [true, Array.from({ length: 16 }, (_, i) => i), 0x14d87100, '01800008101820283038404850586068707800c7'],
    ];
    for (const [canfd, uid, id, wire] of cases) {
        const payload = new DSDL.uavcan_protocol_dynamic_node_id_Allocation();
        payload.fields.first_part_of_unique_id.value = true;
        payload.fields.unique_id.fromString(String.fromCharCode(...uid));
        const options = { payload, sourceNodeId: 0, canfd, transferId: 7, transferPriority: 20 };
        const [frame] = new Transfer(options).toFrames();
        assert.equal(frame.id, id);
        assert.equal(frame.data.toString('hex'), wire);
        const manager = new TransferManager();
        for (let i = 0; i < 2; i++) {
            const decoded = manager.addFrame(frame);
            assert.equal(decoded.canfd, canfd);
            assert.deepEqual(decoded.payload.fields.unique_id.items.map(x => x.value), uid);
        }
        const explicit = new Transfer({ ...options, discriminator: 0x1234 });
        assert.equal((explicit.toFrames()[0].id >>> 10) & 0x3FFF, 0x1234);
        assert.throws(() => new Transfer({ ...options, serviceNotMessage: true }).toFrames(), RangeError);
        if (canfd) assert.throws(() => new Transfer({ ...options, canfd: false }).toFrames(), RangeError);
    }
    assert.throws(() => logTransfer(3, false, 0).toFrames(), RangeError);
    assert.equal(Frame.isValidTransferFrame(new Frame(0x100, [0x80])), false);
    assert.equal(Frame.isValidTransferFrame(new Frame(0x80, [0xc0])), false);
});
