## DroneCAN DSDL JavaScript
#### A JavaScript implementation of the DroneCAN/UAVCAN protocol stack with automatic code generation from DSDL definitions.


Installing from Git or building from source requires Python 3 and PyDroneCAN (`python3 -m pip install dronecan`). In a fresh checkout, `npm ci` prepares the standard bindings.

```
npm ci
```

To build with a specific DSDL checkout, pass its namespace directories.

```
npm run build -- ./DSDL/dronecan ./DSDL/ardupilot ./DSDL/uavcan ./DSDL/com
```

The generated module exposes source versions and fingerprints through `bindingInfo`. `npm pack` includes the selected build. Run `npm run build` to switch back to the standard definitions.

Run example
```
node examples/node_test.js
```

### Tests

Run `npm run test:all` for the JavaScript and generator tests. The JavaScript suite builds its bindings in a temporary directory.
