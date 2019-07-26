import os


def get(event, context):

    return {
        "description": os.environ['APPID'],
        "current": "String",
        "maxTemp": "String",
        "minTemp": "String"
    }