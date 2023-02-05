import boto3
import json
from zipfile import ZipFile
import io

def main(STACKNAME,TEMPLATE):
    # == are we actually logged on?
    try:
        AccountId = boto3.client('sts').get_caller_identity()['Account']
    except:
        print('You do not appear to be authenticated to AWS...')
        exit(1)

    print(f"AWS Account ID = {AccountId}")

    # == Does the stack already exist?
    cf = boto3.client('cloudformation')
    try:
        myStack = cf.describe_stacks(StackName = STACKNAME)['Stacks'][0]
    except:
        print(f"The stack {STACKNAME} does not exist")
        myStack = None

    # == Deploy or Update?
    with open(TEMPLATE,'rt') as j:
        StackTemplate = json.load(j)

    if myStack == None:
        print(f"Deploying a new stack - {STACKNAME}")
        x = cf.create_stack(
            StackName=STACKNAME,
            TemplateBody=json.dumps(StackTemplate),
            Capabilities=['CAPABILITY_IAM']
        )

        # -- wait until it is completed
        waiter = cf.get_waiter('stack_create_complete')
        waiter.wait(
            StackName=STACKNAME,
            WaiterConfig={
                'Delay': 5,
                'MaxAttempts': 123
            }
        )
    else:
        print(f"Updating an existing stack...")
        try:
            x = cf.update_stack(
                StackName=STACKNAME,
                TemplateBody=json.dumps(StackTemplate),
                Capabilities=['CAPABILITY_IAM']
            )
            waiter = cf.get_waiter('stack_update_complete')
            waiter.wait(
                StackName=STACKNAME,
                WaiterConfig={
                    'Delay': 5,
                    'MaxAttempts': 123
                }
            )
            
        except:
            print("TODO : we were unable to update the stack...")

    # -- Let's update the Lambda function code
    LamdaDef = { f"{STACKNAME}-lambdaReport" : ['lambdaReport.py' , 'lambdaCGI.py', 'template.json', 'config.json'],
          f"{STACKNAME}-lambdaAggregate" : ['lambdaAggregate.py'],
          f"{STACKNAME}-lambdaIngestion" : ['lambdaIngestion.py']
    }

    for L in LamdaDef:
        print(f"Update lambda {L}")

        # -- create a zip of the files...
        obj = io.BytesIO()
        with ZipFile(obj, 'w') as zip_object:
            row = 0
            for f in LamdaDef[L]:
                # Adding files that need to be zipped
                print(f" - Zipping -- {f}")
                if row == 0:
                    filename = 'index.py'
                else:
                    filename = f
                
                zip_object.write(f,filename)
                row += 1

        response = boto3.client('lambda').update_function_code(
            FunctionName=L,
            ZipFile=obj.getvalue(),
            Publish=True
        )


    # -- we need the stacks' output parameters - go grab it again in case we had some updates
    myStack = cf.describe_stacks(StackName = STACKNAME)['Stacks'][0]
    outputs = {}
    for x in myStack['Outputs']:
        outputs[x['OutputKey']] = x['OutputValue']

    # -- Update the S3 notification
    print(f"Creating the S3 notification...")
    response = boto3.client('s3').put_bucket_notification_configuration(
        Bucket=outputs['S3IngestionBucket'],
        NotificationConfiguration={
            'LambdaFunctionConfigurations': [
                {
                    'Id' : 'Update',
                    'LambdaFunctionArn': outputs['lambdaIngestion'],
                    'Events': [ 's3:ObjectCreated:*' ]
                }
            ]
        }
    )
    #print(response)
    print("=====================================")

    print(f"FunctionURL = {outputs['lambdaReportFunctionUrl']}")
    print(f"S3IngestionBucket = {outputs['S3IngestionBucket']}")

main('dashboardxx1','dashboard.json')