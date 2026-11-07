# AutoProbe.uuid

## Inputs
Exact approved fixture name and current metadata row.

## Outputs
Captured immutable index UUID. Serverless masks settings.uuid/creation_date; reuse existing documented GET /name/_stats/docs?filter_path=indices.*.uuid fallback. Require exactly requested index, nonempty string UUID. No mutation.

## SQL
None.
