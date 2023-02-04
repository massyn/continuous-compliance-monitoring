# config.json

The `config.json` file is responsible for the core configuration of the solution.  The main usage of the script is to define the [AWS Cognito](https://aws.amazon.com/awscognito) parameters necessary for sign on.

## Example

```json
{
    "cognito_domain" : "https://xxxxx.auth.region.amazoncognito.com",
    "redirect_uri"   : "https://xxxxx.lambda-url.region.on.aws/",
    "client_id"      : "xxxxx",
    "client_secret"  : "xxxxx"
}
```