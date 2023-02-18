# continuous-compliance-monitoring
Continuous Compliance Monitoring

## Getting started

### Requirements

* You need an AWS account
* You need to have an AWS Cognito user pool configured.  You will need to know the `cognito_domain`, `client_id` and `client_secret`

### Installation

* Edit [config.json](docs/config.md) and update the cognito variables
   * You will need to leave the `redirect_url` empty until the end.
* Log onto the AWS account where the solution will be deployed (you may want to set the `AWS_REGION` variable to ensure the `deploy.py` script can get to AWS...)
* Run `deploy.py`
* On completion, you will receive the Lambda function URL.
* When you get the Lambda function URL, update the `config.json` file's `redirect_url` parameter with that URL.
* You will need to also update Cognito with the updated URL.
* Run `deploy.py` again to update the `config.json` file in the Lambda function.

## Configuring

* Create [metric.json](docs/metric.md) to define all the metrics you will run.
* Create [hierarchy.json](docs/hierarchy.md) to define the hierarchy of objects
* Upload both files to the S3 Repository bucket

## Create your first metric

TODO

## Software Components

* [Plotly JavaScipt Library](https://plotly.com/javascript/)

## Release

### 2023.02.18

* Added a new `ingestorPolicy` in `dashboard.json` to grant entities access to use the dashboard resources
* Bug fixes in `lambdaReport.py`
   * when `compliance` is a float it would return an `Internal Server Error`
   * total score miscalculated when the weight is 0
* Added the Pseudo paramer `AWS::Partition` to the arn for cloudwatch logs to make the script generic for all AWS partitions
* Fixed a bug in `lambdaAggregate.py` that do not delete metrics that have been disabled
