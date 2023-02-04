#!/bin/bash

# == feel free to update the stack name
export STACKNAME=dashboard
# == update the path of the lambdaUpdate.py file (file is located here - https://github.com/massyn/cloudformation/blob/main/lambdaUpdate.py)
export LAMBDAUPDATE=../cloudformation/lambdaUpdate.py

# ================================================================================================
export CLOUDFORMATION=dashboard.json
# == deploy a new stack, or update it if it already exists
aws cloudformation describe-stacks --stack-name $STACKNAME > /dev/null 2>&1
if [[ $? -eq 0 ]]; then
    echo "Updating Cloudformation stack..."
    aws cloudformation update-stack --stack-name $STACKNAME --template-body file://$CLOUDFORMATION --capabilities CAPABILITY_IAM 
else
    echo "Creating a new Cloudformation stack..."
    aws cloudformation create-stack --stack-name $STACKNAME --template-body file://$CLOUDFORMATION --capabilities CAPABILITY_IAM 
fi
aws cloudformation wait stack-update-complete --stack-name $STACKNAME

# == Upload the config files to the repository
echo " == Upload configuration files to S3"
S3REPO=$(aws cloudformation describe-stacks --stack-name $STACKNAME --query "Stacks[0].Outputs[?OutputKey == 'S3RepositoryBucket' ].OutputValue" --output text)
echo " - $S3REPO"

if [ -f "hierarchy.json" ]; then
    aws s3 cp hierarchy.json s3://$S3REPO
else
    echo " ** skipping the upload of hierarchy.json since it does not exist **"
fi
if [ -f "metric.json" ]; then
    aws s3 cp metric.json s3://$S3REPO
else
    echo " ** skipping the upload of metric.json since it does not exist **"
fi

echo " == Update the Lambda function code..."
python $LAMBDAUPDATE -fn $STACKNAME-lambdaReport -files lambdaReport.py lambdaCGI.py template.json config.json
python $LAMBDAUPDATE -fn $STACKNAME-lambdaAggregate -files lambdaAggregate.py
python $LAMBDAUPDATE -fn $STACKNAME-lambdaIngestion -files lambdaIngestion.py

echo " == Configure event trigger..."
S3INGESTION=$(aws cloudformation describe-stacks --stack-name $STACKNAME --query "Stacks[0].Outputs[?OutputKey == 'S3IngestionBucket' ].OutputValue" --output text)
lambda=$(aws cloudformation describe-stacks --stack-name $STACKNAME --query "Stacks[0].Outputs[?OutputKey == 'lambdaIngestion' ].OutputValue" --output text)
aws s3api put-bucket-notification-configuration --bucket $S3INGESTION --notification-configuration "{\"LambdaFunctionConfigurations\": [{\"LambdaFunctionArn\": \"$lambda\",\"Events\": [\"s3:ObjectCreated:*\"]}]}"

echo "The path to the report is here..."
aws cloudformation describe-stacks --stack-name $STACKNAME --query "Stacks[0].Outputs[?OutputKey == 'lambdaReportFunctionUrl' ].OutputValue" --output text





