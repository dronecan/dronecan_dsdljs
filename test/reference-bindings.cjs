// Invoked by test_reference_bindings.py with independent PyDroneCAN expectations on stdin.
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const generated = require(process.argv[2]);
const references = JSON.parse(readFileSync(0, 'utf8'));

function checkBinding(bindings, key, ref) {
    const Type = bindings[key];
    assert.ok(Type, key + ' missing from exports');
    assert.equal(Type.FULL_NAME, ref.name, key);
    assert.equal(Type.DTID, ref.dtid, key);
    assert.equal(Type.getDataTypeSignature().toString(), ref.signature, key);
    if (ref.dtid !== null) {
        const registered = ref.direction ? bindings.services[ref.dtid]?.[ref.direction] : bindings.messages[ref.dtid];
        assert.equal(registered, Type, key + ' registry lookup');
    }
    for (const { tao, bits, hex } of ref.defaults) {
        const context = key + ' default, tao=' + tao;
        assert.equal(new Type().pack(tao).join(''), bits, context);
        const decoded = Type.unpack(Buffer.from(hex, 'hex'), tao);
        assert.equal(decoded.bitOffset, bits.length, context);
        assert.equal(decoded.pack(tao).join(''), bits, context);
    }
    for (const { tao, bits, hex } of ref.populated || []) {
        const context = key + ' populated, tao=' + tao;
        const decoded = Type.unpack(Buffer.from(hex, 'hex'), tao);
        const obj = decoded.toObj();
        for (const [field, expected] of Object.entries(ref.fields)) {
            // The object API projects DSDL bools as 0 or 1.
            assert.deepEqual(obj[field], typeof expected === 'boolean' ? Number(expected) : expected, context + '.' + field);
        }
        assert.equal(decoded.bitOffset, bits.length, context);
        assert.equal(decoded.pack(tao).join(''), bits, context);
    }
}

const expectedKeys = [...Object.keys(references), 'messages', 'services'];
assert.deepEqual(Object.keys(generated).sort(), expectedKeys.sort(), 'generated binding exports');
for (const [key, ref] of Object.entries(references)) {
    checkBinding(generated, key, ref);
}
console.log(`PyDroneCAN matched ${Object.keys(references).length} generated bindings`);
