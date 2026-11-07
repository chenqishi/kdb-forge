# es8_stack.perform_request

## Inputs
Existing elastic_transport.Transport.perform_request protocol, learned from installed 8.17 client/transport source.

## Outputs
TransportApiResponse with product header, recorded host/method/path/query/body. Supports only test get/update/delete/refresh/search; unknown requests fail. No network.

## SQL
None; offline only.
