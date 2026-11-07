# trace_node (remote)

Inputs: newly created isolated ES8 client and metrics list. Wrap only that client's native nodes in the standalone probe. Does not patch production clients or classes. Outputs original client, preserving original requests/results; records duration, decoded body byte count, content-length and encoding. SQL: none. No ES mutations.
