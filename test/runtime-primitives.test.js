const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const test = require('node:test');
const ArrayType = require('../dronecan/array_type');
const CompoundType = require('../dronecan/compound_type');
const DSDL = require('../dronecan/dsdl');
const PrimitiveType = require('../dronecan/primitive_type');

const {
    KIND_BOOLEAN: BOOL,
    KIND_UNSIGNED_INT: UINT,
    KIND_SIGNED_INT: INT,
    KIND_FLOAT: FLOAT,
    CAST_MODE_SATURATED: SATURATED,
    CAST_MODE_TRUNCATED: TRUNCATED
} = PrimitiveType;

function hex(bits) {
    const bytes = Buffer.alloc(Math.ceil(bits.length / 8));
    bits.forEach((bit, index) => { bytes[Math.floor(index / 8)] |= bit << (7 - index % 8); });
    return bytes.toString('hex');
}

function roundTrip(value, kind, width, mode) {
    const field = new PrimitiveType(value, kind, width, mode);
    return PrimitiveType.unpack(kind, field.pack(), width, mode);
}

test('integer primitives round-trip all widths with the correct wire order and sign', () => {
    for (let width = 1; width <= 64; width++) {
        const unsignedMax = (1n << BigInt(width)) - 1n;
        const signedMin = -(1n << BigInt(width - 1));
        for (const [kind, value] of [[UINT, unsignedMax], [INT, signedMin], [INT, -1n]]) {
            const actual = roundTrip(value, kind, width).value;
            assert.equal(actual, Number.isSafeInteger(Number(value)) ? Number(value) : value);
        }
    }
    assert.equal(hex(new PrimitiveType(0xabc, UINT, 12).pack()), 'bca0');
    assert.equal(hex(new PrimitiveType(-1, INT, 5).pack()), 'f8');
    assert.equal(hex(new PrimitiveType(-1, INT, 48).pack()), 'ffffffffffff');
    assert.equal(roundTrip(true, BOOL, 1).value, true);
    assert.equal(new PrimitiveType(true, BOOL, 1).toObj(), 1);

    const rc = DSDL.dronecan_sensors_rc_RCInput.unpack(Buffer.from('0100501dc5d07008fff0', 'hex'));
    assert.deepEqual(rc.toObj().rcin, [1500, 2000, 2048, 4095]);
    const esc = DSDL.uavcan_equipment_esc_StatusExtended.unpack(Buffer.from('00000059000000', 'hex'));
    assert.equal(esc.toObj().motor_angle, 300);
    const tunnel = DSDL.uavcan_tunnel_Targetted.unpack(Buffer.from('00fbf0000000', 'hex'));
    assert.equal(tunnel.toObj().serial_id, -1);
    assert.equal(hex(tunnel.pack()), '00fbf0000000');
});

test('integers retain their exact values across decoding and object conversion', () => {
    const int64 = 9007199254740993n;
    for (const value of [int64, -int64]) {
        const decoded = roundTrip(value, INT, 64);
        assert.equal(decoded.value, value);
        assert.equal(decoded.toObj(), value);
    }
    assert.equal(roundTrip(Number.MAX_SAFE_INTEGER, UINT, 64).value, Number.MAX_SAFE_INTEGER);
    assert.throws(() => new PrimitiveType(Number.MAX_SAFE_INTEGER + 1, UINT, 64).pack(), /safe Number range/);

    const bytes = '00000000000000efcdab8967452301';
    const version = DSDL.uavcan_protocol_SoftwareVersion.unpack(Buffer.from(bytes, 'hex'));
    assert.equal(version.toObj().image_crc, 0x0123456789abcdefn);
    assert.equal(hex(version.pack()), bytes);
});

test('saturated and truncated integer casts preserve the respective limits and low bits', () => {
    assert.equal(roundTrip(33, UINT, 5, SATURATED).value, 31);
    assert.equal(roundTrip(33, UINT, 5, TRUNCATED).value, 1);
    assert.equal(roundTrip(-20, INT, 5, SATURATED).value, -16);
    assert.equal(roundTrip(-20, INT, 5, TRUNCATED).value, 12);
    const field = roundTrip(0xabc, UINT, 12, TRUNCATED);
    assert.equal(field.value, 0xabc);
    assert.equal(field.cast_mode, TRUNCATED);
    assert.equal(roundTrip(-1, UINT, 56, TRUNCATED).value, 0xffffffffffffffn);
    assert.equal(roundTrip(-1, UINT, 56, SATURATED).value, 0);
});

test('floating-point packing rounds half precision and respects finite and NaN encodings', () => {
    const half = value => hex(new PrimitiveType(value, FLOAT, 16).pack());
    assert.equal(half(0.9999), '003c');
    assert.equal(half(-0.01), '1fa1');
    assert.equal(half(5e-8), '0100');
    assert.equal(half(70000), 'ff7b');
    assert.equal(half(-0), '0080');
    assert.ok(Object.is(roundTrip(-0, FLOAT, 16).value, -0));
    assert.equal(roundTrip(70000, FLOAT, 16, TRUNCATED).value, Infinity);
    assert.equal(roundTrip(-70000, FLOAT, 16, SATURATED).value, -65504);
    assert.equal(roundTrip(Infinity, FLOAT, 64).value, Number.MAX_VALUE);
    assert.equal(hex(new PrimitiveType(NaN, FLOAT, 64).pack()), '000000000000f87f');
    assert.ok(Number.isNaN(roundTrip(NaN, FLOAT, 64).value));
});

test('forwarding a decoded float preserves its wire encoding until the next assignment', () => {
    const wire = '007c00fc0080'; // +Infinity, -Infinity, -0
    const message = DSDL.uavcan_equipment_ahrs_MagneticFieldStrength.unpack(Buffer.from(wire, 'hex'));
    assert.deepEqual(message.toObj().magnetic_field_ga, [Infinity, -Infinity, -0]);
    assert.equal(hex(message.pack()), wire);
    const [positive, negative] = message.fields.magnetic_field_ga.items;
    positive.value = Infinity;
    negative.value = 1;
    assert.equal(hex(message.pack()), 'ff7b003c0080');

    for (const [width, payload] of [[16, '017c'], [32, '010080ff'], [64, '020000000000f0ff']]) {
        const bits = Buffer.from(payload, 'hex').getBits(0, width);
        const field = PrimitiveType.unpack(FLOAT, bits, width);
        assert.ok(Number.isNaN(field.value));
        assert.equal(hex(field.pack()), payload);
        field.value = NaN;
        assert.equal(hex(field.pack()), hex(new PrimitiveType(NaN, FLOAT, width).pack()));
    }
});

test('byte arrays encode UTF-8 paths and allow lossless binary reads and writes', () => {
    const path = new DSDL.uavcan_protocol_file_Path();
    path.fields.path.fromString('配置.bin');
    const bytes = 'e9858de7bdae2e62696e';
    assert.equal(hex(path.pack()), bytes);
    assert.equal(DSDL.uavcan_protocol_file_Path.unpack(Buffer.from(bytes, 'hex')).fields.path.toString(), '配置.bin');

    const byteArray = new ArrayType(new PrimitiveType(null, UINT, 8), ArrayType.MODE_DYNAMIC, 3);
    byteArray.fromBytes([0, 128, 255]);
    assert.deepEqual(byteArray.toBytes(), Buffer.from([0, 128, 255]));
    assert.deepEqual(byteArray.toObj(true), [0, 128, 255]);
    assert.throws(() => byteArray.fromString('配置'), /Array is full/);
    assert.deepEqual(byteArray.toBytes(), Buffer.from([0, 128, 255]));
});

test('compound arrays expose outbound entries and static arrays get independent defaults', () => {
    const arrayCommand = new DSDL.uavcan_equipment_actuator_ArrayCommand();
    const command = new DSDL.uavcan_equipment_actuator_Command();
    command.fields.actuator_id.value = 1;
    command.fields.command_value.value = 0.5;
    arrayCommand.fields.commands.push(command);
    const packed = hex(arrayCommand.pack());
    const received = DSDL.uavcan_equipment_actuator_ArrayCommand.unpack(Buffer.from(packed, 'hex'));
    assert.equal(packed, '01000038');
    assert.deepEqual(JSON.parse(JSON.stringify(arrayCommand.toObj().commands)), [{ actuator_id: 1, command_type: 0, command_value: 0.5 }]);
    assert.deepEqual(JSON.parse(JSON.stringify(received.toObj().commands)), JSON.parse(JSON.stringify(arrayCommand.toObj().commands)));

    const sample = new CompoundType(new DSDL.uavcan_equipment_actuator_Command());
    const fixedArray = new ArrayType(sample, ArrayType.MODE_STATIC, 2);
    assert.equal(fixedArray.getNormalizedDefinition(), 'uavcan.equipment.actuator.Command[2]');
    assert.equal(fixedArray.getMinBitlen(), 64);
    assert.equal(fixedArray.getMaxBitlen(), 64);
    fixedArray.items[0].fields.actuator_id.value = 4;
    assert.equal(fixedArray.items[1].fields.actuator_id.value, 0);
    assert.equal(sample.fields.actuator_id.value, 0);
});

test('compound metadata and default values match the generated DSDL bindings', () => {
    const read = new DSDL.uavcan_protocol_file_Read_Request();
    const wrapper = new CompoundType(read);
    assert.equal(wrapper.default_dtid, read.dataTypeId);
    assert.equal(wrapper.getDataTypeSignature(), read.getDataTypeSignature());
    assert.equal(wrapper.getDsdlSignature(), read.getDsdlSignature());
    assert.equal(wrapper.getDsdlSignatureSourceDefinition(), read.getDsdlSignatureSourceDefinition());
    assert.notEqual(wrapper.getDsdlSignature(), wrapper.getDataTypeSignature());
    assert.equal(hex(wrapper.pack()), '0000000000');
    assert.equal(hex(new DSDL.uavcan_protocol_param_GetSet_Request().pack()), '0000');
    assert.equal(hex(new DSDL.uavcan_equipment_ahrs_MagneticFieldStrength().pack()), '000000000000');
});

test('JSON export preserves nested 64-bit integers as decimal strings and leaves safe numbers numeric', async () => {
    // The formatter is a browser ES module inside the CommonJS package.
    const source = readFileSync(require.resolve('../dronecan/message_format_utils.js'), 'base64');
    const { toJson } = await import('data:text/javascript;base64,' + source);
    const response = new DSDL.uavcan_protocol_GetNodeInfo_Response();
    const version = response.fields.software_version.msg;
    version.fields.image_crc.value = 0x0123456789abcdefn;
    version.fields.vcs_commit.value = 12345678;
    const json = JSON.parse(toJson(response));
    assert.equal(json.software_version.image_crc, '81985529216486895');
    assert.equal(json.software_version.vcs_commit, 12345678);
    assert.ok(!Object.hasOwn(json.software_version, 'getConstant'));
    assert.deepEqual(JSON.parse(toJson({ values: [0, -9007199254740993n] })),
        { values: [0, '-9007199254740993'] });
});
