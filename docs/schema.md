# Data Schema

This chapter describes the data schema, and a high-level process overview.

## Meta data

There are 2 key files that provide the structure for dealing with metrics.

### metrics.json

The `metric.json` defines the list of metrics currently in use by the dashboard.  The file lives in the S3 bucket (`S3RepositoryBucket`) from the [cloudformation stack](../dashboard.json).

|**Field**|**Description**|
|--|--|
|id|Unique identifier for the metric|
|title|A cosmetic title displayed on the dashboard|
|target|The target to achieve (a value between 0 and 1) used to drive the colour of the bar for that metric|
|weight|The weighted value to attribute to the metric.|
|status|Define if the metric is active or not|

#### Sample entry

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

### hierarchy.json

The `hierrachy.json` file is slightly more complicated.  The dashboard employs a mechanism to allow compliance objects to be mapped against a hierarchy.  What this means is the dashboard will allow you to represent data across an organization, based on the scope the owner would like to see.

A company may be operating across many countries, each with many states, and different offices across those states in different countries.  You may choose to operate a geographical hierarchy.  It may look a like this.

If the CEO wants to see everything for the whole company, the default view will include all objects.  If the regional manager of the Australian markets wanted to view the KPIs for his unit only, the hierarchy mapping would allow them to filter the data for that particular region only.

The hierarchy also offers the use of what is known as an _Alternate Mapping_.  Instead of just specifying the name of the level, you can specify multiple names for the same leaf, so where a level might be known as `New South Wales`, another way to represent it might be just `NSW`.  You can specify as many alternative names as you like, simply by adding more with the pipe separator.

The last level in the hierarchy is always a list.

```json
{
    "Australia" : {
        "New South Wales|NSW" : {
            "Greater Sydney" : [
                "Sydney-HQ",
                "Blacktown",
                "Penrith"
            ],
            "Newcastle" : {},
        },
        "Queensland|QLD" : [
            "Brisbane"
        ]
    }
}
```

Note that if for whatever reason you're only operating a single level, it should be stored as empty dictionaries.

```json
{
    "Australia" : {},
    "New Zealand" : {}
}
```

### Loading a metric

Now the real fun begins.  A metric can be either `json` or `csv`, and it suffix must end as either `.json` or `.csv` respectfully.  This allows the ingester to know how to parse the input file.

A metric (or a measure) is used to calculate how well a particular object or resource is aligned to a particular objective.  Assuming we want to measure how many servers have had a successful backup, we could create a metric like this.

```json
[
    {
        "id" : "INF-001",
        "title" : "% of servers with a successful backup in the last 24 hours",
        "target" : 0.99,
        "weight" : 1,
        "status" : true
    }
]
```

The second requirement for the filename is for the metric file name to begin with the metric ID.  In this example, a file name like `INF-001-2022-08-22.json` would be perfectly valid.

So in this example, we will list all servers in our environment and indicate if they had a successful backup or not.  We would extract the data from our backup tool and produce a metric upload file as follow

```json
[
    {
        "resource" : "ServerName1",
        "compliance" : 1,
        "last_successful_backup" : "2022-02-18 09:44",
        "mapping" : "Australia"
    },
    {
        "resource" : "ServerName2",
        "compliance" : 0,
        "last_successful_backup" : "2022-02-15 03:43",
        "mapping" : "New Zealand"
    }
]
```

Calling out the specific fields, we have

|**Field**|**Description**|
|--|--|
|resource|A recommended field name to use to refer to the specific object being measured|
|compliance|A float value (between 0 and 1) that indicates if the item is compliant or not|
|mapping|A field specifying where in the hierarchy to map the object to|
|- All other fields -|Cosmetically added to the report to add additional context|

#### A note about "compliance"

In most settings, something either is (1) or isn't (0) compliant.  You may be in a situation where you are measuring a particular item, and it provides you with a score.  One example is you have a metric that has compounded items to measure.  For example, if you measure end-user account compliance, you may dictate that users must change their passwords every 90 days, and they must have MFA enabled.  If they have only 1 of two items defined, their compliance score might be only `0.5` instead of a `1` or `0`.  How you define the score is entirely dependent on the design of your metric and its intended outcome.

You can also use `-1` as a compliance field to indicate resources that should be skipped.  They will still appear in the detailed report, but will not count toward any score calculation.  This is helpful to show that items have been detected but may have been excluded for any particular reason.

#### A note about "mapping"

When you specify the mapping field, you provide a name of an item within the hierarchy to map the object to.  If the mapping cannot be found, it will be mapped to `Unknown`

## Ingestion

As soon as the metric file hits the ingestion S3 bucket, the `lamdbaIngestion.py` function is triggered.  It will read the data, one record at a time.

For every record it will:

* Lookup the mapping against the hierarchy
* Count the total objects and compliance scores against the hierarchy.

### Mapping the hierarchy

Using our hierarchy above, if the mapping specifies `Sydney`, the hierarchy item will become `/Australia/New South Wales/Sydney`

Once the hierarchy level is identified, the `totalok` and `total` is calculated.  

* `totalok` is a sum of the `compliance` field
* `total` is a count of the total number of items

### Writing the output

A `slot` is a collection of files for the current month.  This ensures that a historical record is created for every month, allowing you to view previous months, and to see trends as time goes on.

A typical slot value will be `YYYY-MM`, for example `2023-02`

#### $slot/metric.json

The `metric.json` file is copied across to the slot.  This helps to retain a historical trace of what the valid measures were at this point in time.  Note that this file is overwritten by the last metric loaded for that month.

#### $slot/hierarchy.json

The `hierarchy.json` file is copied across to the slot.  This helps to retain a historical trace of what the hierarchy was at this point in time.  Note that this file is overwritten by the last metric loaded for that month.

#### $slot/$id/summary.json

The `summary.json` file contains a dictionary of the hierarchy with two fields : the `totalok`, and `total` count for that level in the hierarchy for the particular metric being loaded.

```json
{
    "/": [ 0.5, 2.0 ],
    "/Australia/New South Wales/Sydney" : [ 1.0, 1.0],
    "/Unknown": [0.5, 2.0]
}
```

#### $slot/$id/metric.json

The `metric.json` file is the dictionary of the specific metric loaded.

```json
{
    "id" : "INF-001",
    "title" : "% of servers with a successful backup in the last 24 hours",
    "target" : 0.99,
    "weight" : 1,
    "status" : true
}
```
    Note that the metric details is essentially duplicated from the `metric.json` file loaded into the `${slot}` field.  This is provided to allow quick and easy access to the metric currently loaded here.

#### $slot/$id/detail.json

The `detail.json` file contains the raw data, split by hierarchy.  This is necessary to allow the user to filter and show evidence that they are interested in.

The challenge with this file, is depending on the complexity of your hierarchy, it can get very big, very quickly.  To optimize the file size, the structure is as follow:

* A `heads` list contains the list of headers used
* A `detail` dictionary exists that contains a break down by each of the hierarchy items
* The detail then contains a list of lists which contains all the items, with the variables in the same order as provided in heads previously.

```json
{
    "heads": ["resource", "compliance", "mapping"],
    "detail": {
        "/Unknown": [
            ["item1", "0.0", "Australia"],
            ["item2", "-1.0", "South Africa"],
            ["item3", "0.5", "Unknown"]
        ]
    }
}
```

## Aggregator

The `lambdaAggregate.py` function is responsible to read the summary files from all metrics loaded in this slot, and combining them into a single file. 

### $slot/aggregate.json

The `aggregate.json` file in the individual `$slot` folders will have the following strucure

* Hierarchy
   * id
     * [ totalok , total ]

```json
{
    "/": {
        "IAM-001": [0.5, 2.0],
        "IAM-002": [1640.0, 1649.0]
    },
    "/Unknown": {
        "IAM-001": [0.5, 2.0],
        "INF-001": [0.0, 3.0]
    }
}
```

The `aggregate.json` file is recreated every time the lambda function executes.

## Report

TODO