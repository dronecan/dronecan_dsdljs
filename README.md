## DroneCAN DSDL JavaScript
#### A JavaScript implementation of the DroneCAN/UAVCAN protocol stack with automatic code generation from DSDL definitions.


The tool generates JavaScript classes from DSDL definitions. To generate bindings for the standard DroneCAN data types, run:
```
./dronecan_dsdljs.py ./DSDL/dronecan ./DSDL/ardupilot ./DSDL/uavcan ./DSDL/com --output ./dronecan
```

Run example
```
npm install
node examples/node_test.js
```