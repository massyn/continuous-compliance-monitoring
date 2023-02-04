# continuous-compliance-monitoring
Continuous Compliance Monitoring

## Getting started

### Requirements

* You need an AWS account
* You need to have an AWS Cognito user pool configured.  You will need to know the `cognito_domain`, `client_id` and `client_secret`

### Installation
* Download [lambdaUpdate.py](https://github.com/massyn/cloudformation/blob/main/lambdaUpdate.py) and save it somewhere
* Edit `refresh.sh` and replace the path of `lambdaUpdate.py` with the path of the file you just downloaded
* Edit [config.json](docs/config.md) and update the cognito variables
   * You will need to leave the `redirect_url` empty until the end.
* Create [metric.json](docs/metric.md) to define all the metrics you will run.
* Create [hierarchy.json](docs/hierarchy.md) to define the hierarchy of objects
* Log onto the AWS account where the solution will be deployed (you may want to set the `AWS_REGION` variable to ensure the `refresh.sh` script can get to AWS...)
* Run `refresh.sh`
* On completion, you will receive the Lambda function URL.
* When you get the Lambda function URL, update the `config.json` file's `redirect_url` parameter with that URL.
* You will need to also update Cognito with the updated URL.
* Run `refresh.sh` again to update the `config.json` file in the Lambda function.

## Create your first metric

TODO

## Software Components

* [Plotly JavaScipt Library](https://plotly.com/javascript/)



