# post_query

## Inputs
Original ASGI service, endpoint /search or /web_search, copied request JSON.

## Outputs
HTTP response from actual original handler with AsyncClient/ASGITransport closed. No HTTP listener started, only external ES/embedding boundaries replaced. /search ID is id; /web_search retains old _id.

## SQL
None.
