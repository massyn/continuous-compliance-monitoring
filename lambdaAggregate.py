import boto3
import datetime
import os
import json

def lambda_handler(event, context):
    

    s3 = boto3.client('s3', region_name = os.environ['AWS_REGION'])

    try:
        aggregate = json.loads(s3.get_object(Bucket=os.environ['S3RepositoryBucket'], Key='aggregate.json')['Body'].read().decode('utf-8'))
        print(' -- reading the file --')
    except:
        aggregate = {}
        print(' -- start a fresh file --')
    
    if not 'hierarchy' in aggregate:
        aggregate['hierarchy'] = {}
    
    # Update the data in the slot
    slot = "{:04d}-{:02d}".format(datetime.date.today().year,datetime.date.today().month)
    try:
        print(f"Slot {slot} has a metric")
        metric = json.loads(s3.get_object(Bucket=os.environ['S3RepositoryBucket'], Key=f'{slot}/metric.json')['Body'].read().decode('utf-8'))
    except:
        print(f"There is no metric yet for slot {slot}")
        metric = []

    if metric != []:
        # store the metric for the month
        if not 'metric' in aggregate:
            aggregate['metric'] = {}
        aggregate['metric'][slot] = metric
        
        for x in metric:
            id = x['id']
            if not '/' in aggregate['hierarchy']:
                aggregate['hierarchy']['/'] = {}
            if not slot in aggregate['hierarchy']['/']:
                aggregate['hierarchy']['/'][slot] = {}

            if x.get('status',True) != False:
                # -- now we try to read it
                try:
                    print(f"{id} has data")
                    summary = json.loads(s3.get_object(Bucket=os.environ['S3RepositoryBucket'], Key=f"{slot}/{id}/summary.json")['Body'].read().decode('utf-8'))
                    thisMetric = json.loads(s3.get_object(Bucket=os.environ['S3RepositoryBucket'], Key=f"{slot}/{id}/metric.json")['Body'].read().decode('utf-8'))
                except:
                    print(f"There is no data yet for metric {id} for slot {slot}")
                    summary = {}
                    aggregate['hierarchy']['/'][slot][id] = {
                        'title'     : x['title'],
                        'weight'    : x['weight'],
                        'target'    : x['target'],
                        'totalok'   : 0,
                        'total'     : 0,
                        'timestamp' : None
                    }
    
                for h in summary:
                    if not h in aggregate['hierarchy']:
                        aggregate['hierarchy'][h] = {}
                    
                    if not slot in aggregate['hierarchy'][h]:
                        aggregate['hierarchy'][h][slot] = {}

                    aggregate['hierarchy'][h][slot][id] = {
                        'title'     : x['title'],
                        'weight'    : x['weight'],
                        'target'    : x['target'],
                        'totalok'   : summary[h][0],
                        'total'     : summary[h][1],
                        'timestamp' : thisMetric['_ProcessedDate']
                    }
            else:
                print(f"Metric {id} is disabled -- skipping")
                # -- if it is switched off, remove any data we have of it
                for h in aggregate['hierarchy']:
                    if id in aggregate['hierarchy'][h][slot]:
                        print(f" - Removing data from hierarchy {h}")
                        del aggregate['hierarchy'][h][slot][id]

    


    # == write the aggregate back to disk
    s3.put_object(
        Body = json.dumps(aggregate),
        Bucket = os.environ['S3RepositoryBucket'],
        Key = 'aggregate.json'
    )

    return { 'statusCode': 200, 'body': 'All good' }