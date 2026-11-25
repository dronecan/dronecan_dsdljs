const test = require('node:test');
const { once } = require('node:events');
const assert = require('node:assert/strict');
const { Node, DSDL, TransferManager } = require('..');
const Transfer = require('../dronecan/transfer');

function node(nodeId, sendCanfd = false) {
    const instance = new Node({ nodeId, sendCanfd });
    clearInterval(instance.nodeStatusIntervalID);
    return instance;
}

function deliver(receiver, transfer) {
    for (const frame of transfer.toFrames()) receiver.handleFrame(frame);
}

function paramResponse(name, field, value) {
    const msg = new DSDL.uavcan_protocol_param_GetSet_Response();
    msg.fields.name.fromString(name);
    const union = msg.fields.value.msg;
    union.unionFieldIndex.value = union.unionFields.indexOf(field);
    if (field === 'string_value') union.unionField.fromString(value);
    else union.unionField.value = value;
    return msg;
}

function reply(request, payload) {
    return new Transfer({
        sourceNodeId: request.destNodeId, destNodeId: request.sourceNodeId,
        transferId: request.transferId, payload, serviceNotMessage: true
    });
}

test('GetNodeInfo addresses only the requested node and echoes the request over Classic and FD', () => {
    for (const canfd of [false, true]) {
        const client = node(11, canfd);
        const server = node(42);
        const bystander = node(73);
        let otherFrames = 0;
        bystander.on('sendFrame', () => otherFrames++);
        client.on('sendFrame', (...args) => {
            bystander.emit('can-frame', ...args);
            server.emit('can-frame', ...args);
        });
        server.on('sendFrame', (...args) => client.emit('can-frame', ...args));
        for (let tid = 0; tid < 3; tid++) {
            let response;
            client.request({
                destNodeId: 42, priority: 17, req: new DSDL.uavcan_protocol_GetNodeInfo_Request(),
                callback: transfer => { response = transfer; }
            });
            assert.equal(response?.transferId, tid);
            assert.equal(response.sourceNodeId, 42);
            assert.equal(response.destNodeId, 11);
            assert.equal(response.transferPriority, 17);
            assert.equal(response.canfd, canfd);
            assert.equal(response.payload.fields.name.toString(), 'dronecan.js');
        }
        assert.equal(otherFrames, 0);
        assert.equal(client.callbacks.size, 0);
    }
});

test('only the matching service, client, server and TID can complete a request', () => {
    const client = node(11);
    const calls = [];
    const read = id => client.fetchNodeParam(id, 0, '', () => calls.push(id));
    const a = read(125);
    const b = read(42);
    assert.equal(a.transferId, b.transferId);
    for (let i = 0; i < 35; i++) {
        client.request({ req: client.status, serviceNotMessage: false });
    }
    const param = paramResponse('OPTION', 'integer_value', 5);
    deliver(client, reply(a, new DSDL.uavcan_protocol_RestartNode_Response()));
    const otherClient = reply(a, param);
    otherClient.destNodeId = 19;
    deliver(client, otherClient);
    assert.deepEqual(calls, []);
    deliver(client, reply(b, param));
    deliver(client, reply(a, param));
    assert.deepEqual(calls, [42, 125]);
    assert.equal(client.callbacks.size, 0);
});

test('TID wrap cannot overwrite an outstanding request', () => {
    const client = node(11);
    const request = onError => client.fetchNodeParam(42, 0, '', null, onError);
    const pending = Array.from({ length: 32 }, () => request());
    let failure;
    assert.equal(request(error => { failure = error.code; }), null);
    assert.equal(failure, 'REQUEST_PENDING');
    assert.equal(client.callbacks.size, 32);
    const freed = pending[8];
    deliver(client, reply(freed, paramResponse('P', 'integer_value', 8)));
    assert.equal(request(error => { failure = error.code; }), null);
    assert.equal(failure, 'REQUEST_PENDING');
    deliver(client, reply(pending[0], paramResponse('P', 'integer_value', 0)));
    assert.equal(request().transferId, 0);
    client.setNodeId(12);
    assert.equal(client.callbacks.size, 0);
});

function connect(client, server) {
    client.on('sendFrame', (...args) => server.emit('can-frame', ...args));
    server.on('sendFrame', (...args) => client.emit('can-frame', ...args));
}

test('service responses must use the original request even when answered out of order', () => {
    const client = node(11);
    const server = node(42);
    connect(client, server);
    const requests = [];
    const results = [];
    server.on('uavcan.protocol.param.GetSet.Request', transfer => requests.push(transfer));
    for (const name of ['A', 'B']) {
        client.fetchNodeParam(42, 0, name, transfer => results.push([name, transfer.payload.fields.name.toString()]));
    }
    const res = paramResponse('B', 'integer_value', 2);
    assert.throws(() => server.request({ req: res, destNodeId: 11, requestNotResponse: false }), /response\(\)/);
    assert.equal(client.callbacks.size, 2);
    server.response({ res, transfer: requests[1] });
    server.response({ res: paramResponse('A', 'integer_value', 1), transfer: requests[0] });
    assert.deepEqual(results, [['B', 'B'], ['A', 'A']]);
    assert.equal(client.callbacks.size, 0);
});

for (const canfd of [false, true]) {
    test(`GetSet reads parameters by index through the end marker and by name over ${canfd ? 'FD' : 'Classic CAN'}`, () => {
        const client = node(11, canfd);
        const server = node(125);
        connect(client, server);
        const params = [
            ['SERIAL', 'integer_value', 9007199254740993n],
            ['GAIN', 'real_value', -0.25],
            ['ENABLE', 'boolean_value', 0],
            ['LABEL', 'string_value', '接收机'],
        ];
        const queries = [];
        server.on('uavcan.protocol.param.GetSet.Request', transfer => {
            const { index, value, name } = transfer.payload.fields;
            assert.equal(transfer.canfd, canfd);
            assert.equal(value.msg.unionFields[value.unionFieldIndex.value], 'empty');
            const key = name.toString();
            queries.push([index.value, key]);
            const row = key ? params.find(([n]) => n === key) : params[index.value];
            const res = row ? paramResponse(...row) : new DSDL.uavcan_protocol_param_GetSet_Response();
            server.response({ res, transfer });
        });

        function read(index, name = '') {
            let result;
            client.fetchNodeParam(125, index, name, transfer => {
                assert.equal(transfer.canfd, canfd);
                const fields = transfer.payload.fields;
                const value = fields.value.msg;
                const tag = value.unionFields[value.unionFieldIndex.value];
                result = [fields.name.toString(), tag, tag === 'empty' ? null : value.unionField.toObj()];
            });
            assert.ok(result, 'each parameter read must receive a response');
            return result;
        }

        assert.deepEqual(params.map((_, i) => read(i)), params);
        assert.deepEqual(read(params.length), ['', 'empty', null]);
        // A named GetSet ignores its index, even when the 13-bit index is out of table range.
        assert.deepEqual(read(8191, 'LABEL'), params[3]);
        assert.deepEqual(queries, [[0, ''], [1, ''], [2, ''], [3, ''], [4, ''], [8191, 'LABEL']]);
        assert.equal(client.callbacks.size, 0);
    });

    test(`GetSet writes UTF-8 strings and opaque bytes over ${canfd ? 'FD' : 'Classic CAN'}`, () => {
        const client = node(11, canfd);
        const server = node(125);
        connect(client, server);
        client.updateNodeParamsFromResponse({ sourceNodeId: 125, payload: paramResponse('LABEL', 'string_value', '') }, 0);
        const writes = [];
        server.on('uavcan.protocol.param.GetSet.Request', transfer => {
            assert.equal(transfer.canfd, canfd);
            const bytes = transfer.payload.fields.value.msg.unionField.toBytes();
            writes.push(bytes);
            const res = paramResponse('LABEL', 'string_value', '');
            res.fields.value.msg.unionField.fromBytes(bytes);
            server.response({ res, transfer });
        });
        const binary = [0, 128, 255];
        const cases = [[binary, binary], [Uint8Array.from(binary), binary], [Buffer.from(binary), binary],
            ['接收机', Buffer.from('接收机')], ['', []]];
        for (const [input, expected] of cases) {
            client.setNodeParam(125, 0, input);
            assert.deepEqual(writes.at(-1), Buffer.from(expected));
            assert.deepEqual(client.nodeParams[125][0].fields.value.msg.unionField.toBytes(), Buffer.from(expected));
        }
        assert.throws(() => client.setNodeParam(125, 0, [256]), RangeError);
        assert.throws(() => client.setNodeParam(125, 0, Uint16Array.of(256)), TypeError);
        assert.equal(writes.length, cases.length);
        assert.equal(client.callbacks.size, 0);
    });
}

test('a GetSet retry ignores a timed-out response even after transfer ID wraparound', { timeout: 2000 }, async t => {
    // A real node heartbeat keeps the event loop alive until the unref'ed service timer fires.
    const client = new Node({ nodeId: 11 });
    t.after(() => clearInterval(client.nodeStatusIntervalID));
    const server = node(125);
    connect(client, server);
    const requests = [];
    server.on('uavcan.protocol.param.GetSet.Request', transfer => requests.push(transfer));
    const results = [];
    const onResponse = transfer => results.push(transfer.payload.fields.value.msg.unionField.value);
    const timeout = once(client, 'request-error');
    const failures = [];
    const expired = client.fetchNodeParam(125, 0, 'GAIN', onResponse, error => failures.push(error.code), 5);
    const [error, failedRequest] = await timeout;
    assert.equal(error.code, 'REQUEST_TIMEOUT');
    assert.equal(failedRequest, expired);
    assert.deepEqual(failures, ['REQUEST_TIMEOUT']);
    assert.equal(client.callbacks.size, 0);

    for (let index = 1; index < 32; index++) {
        client.fetchNodeParam(125, index, '');
        const request = requests.at(-1);
        assert.equal(request.transferId, index);
        server.response({ res: paramResponse('P' + index, 'integer_value', index), transfer: request });
    }
    const blocked = client.fetchNodeParam(125, 0, 'GAIN', onResponse, err => failures.push(err.code));
    assert.equal(blocked, null);
    assert.deepEqual(failures, ['REQUEST_TIMEOUT', 'REQUEST_PENDING']);
    assert.equal(requests.length, 32);
    server.response({ res: paramResponse('GAIN', 'integer_value', 4), transfer: requests[0] });
    assert.deepEqual(results, []);
    assert.equal(client.callbacks.size, 0);
});

test('cancelled IDs can be reused after the transfer timeout and stay scoped to one server', async () => {
    const client = node(11);
    const failures = [];
    const read = id => client.fetchNodeParam(id, 0, '', null, err => failures.push(err.code));
    for (let tid = 0; tid < 32; tid++) {
        const req = read(125);
        assert.equal(req.transferId, tid);
        assert.ok(client.cancelRequest(req));
    }
    client.resetSession();
    assert.equal(read(125), null);
    assert.deepEqual(failures, ['REQUEST_PENDING']);
    const other = read(42);
    assert.equal(other.transferId, 0);
    deliver(client, reply(other, paramResponse('P', 'integer_value', 7)));
    await new Promise(resolve => setTimeout(resolve, TransferManager.TRANSFER_TIMEOUT_MS));
    const next = read(125);
    assert.equal(next.transferId, 0);
    deliver(client, reply(next, paramResponse('P', 'integer_value', 8)));
    assert.equal(client.callbacks.size, 0);
});

test('a remote reboot invalidates parameter and discovery requests for that node', () => {
    const client = node(11);
    const server = node(125);
    connect(client, server);
    const discovery = [];
    server.removeAllListeners('uavcan.protocol.GetNodeInfo.Request');
    server.on('uavcan.protocol.GetNodeInfo.Request', request => discovery.push(request));
    const heartbeat = uptime => {
        server.status.fields.uptime_sec.value = uptime;
        server.request({ req: server.status, serviceNotMessage: false });
    };
    heartbeat(150);
    const cached = paramResponse('P', 'integer_value', 4);
    for (const id of [42, 125]) client.updateNodeParamsFromResponse({ sourceNodeId: id, payload: cached }, 0);
    let otherResponded = false;
    const other = client.fetchNodeParam(42, 7, '', () => { otherResponded = true; });
    const failures = [];
    const onError = err => failures.push(err.code);
    client.fetchNodeParam(125, 1, '', assert.fail, onError);
    const write = client.setNodeParam(125, 0, 10, onError);

    heartbeat(1);
    assert.deepEqual(failures, ['NODE_RESTARTED', 'NODE_RESTARTED']);
    assert.equal(client.nodeParams[125], undefined);
    assert.equal(client.nodeParamsRequestingNodeId, null);
    assert.equal(client.getNodeParamsRequestingIndex(125), undefined);
    deliver(client, reply(write, paramResponse('P', 'integer_value', 10)));
    assert.equal(client.nodeParams[125], undefined);

    server.responseNodeInfo(discovery[0]);
    assert.equal(client.nodeMonitors[125].name, undefined);
    heartbeat(2);
    assert.equal(discovery.length, 2);
    server.responseNodeInfo(discovery[1]);
    assert.equal(client.nodeMonitors[125].name, server.name);
    assert.equal(client.nodeParams[42][0], cached);
    assert.equal(client.getNodeParamsRequestingIndex(42), 7);
    deliver(client, reply(other, cached));
    assert.ok(otherResponded);
    assert.equal(client.callbacks.size, 0);
});

test('a GetNodeInfo response before the first new heartbeat cannot mask a reboot', () => {
    const client = node('11');
    const server = node('42');
    connect(client, server);
    server.status.fields.uptime_sec.value = 100;
    server.request({ req: server.status, serviceNotMessage: false });
    const [id] = Object.keys(client.nodeMonitors);
    client.updateNodeParamsFromResponse({ sourceNodeId: 42, payload: paramResponse('OLD', 'integer_value', 9) }, 0);
    let error;
    client.fetchNodeParam(id, 0, '', assert.fail, err => { error = err.code; });
    client.refreshNodeMonitor();
    assert.deepEqual(client.nodeMonitors, {});
    // The restarted server replies with its own current uptime (0 s) before publishing NodeStatus.
    let info;
    client.getNodeInfo(id, transfer => { info = transfer.payload.toObj(); });
    assert.equal(info.name, server.name);
    assert.ok(info.status.uptime_sec < 100);
    assert.equal(client.nodeMonitors[42].status.uptime_sec, 100);
    server.status.fields.uptime_sec.value = 2;
    server.request({ req: server.status, serviceNotMessage: false });
    assert.equal(error, 'NODE_RESTARTED');
    assert.equal(client.nodeParams[42], undefined);
    assert.equal(client.nodeParamsRequestingNodeId, null);
    assert.equal(client.nodeMonitors[42].status.uptime_sec, 2);
    assert.equal(client.callbacks.size, 0);
});

test('a heartbeat after the offline timeout rediscovers the identity behind the same ID', t => {
    let now = 0;
    t.mock.method(performance, 'now', () => now);
    const client = node(11);
    const server = node(42);
    connect(client, server);
    const heartbeat = uptime => {
        server.status.fields.uptime_sec.value = uptime;
        server.request({ req: server.status, serviceNotMessage: false });
    };
    server.name = 'old-node';
    heartbeat(60);
    assert.equal(client.nodeMonitors[42].name, 'old-node');
    const old = paramResponse('OLD', 'integer_value', 9);
    client.updateNodeParamsFromResponse({ sourceNodeId: 42, payload: old }, 0);
    client.updateNodeParamsFromResponse({ sourceNodeId: 73, payload: old }, 0);
    let error;
    client.fetchNodeParam(42, 0, '', assert.fail, err => { error = err.code; });
    client.refreshNodeMonitor();
    now = 3001;
    server.name = 'replacement';
    heartbeat(400);
    assert.equal(error, 'NODE_RECONNECTED');
    assert.equal(client.nodeMonitors[42].name, 'replacement');
    assert.equal(client.nodeMonitors[42].status.uptime_sec, 400);
    assert.equal(client.nodeParams[42], undefined);
    assert.equal(client.nodeParams[73][0], old);
});

test('a reboot clears only the remote source\'s duplicate and partial receive records', () => {
    const client = node(11);
    function heartbeat(uptime, transferId) {
        const status = new DSDL.uavcan_protocol_NodeStatus();
        status.fields.uptime_sec.value = uptime;
        deliver(client, new Transfer({ sourceNodeId: 42, payload: status, transferId }));
    }
    function request(id, index, transferId) {
        const payload = new DSDL.uavcan_protocol_param_GetSet_Request();
        payload.fields.index.value = index;
        payload.fields.name.fromString('MULTIFRAME_PARAM');
        return new Transfer({ sourceNodeId: id, destNodeId: 11, requestNotResponse: true,
            serviceNotMessage: true, transferId, payload });
    }
    const received = [];
    client.on('uavcan.protocol.param.GetSet.Request', req => received.push(req));
    heartbeat(150, 12);
    for (const id of [42, 73]) deliver(client, request(id, 3, 0));
    const stale = request(42, 4, 1).toFrames();
    const live = request(73, 4, 1).toFrames();
    client.handleFrame(stale[0]);
    client.handleFrame(live[0]);
    heartbeat(1, 0);
    for (const frame of stale.slice(1)) client.handleFrame(frame);
    for (const id of [42, 73]) deliver(client, request(id, 7, 0));
    for (const frame of live.slice(1)) client.handleFrame(frame);
    assert.deepEqual(received.map(req => [req.sourceNodeId, req.payload.fields.index.value]),
        [[42, 3], [73, 3], [42, 7], [73, 4]]);
    const respond = req => client.response({ res: paramResponse('P', 'integer_value', 1), transfer: req });
    assert.equal(respond(received[0]), null); // The old requester no longer owns this TID.
    assert.ok(respond(received[1]));
    assert.ok(respond(received[2]));
});

test('service node IDs are validated before updating request state or transmitting', () => {
    const client = node('11');
    const session = client.sessionId;
    client.setNodeId('011');
    assert.equal(client.sessionId, session);
    let frames = 0;
    client.on('sendFrame', () => frames++);
    for (const invalid of [null, '', 0, '1.5', 128, true]) {
        assert.throws(() => client.fetchNodeParam(invalid, 3, ''), RangeError);
        assert.throws(() => client.getNodeInfo(invalid), RangeError);
    }
    assert.equal(frames, 0);
    assert.equal(client.nodeParamsRequestingNodeId, null);
    assert.equal(client.callbacks.size, 0);
});

test('a bus change drops partial frames and isolates identical pending service IDs on different buses', () => {
    const client = node(11);
    const msg = paramResponse('LONG_PARAM', 'integer_value', 7);
    client.updateNodeParamsFromResponse({ sourceNodeId: 125, payload: msg }, 0);
    const responses = [];
    const failures = [];
    const read = () => client.fetchNodeParam(125, 0, '', transfer => responses.push(transfer.bus),
        error => failures.push(error.code));
    const old = read();
    const frames = reply(old, msg).toFrames();
    assert.ok(frames.length > 1);
    client.handleFrame(frames[0]);
    client.setBus(1);
    assert.deepEqual(failures, ['SESSION_RESET']);
    assert.deepEqual(client.nodeParams, {});
    const current = read();
    assert.equal(current.transferId, old.transferId);
    let received = 0;
    client.on('transfer-rx', () => received++);
    for (const frame of frames.slice(1)) client.handleFrame(frame);
    for (const frame of frames) client.emit('can-frame', frame.id, frame.data, frame.data.length, 0);
    assert.equal(received, 0);
    assert.deepEqual(responses, []);
    deliver(client, reply(current, msg));
    assert.deepEqual(responses, [1]);
    assert.equal(client.callbacks.size, 0);
});

test('parameter writes keep confirmed values until matching acknowledgements arrive', () => {
    for (const [field, oldValue, newValue] of [
        ['integer_value', 5, 9007199254740993n], ['string_value', '旧值', '已更新']
    ]) {
        const client = node(11);
        const name = 'PARAM';
        const original = paramResponse(name, field, oldValue);
        client.updateNodeParamsFromResponse({ sourceNodeId: 125, payload: original }, 3);
        const write = client.setNodeParam(125, 3, newValue);
        assert.equal(client.nodeParams[125][3].fields.value.msg.unionField.toObj(), oldValue);
        assert.equal(write.payload.fields.value.msg.unionField.toObj(), newValue);
        deliver(client, reply(write, paramResponse(name, field, newValue)));
        assert.equal(client.nodeParams[125][3].fields.value.msg.unionField.toObj(), newValue);
    }
});

test('a GetSet write uses the node-confirmed value and rejects acknowledgements for another parameter', () => {
    const client = node(11);
    const server = node(125);
    connect(client, server);
    client.updateNodeParamsFromResponse({ sourceNodeId: 125, payload: paramResponse('LIMIT', 'integer_value', 3) }, 0);
    let responseName = 'LIMIT';
    server.on('uavcan.protocol.param.GetSet.Request', transfer => {
        const { name, value } = transfer.payload.fields;
        assert.equal(name.toString(), 'LIMIT');
        assert.equal(value.msg.unionField.value, 99);
        const res = paramResponse(responseName, 'integer_value', responseName === 'LIMIT' ? 10 : 42);
        server.response({ res, transfer });
    });
    const errors = [];
    const write = () => client.setNodeParam(125, 0, 99, error => errors.push(error.code));
    write();
    const confirmed = client.nodeParams[125][0];
    assert.equal(confirmed.fields.value.msg.unionField.value, 10);
    responseName = 'OTHER';
    write();
    assert.deepEqual(errors, ['PARAM_NAME_MISMATCH']);
    assert.equal(client.nodeParams[125][0], confirmed);
    assert.equal(client.callbacks.size, 0);
});

test('GetSet writes report missing parameters on empty value or name and retain the confirmed cache', () => {
    const client = node(11);
    const cached = paramResponse('OPTION', 'integer_value', 12);
    client.updateNodeParamsFromResponse({ sourceNodeId: 125, payload: cached }, 3);
    const emptyValue = new DSDL.uavcan_protocol_param_GetSet_Response();
    emptyValue.fields.name.fromString('OPTION');
    const errors = [];
    for (const res of [emptyValue, paramResponse('', 'integer_value', 15)]) {
        const request = client.setNodeParam(125, 3, 15, error => errors.push(error.code));
        deliver(client, reply(request, res));
        assert.equal(client.nodeParams[125][3], cached);
    }
    assert.deepEqual(errors, ['PARAM_NOT_FOUND', 'PARAM_NOT_FOUND']);
    assert.equal(client.callbacks.size, 0);
});

test('concurrent writes respect confirmation order and a subsequent parameter fetch', () => {
    for (const firstReply of [0, 1]) {
        const client = node(11);
        const result = value => paramResponse('P', 'integer_value', value);
        client.updateNodeParamsFromResponse({ sourceNodeId: 125, payload: result(0) }, 0);
        const writes = [1, 2].map(value => client.setNodeParam(125, 0, value));
        for (const i of [firstReply, 1 - firstReply]) deliver(client, reply(writes[i], result(i + 1)));
        assert.equal(client.nodeParams[125][0].fields.value.msg.unionField.value, 2);
        const last = client.setNodeParam(125, 0, 3);
        client.updateNodeParamsFromResponse({ sourceNodeId: 125, payload: result(4) }, 0);
        deliver(client, reply(last, result(3)));
        assert.equal(client.nodeParams[125][0].fields.value.msg.unionField.value, 4);
    }
});

test('node helpers use the DSDL ranges and accept typed channel and UID buffers', () => {
    const n = node(11);
    const frames = [];
    n.on('sendFrame', (_id, data) => frames.push(Buffer.from(data)));
    for (const uid of [[0, 128, 255], Uint8Array.of(0, 128, 255), Buffer.from([0, 128, 255])]) {
        n.sendUavcanProtocolDynamicNodeIdAllocation(true, 42, uid);
        assert.deepEqual([...frames.at(-1).subarray(1, 4)], [0, 128, 255]);
    }
    const cmd = n.sendUavcanEquipmentActuatorArrayCommand(0, [{ id: 255, type: 4, value: 1500 }]);
    assert.equal(cmd.payload.toObj().commands[0].actuator_id, 255);
    assert.deepEqual(n.sendUavcanEquipmentEscRawCommand(0, Int16Array.of(-8192, 8191)).payload.toObj().cmd, [-8192, 8191]);
    const before = frames.length;
    assert.throws(() => n.sendUavcanEquipmentEscRawCommand(0, [8192]), RangeError);
    assert.throws(() => n.sendUavcanEquipmentActuatorArrayCommand(0, [{ id: 256, type: 4, value: 0 }]), RangeError);
    assert.throws(() => n.sendUavcanEquipmentActuatorArrayCommand(0, [{ id: 1, type: 4, value: NaN }]), RangeError);
    assert.equal(frames.length, before);
});

test('adapter remote and error frames cannot acknowledge a service request', () => {
    const client = node(11);
    let replies = 0;
    const request = client.fetchNodeParam(125, 0, '', () => replies++);
    const frames = reply(request, paramResponse('P', 'integer_value', 42)).toFrames();
    for (const flag of [0x40000000, 0x20000000]) {
        for (const frame of frames) client.emit('can-frame', frame.id | flag, frame.data, frame.data.length);
    }
    assert.equal(replies, 0);
    for (const frame of frames) client.emit('can-frame', frame.id, frame.data, frame.data.length);
    assert.equal(replies, 1);
});

test('discovery retries on the next heartbeat after a local send failure', () => {
    const observer = node(11);
    const other = node(42);
    other.on('sendFrame', (...args) => observer.emit('can-frame', ...args));
    const heartbeat = () => other.request({ req: other.status, serviceNotMessage: false });
    observer.once('sendFrame', () => { throw new Error('Adapter unavailable'); });
    heartbeat();
    assert.equal(observer.callbacks.size, 0);
    let requests = 0;
    observer.on('sendFrame', (...args) => {
        requests++;
        other.emit('can-frame', ...args);
    });
    heartbeat();
    heartbeat();
    assert.equal(observer.nodeMonitors[42].name, 'dronecan.js');
    assert.equal(requests, 1);
});
