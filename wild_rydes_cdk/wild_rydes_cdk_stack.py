from aws_cdk import (
    core,
    aws_codecommit as codecommit,
    aws_amplify as amplify,
    aws_iam as iam,
    aws_dynamodb as ddb,
    aws_lambda as _lambda,
    aws_apigateway as apigw
)

class WildRydesCdkStack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create repo for Amplify static site
        amplify_repo = codecommit.Repository(
            self, 'amplify-wild-rydes-repo',
            repository_name='amplify-wild-rydes',
            description='Repo for the Wild Rydes static site for Amplify'
        )

        # Create repo for holding the code for this project
        app_repo = codecommit.Repository(
            self, 'app-serverless-workshop-repo',
            repository_name='app-wild-rydes-serverless-workshop',
            description='Repo for project from webapp.serverlessworkshops.io/staticwebhosting/overview/'
        )

        # IAM Role & Policy for Amplify
        amplify_role = iam.Role(
            self, 'amplify-wild-rydes-role',
            role_name='amplify-wild-rydes-role',
            assumed_by=iam.ServicePrincipal('amplify.amazonaws.com')
        )        

        # Amplify
        amplify_static_site = amplify.App(
            self,'amplify-wild-rydes-site',
            source_code_provider=amplify.CodeCommitSourceCodeProvider(repository=amplify_repo),
            description='Wild Rydes Amplify Static Site',
            role=amplify_role,
            app_name='wild-rydes-site'
        )

        master = amplify_static_site.add_branch("master")

        # Policy is fairly open
        # Ran into issues when I deployed the cognito user pools through the amplify cli
        # It creates a new CloudFormation stack and deploys several resources
        amplify_policy = iam.Policy(
            self, 'amplify-wild-rydes-policy',
            roles=[amplify_role],
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=['codecommit:GitPull'],
                    resources=[amplify_repo.repository_arn]
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=['amplify:GetApp', 'amplify:CreateBackendEnvironment', 'cloudformation:*', 'cognito:*', 'lambda:*', 's3:*', 'iam:*'],
                    resources=['*']
                )
            ]
        )

        # DynamoDB
        # removal_policy=core.RemovalPolicy.DESTROY is to ensure it is deleted since this is only a lab
        # table_name is required to be Rides, its configured in the nodejs code that the lambda function runs
        rides_table = ddb.Table(
            self, 'Table',
            table_name='Rides',
            partition_key=ddb.Attribute(name='RideId', type=ddb.AttributeType.STRING),
            removal_policy=core.RemovalPolicy.DESTROY
        )

        # Lambda Functions
        request_unicorn_role = iam.Role(
            self, 'RequestUnicornRole',
            role_name='wild-rydes-lambda-role',
            assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole')]
        )

        # Grant write access to the lambda role
        rides_table.grant_write_data(request_unicorn_role)

        request_unicorn = _lambda.Function(
            self, 'request-unicorn',
            handler='requestUnicorn.handler',
            runtime=_lambda.Runtime.NODEJS_12_X,
            code=_lambda.AssetCode('request_unicorn'),
            role=request_unicorn_role,
            function_name='request-unicorn-wild-rydes'
        )

        # Rest API
        ride_api_gw = apigw.RestApi(
            self, 'wild-rydes-apigw',
            rest_api_name='WildRydes',
            endpoint_types=[apigw.EndpointType.REGIONAL]            
        )

        # APIGW Lambda Integration
        # proxy enabled for the workshop
        ride_api_gw_lambda_integration = apigw.LambdaIntegration(request_unicorn, proxy=True,
            integration_responses=[{
                'statusCode': '200',
                'responseParameters': {'method.response.header.Access-Control-Allow-Origin': "'*'",}
            }]    
        )

        post_ride_resource = ride_api_gw.root.add_resource('ride')
        post_ride_resource_method = post_ride_resource.add_method('POST', ride_api_gw_lambda_integration,
            method_responses=[{
                    'statusCode': '200',
                    'responseParameters': {'method.response.header.Access-Control-Allow-Origin': True,}
            }]
        )

        # This needs to be created after the Amplify site unless you create the cognito userpool in the cdk
        # I went through the Amplify CLI to create the backend
        ride_api_gw_authorizer = apigw.CfnAuthorizer(
            self, 'wild-rydes-apigw-authorizer',
            rest_api_id=ride_api_gw.rest_api_id,
            name='wild-rydes-apigw-authorizer',
            type='COGNITO_USER_POOLS',
            identity_source='method.request.header.name.Authorization',
            identity_validation_expression="Bearer (.*)",
            provider_arns=['arn:aws:cognito-idp:us-east-1:<ACCOUNT_ID>:userpool/<USER_POOL_ID>']
        )

        # https://github.com/aws/aws-cdk/issues/5618
        post_ride_resource_fix = post_ride_resource_method.node.find_child('Resource')
        post_ride_resource_fix.add_property_override('AuthorizationType', 'COGNITO_USER_POOLS')
        post_ride_resource_fix.add_property_override('AuthorizerId', {"Ref": ride_api_gw_authorizer.logical_id})

        # Enable CORS for the workshop
        post_ride_resource.add_method('OPTIONS', apigw.MockIntegration(
            integration_responses=[{
                'statusCode': '200',
                'responseParameters': {
                    'method.response.header.Access-Control-Allow-Headers': "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
                    'method.response.header.Access-Control-Allow-Origin': "'*'",
                    'method.response.header.Access-Control-Allow-Methods': "'POST,OPTIONS'"
                }
            }],
            passthrough_behavior=apigw.PassthroughBehavior.WHEN_NO_MATCH,
            request_templates={"application/json":"{\"statusCode\":200}"}
            ),
            method_responses=[{
            'statusCode': '200',
            'responseParameters': {
                'method.response.header.Access-Control-Allow-Headers': True,
                'method.response.header.Access-Control-Allow-Methods': True,
                'method.response.header.Access-Control-Allow-Origin': True,
                }
            }]
        )

        # Outputs
        amplify_repo_url = core.CfnOutput(
            self, 'amplify-repo-url',
            value=amplify_repo.repository_clone_url_http
        )

        app_repo_url = core.CfnOutput(
            self, 'app-repo-url',
            value=app_repo.repository_clone_url_http
        )

        amplify_default_domain = core.CfnOutput(
            self, 'amplify-default-domain',
            value=amplify_static_site.default_domain
        )

        request_unicorn_apigw = core.CfnOutput(
            self, 'request-unicorn-apigw',
            value=request_unicorn_apigw.url
        )
