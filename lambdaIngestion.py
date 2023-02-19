import boto3
import json
import os
import datetime
import csv,codecs

def produceHierarchyLookupTable(hierarchy):
    print('produceHierarchyLookupTable')
    def leaf(x,H,parent = ''):
        for y in x:
            # The first item is the main leaf.  Anything after that are either alternate names, wildcards, or CIDR addresses
            i = y.split('|')
            me = i[0]
            key = f"{parent}/{me}"

            if '/' in me:
                print(f' ** You cannot have a / in the hierarchy table! -- {y}')
                exit(1)
                return { 'statusCode': 400, 'body': f' ** You cannot have a / in the hierarchy table! -- {y}' }

            # create the children leaf
            if parent == '':
                cParent = '/'
            else:
                cParent = parent

            if not cParent in H['children']:
                H['children'][cParent] = []
            if not key in H['children'][cParent]:
                H['children'][cParent].append(key)

            # Use case - use the hierarchy defined as is
            H["direct"][me] = key

            for a in i:
                if '*' in a:
                    # Use case - a hierarchy leaf could be a wildcard
                    if not a in H['wildcard']:
                        H['wildcard'][a] = key
                elif '/' in a:
                    # Use case - a hierarchy leaf could be an IP address CIDR
                    if not a in H['cidr']:
                        H['cidr'][a] = key
                else:
                    # Use case - a hierarchy leaf could have an alternate name
                    if not a in H['direct']:
                        H['direct'][a] = key

            if type(x) == dict:
                leaf(x[y],H,key)
            
    H = { "direct" : {}, "wildcard" : {}, "cidr" : {}, "children" : {} }

    # == add an "Unknown" hierarchy item
    if not 'Unknown' in hierarchy:
        hierarchy["Unknown"] = []

    leaf(hierarchy,H)

    return H

def lookupMetric(key,metric):
    print('lookupMetric')
    # -- look for the metric
    myMetric = None
    for m in metric:
        if key.startswith(m['id']):
            print(f" -- found metric id {m['id']}")
            if not 'weight' in m:
                m['weight'] = 1
                print(f" ** no weight found in {m['id']} - defaulting to 1")
            else:
                m['weight'] = float(m['weight'])
            if not 'target' in m:
                m['target'] = 0.9
                print(f" ** no target found in {m['id']} - defaulting to 0.9")
            else:
                m['target'] = float(m['target'])

            myMetric = m
    if myMetric == None:
        print("ERROR - No metric found")
        exit(1)
    
    # -- add the processedDate -- useful to identify when the measure was uploaded
    myMetric['_ProcessedDate'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return myMetric

def processInputFile(key,hierarchy,rawdata):
    def lookupHierarchy(H,item):
        if item in H['direct']:
            return H['direct'][item]
        else:
            # TODO - Wildcard

            # TODO - CIDR
            return "/Unknown"

    def processInputJSON(output,rawdata,hierarchy):
        data = json.loads(rawdata)
        heads = {}
        row = 0
        for item in data:
            if row == 0:
                heads = list(item.keys())
                output['heads'] = heads

                if not 'mapping' in heads:
                    print('** WARNING - no mapping field - defaults to Unknown')
                if not 'compliance' in heads:
                    print('** WARNING - no compliance field - defaults to 0')

                
            # -- main fields
            mapping = item.get('mapping','Unknown')
            compliance = item.get('compliance',0)

            # -- lookup the hierarchy
            H = lookupHierarchy(hierarchy,mapping)

            # -- detail
            if not H in output['detail']:
                output['detail'][H] = []

            # -- we do it like this to ensure the data always has the same fields.  This is to reduce the size of the detail file
            thisrow = []
            for h in heads:
                thisrow.append(item.get(h,''))
            output['detail'][H].append(thisrow)

            # -- record the summary by rolling it up the hierarchy
            H2 = ''
            for x in (H.split('/')):
                H2 += f'/{x}'
                H2 = H2.replace('//','/')

                if not H2 in output['summary']:
                    output['summary'][H2] = [ 0,0]

                # Ignore (skip) any item where the compliance is -1s
                if float(compliance) >= 0:
                    output['summary'][H2][0] += float(compliance)
                    output['summary'][H2][1] += 1.0

            row += 1
            
        return output

    def processInputCSV(output,rawdata,hierarchy):
        row = 0
        heads = {}
        for l in rawdata.split('\n'):
            if l != '':
                for c in csv.reader([l], delimiter=',', quotechar='"'):
                    if row == 0:
                        # -- header row
                        for (i,h) in enumerate(c):
                            heads[h] = i
                        output['heads'] = heads

                        if not 'mapping' in heads:
                            print('** WARNING - no mapping field - defaults to Unknown')
                        if not 'compliance' in heads:
                            print('** WARNING - no compliance field - defaults to 0')
                    else:
                        # -- detail row
                        if not 'mapping' in heads:
                            mapping = 'Unknown'
                        else:
                            mapping = c[heads['mapping']]

                        # -- lookup the hierarchy
                        H = lookupHierarchy(hierarchy,mapping)

                        if not 'compliance' in heads:
                            compliance = 0.0
                        else:
                            compliance = c[heads['compliance']]

                        # -- record the detail
                        if not H in output['detail']:
                            output['detail'][H] = []
                        output['detail'][H].append(c)

                        # -- record the summary by rolling it up the hierarchy
                        H2 = ''
                        for x in (H.split('/')):
                            H2 += f'/{x}'
                            H2 = H2.replace('//','/')

                            if not H2 in output['summary']:
                                output['summary'][H2] = [ 0,0 ]
                            if float(compliance) >=0 :
                                output['summary'][H2][0] += float(compliance)
                                output['summary'][H2][1] += 1.0
                row += 1
        return output

    print("processInputFile")
    output = {
        "summary" : {},
        "heads" : {},
        "detail" : {}
    }

    # -- what kind of file is this?
    if key.endswith('.json'):
        print('** Identified as a json file')
        processInputJSON(output,rawdata,hierarchy)
    elif key.endswith('.csv'):
        print('** Identified as a csv file')
        processInputCSV(output,rawdata,hierarchy)
    else:
        print(' ** Unknown data file type - filename must be either .csv or .json **')
        exit(1)

    return output

def lambda_handler(event, context):

    s3 = boto3.client('s3', region_name = os.environ['AWS_REGION'])

    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        print(f" bucket = {bucket} , key = {key}")
        
        # -- read the file
        hierarchy = s3.get_object(Bucket=os.environ['S3RepositoryBucket'], Key='hierarchy.json')['Body'].read().decode('utf-8')
        metric = s3.get_object(Bucket=os.environ['S3RepositoryBucket'], Key='metric.json')['Body'].read().decode('utf-8')
        rawdata = s3.get_object(Bucket=bucket, Key=key)['Body'].read().decode('utf-8')
        
        files = main_process(hierarchy,metric,key,rawdata)

        if files != None:
            for file in files:
                print(f"Writing output file = {file}")
                s3.put_object(
                    Body = json.dumps(files[file]),
                    Bucket = os.environ['S3RepositoryBucket'],
                    Key = file
                )
        else:
            print("Not writing anything")

        # -- delete the file
        print(f"Deleting {key}")
        s3.delete_object(Bucket=bucket, Key=key)
        
    return { 'statusCode': 200, 'body': 'Weird operation or not received' }

def main_process(hierarchy,metric,key,rawdata):
    
    HLT = produceHierarchyLookupTable(json.loads(hierarchy))
    myMetric = lookupMetric(key,json.loads(metric))
    output = processInputFile(key,HLT,rawdata)

    # == where to write the files to
    slot = "{:04d}-{:02d}".format(datetime.date.today().year,datetime.date.today().month)

    return {
        f"{slot}/metric.json"                   : json.loads(metric),
        f"{slot}/hierarchy.json"                : json.loads(hierarchy),
        f"{slot}/{myMetric['id']}/summary.json" : output['summary'],
        f"{slot}/{myMetric['id']}/detail.json" : {
            'heads' : output['heads'],
            'detail' : output['detail']
        },
        f"{slot}/{myMetric['id']}/metric.json"  : myMetric
    }

    

# ============    
def main_cli(key):
    def readfile(f):
        print(f'Reading {f}')
        with open(f,'rt') as q:
            return q.read()

    hierarchy = readfile('hierarchy.json')
    metric = readfile('metric.json')
    rawdata = readfile(key)

    output = main_process(hierarchy,metric,key,rawdata)

    print(json.dumps(output,indent=4))

if __name__ == '__main__':
    main_cli('CSV-001.csv')
    main_cli('AWS-001.json')
