/***
    Author: Huibean Luo <huibean.luo@vimdrones.com>
***/

const { mavlink20, MAVLink20Processor } = require('./mavlink');
const dgram = require('dgram');
const server = dgram.createSocket('udp4');
const dronecan = require('../dronecan');

// set up global variables to be used in the REPL
global.dronecan = dronecan;
global.localNode = new dronecan.Node({nodeId:120});

clients = new Set();
// const logger = console;
const logger = null;
const systemId = 255;
const componentId = 0;
let targetSystem = 255;
let targetComponent = 0;
const mavlinkProcessor = new MAVLink20Processor(logger, systemId, componentId);

const sendMavlinkMsg = (msg) => {
    let buf = Buffer.from(msg.pack(mavlinkProcessor));
    let index = 0;
    clients.forEach(client => {
        const [address, port] = client.split(':');
        if (index === 0) {
            server.send(buf, 0, buf.length, parseInt(port), address, (err) => {
                if (err) {
                    console.error(`Failed to send message to ${client}: ${err.message}`);
                }
            });
        }
        index++;
    });
}

const enableMavlinkCanForward = (bus) => {
    const msg = new mavlink20.messages.command_long(
        targetSystem, // target_system
        targetComponent, // target_component
        mavlink20.MAV_CMD_CAN_FORWARD, // command
        0, // confirmation
        bus + 1, // param1
        0, // param2
        0, // param3
        0, // param4
        0, // param5
        0, // param6
        0 // param7
    );
    sendMavlinkMsg(msg);
}

server.on('error', (err) => {
    console.error(`Server error:\n${err.stack}`);
    server.close();
});

server.on('message', (msg, rinfo) => {
    const clientInfo = `${rinfo.address}:${rinfo.port}`;
    clients.add(clientInfo);
    // console.log(`Server got: ${msg} from ${clientInfo}`);
    // console.log(`Current clients: ${Array.from(clients).join(', ')}`);
    const data = new Uint8Array(msg);
    const messages = mavlinkProcessor.parseBuffer(data);
    if (messages.length > 0) {
        messages.forEach((message) => {
            // console.log(message);
            let name = message._name;
            let srcSystem = message._header.srcSystem;
            let srcComponent = message._header.srcComponent;
            let msgId = message._header.msgId;
            switch (msgId) {
                case mavlink20.MAVLINK_MSG_ID_HEARTBEAT:
                    // console.log('Heartbeat:', message);
                    targetSystem = srcSystem;
                    targetComponent = srcComponent;
                    enableMavlinkCanForward(localNode.bus);
                    break;
                case mavlink20.MAVLINK_MSG_ID_CAN_FRAME:
                    let isExtended = message.id & dronecan.TransferManager.FlagEFF;
                    if (isExtended) {
                        localNode.emit('can-frame', message.id, message.data, message.len);
                    } else {
                        console.log('Standard frame');
                    }
                    break;
            };
        });
    }
});

server.on('listening', () => {
    const address = server.address();
    console.log(`Server listening ${address.address}:${address.port}`);
});

server.bind(14550, '127.0.0.1');

// locadNode
localNode.on('nodeList', (nodeList) => {
    // console.log('Node list:', nodeList);
});

localNode.on('uavcan.protocol.NodeStatus', (transfer) => {
    const msg = transfer.payload;
    console.log(msg.toObj());
});

localNode.on('uavcan.equipment.actuator.ArrayCommand', (transfer) => {
    // const msg = transfer.payload;
    // console.log(msg.toObj());
});

localNode.on('sendFrame', (messageId, data, len) => {
    const msg = new mavlink20.messages.can_frame(
        targetSystem, // target_system
        targetComponent, // target_component
        localNode.bus, // bus
        len,
        messageId,
        data.toString('binary')
    );
    sendMavlinkMsg(msg);
});

// localNode.fetchNodeParams(125, 0);