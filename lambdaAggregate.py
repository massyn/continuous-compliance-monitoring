import boto3
import datetime
import os
import json

def lambda_handler(event, context):

    # -- setup the S3 resource -- we will use this a few times
    s3 = boto3.client('s3', region_name = os.environ['AWS_REGION'])
    
    # -- the aggregator will only aggregate all metrics for the current slot
    slot = "{:04d}-{:02d}".format(datetime.date.today().year,datetime.date.today().month)
    try:
        print(f"Slot {slot} has a metric")
        metric = json.loads(s3.get_object(Bucket=os.environ['S3RepositoryBucket'], Key=f'{slot}/metric.json')['Body'].read().decode('utf-8'))
    except:
        print(f"There is no metric yet for slot {slot}")
        metric = []

    thisSlot = {}
    if metric != []:
 
        for x in metric:
            id = x['id']
            if not '/' in thisSlot:
                thisSlot['/'] = {}

            if x.get('status',True) != False:
                # -- now we try to read it
                try:
                    print(f"{id} has data")
                    summary = json.loads(s3.get_object(Bucket=os.environ['S3RepositoryBucket'], Key=f"{slot}/{id}/summary.json")['Body'].read().decode('utf-8'))
                except:
                    print(f"There is no data yet for metric {id} for slot {slot}")
                    summary = {}
                    thisSlot['/'][id] = [ -1, -1 ]
    
                for h in summary:
                    if not h in thisSlot:
                        thisSlot[h] = {}
                    thisSlot[h][id] = summary[h]
            else:
                print(f"Metric {id} is disabled -- skipping")
                # -- if it is switched off, remove any data we have of it
               
    # == write the aggregate back to disk
    s3.put_object(
        Body = json.dumps(thisSlot),
        Bucket = os.environ['S3RepositoryBucket'],
        Key = f"{slot}/aggregate.json"
    )

    return { 'statusCode': 200, 'body': 'All good' }