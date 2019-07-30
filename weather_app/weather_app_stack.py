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
                    getWeather(city: String!): Weather
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
            timeout=core.Duration.seconds(900),
            memory_size=128,
            runtime=Runtime.NODEJS_10_X,
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

        self.add_resolvers(graphql_api, api_schema, data_source=data_source, lambda_source=lambda_source)

    def add_resolvers(self, graphql_api, api_schema, **kwargs):
        get_all_dest_resolver = CfnResolver(
            self,
            'GetAllDestinationsResolver',
            api_id=graphql_api.attr_api_id,
            type_name='Query',
            field_name='getAllDestinations',
            data_source_name=kwargs['data_source'].name,
            request_mapping_template="""{
                "version": "2017-02-28",
                "operation": "Scan",

            }""",
            response_mapping_template="$util.toJson($ctx.result.items)"
        )
        get_all_dest_resolver.add_depends_on(api_schema)

        get_by_state_dest_resolver = CfnResolver(
            self,
            'GetDestinationsByStateResolver',
            api_id=graphql_api.attr_api_id,
            type_name='Query',
            field_name='getDestinationsByState',
            data_source_name=kwargs['data_source'].name,
            request_mapping_template="""{
                "version": "2017-02-28",
                "operation": "Query",
                "query": {
                    "expression": "#state = :state",
                    "expressionNames": {
                        "#state": "state",
                    },
                    "expressionValues": {
                        ":state": {
                            "S": "$util.dynamodb.toDynamoDBJson($ctx.args.state)",
                        }
                    }
                }
            }""",
            response_mapping_template="$util.toJson($ctx.result.items)"
        )
        get_by_state_dest_resolver.add_depends_on(api_schema)

        get_dest_resolver = CfnResolver(
            self,
            'GetDestinationResolver',
            api_id=graphql_api.attr_api_id,
            type_name='Query',
            field_name='getDestination',
            data_source_name=kwargs['data_source'].name,
            request_mapping_template="""{
                "version": "2017-02-28",
                "operation": "GetItem",
                "key": {
                    "id": $util.dynamodb.toDynamoDBJson($ctx.args.id)
                }
            }""",
            response_mapping_template="$util.toJson($ctx.result)"
        )
        get_dest_resolver.add_depends_on(api_schema)

        add_dest_resolver = CfnResolver(
            self,
            'AddDestinationResolver',
            api_id=graphql_api.attr_api_id,
            type_name='Mutation',
            field_name='addDestination',
            data_source_name=kwargs['data_source'].name,
            request_mapping_template="""{
                "version" : "2017-02-28",
                "operation" : "PutItem",
                "key" : {
                    "id": $util.dynamodb.toDynamoDBJson($util.autoId()),
                },
                "attributeValues" : $util.dynamodb.toMapValuesJson($ctx.args)
            }""",
            response_mapping_template="$util.toJson($ctx.result)"
        )
        add_dest_resolver.add_depends_on(api_schema)

        get_weather_resolver = CfnResolver(
            self,
            'GetWeatherResolver',
            api_id=graphql_api.attr_api_id,
            type_name='Query',
            field_name='getWeather',
            data_source_name=kwargs['lambda_source'].name,
            request_mapping_template="""{
                "version" : "2017-02-28",
                "operation": "Invoke",
                "payload": $util.toJson($context.arguments)
            }""",
            response_mapping_template="$util.toJson($context.result)"
        )
        get_weather_resolver.add_depends_on(api_schema)

        weather_resolver = CfnResolver(
            self,
            'ConditionsResolver',
            api_id=graphql_api.attr_api_id,
            type_name='Destination',
            field_name='conditions',
            data_source_name=kwargs['lambda_source'].name,
            request_mapping_template="""{
                "version" : "2017-02-28",
                "operation": "Invoke",
                "payload": {
                    "city": $util.toJson($context.source.city)
                }
            }""",
            response_mapping_template="$util.toJson($context.result)"
        )
        weather_resolver.add_depends_on(api_schema)
