# metric.json

The `metric.json` defines the list of metrics currently in use by the dashboard.  The file lives in the S3 bucket (`S3RepositoryBucket`) from the [cloudformation stack](../dashboard.json).

## Example

```json
[
    {
        "id" : "MET-001",
        "title" : "My very first Metric",
        "target" : 0.95,
        "weight" : 1,
        "status" : true
    }
]
```