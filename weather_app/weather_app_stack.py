import os
from aws_cdk import core
from aws_cdk.aws_appsync import (
    CfnGraphQLApi, CfnApiKey, CfnGraphQLSchema, CfnDataSource, CfnResolver
)
from aws_cdk.aws_dynamodb import (
    Table, Attribute, AttributeType, StreamViewType, BillingMode,
)
from aws_cdk.aws_iam import (
    Role, ServicePrincipal, ManagedPolicy
)
from aws_cdk.aws_lambda import (
    Function, Code, Runtime
)
from dotenv import load_dotenv
dotenv_path = os.path.join(os.getcwd(), '.envvar')
load_dotenv(dotenv_path)


class WeatherAppStack(core.Stack):

    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        graphql_api = CfnGraphQLApi(
            self,
            'WeatherApi',
            name='weather-api',
            authentication_type='API_KEY'
        )

        CfnApiKey(
            self,
            'WeatherApiKey',
            api_id=graphql_api.attr_api_id
        )

        api_schema = CfnGraphQLSchema(
            self,
            'WeatherSchema',
            api_id=graphql_api.attr_api_id,
            definition="""
                type Destination {
                    id: ID!
                    description: String!
                    state: String!
                    city: String!
                    zip: String!
                    conditions: Weather!
                }
                        
                type Mutation {
                    addDestination(
                        id: ID,
                        description: String!,
                        state: String!,
                        city: String!,
                        zip: String!
                    ): Destination!
                }
                        
                type Query {
                    getWeather: Weather
                    # Get a single value of type 'Post' by primary key.
                    getDestination(id: ID!, zip: String): Destination
                    getAllDestinations: [Destination]
                    getDestinationsByState(state: String!): [Destination]
                }
                        
                type Subscription {
                    newDestination: Destination
                        @aws_subscribe(mutations: ["addDestination"])
                }
                        
                type Weather {
                    description: String
                    current: String
                    maxTemp: String
                    minTemp: String
                }
                        
                schema {
                    query: Query
                    mutation: Mutation
                    subscription: Subscription
                }
            """
        )

        table_name = 'destinations'

        table = Table(
            self,
            'DestinationsTable',
            table_name=table_name,
            partition_key=Attribute(
                name="id",
                type=AttributeType.STRING,
            ),
            billing_mode=BillingMode.PAY_PER_REQUEST,
            stream=StreamViewType.NEW_IMAGE
        )

        table_role = Role(
            self,
            'DestinationsDynamoDBRole',
            assumed_by=ServicePrincipal('appsync.amazonaws.com')
        )

        table_role.add_managed_policy(
            ManagedPolicy.from_aws_managed_policy_name('AmazonDynamoDBFullAccess')
        )

        data_source = CfnDataSource(
            self,
            'DestinationsDataSource',
            api_id=graphql_api.attr_api_id,
            name='DestinationsDynamoDataSource',
            type='AMAZON_DYNAMODB',
            dynamo_db_config=CfnDataSource.DynamoDBConfigProperty(
                table_name=table.table_name,
                aws_region=self.region
            ),
            service_role_arn=table_role.role_arn
        )

        lambdaFn = Function(
            self,
            "GetWeather",
            code=Code.asset(os.getcwd() + "/lambdas/weather/"),
            handler="weather.get",
            timeout=core.Duration.seconds(300),
            runtime=Runtime.PYTHON_3_7,
            environment={
                'APPID': os.getenv('APPID')
            }
        )

        lambda_role = Role(
            self,
            'WeatherLambdaRole',
            assumed_by=ServicePrincipal('appsync.amazonaws.com')
        )

        lambda_role.add_managed_policy(
            ManagedPolicy.from_aws_managed_policy_name('AWSLambdaFullAccess')
        )

        lambda_source = CfnDataSource(
            self,
            'WeatherDataSource',
            api_id=graphql_api.attr_api_id,
            name='WeatherCondition',
            type='AWS_LAMBDA',
            lambda_config=CfnDataSource.LambdaConfigProperty(
                lambda_function_arn=lambdaFn.function_arn
            ),
            service_role_arn=lambda_role.role_arn
        )

        delete_resolver = CfnResolver(
            self,
            'GetWeatherResolver',
            api_id=graphql_api.attr_api_id,
            type_name='Query',
            field_name='getWeather',
            data_source_name=lambda_source.name,
            request_mapping_template="""{
                "version" : "2017-02-28",
                "operation": "Invoke",
                "payload": $util.toJson($context.arguments)
            }""",
            response_mapping_template="$util.toJson($context.result)"
        )
        delete_resolver.add_depends_on(api_schema)

