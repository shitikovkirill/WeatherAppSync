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


