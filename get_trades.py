import json
import os
import boto3
from pymfl.mfl import MFL


def handler(event, context):
    mfl = MFL(
        os.getenv('MFL_USERNAME'),
        os.getenv('MFL_PASSWORD'),
        os.getenv('MFL_LEAGUEID')
        )
    
    trades = mfl.trades()

    body = {
        'trades': trades
    }

    response = {
        "statusCode": 200,
        "body": body
    }

    return response

    # Use this code if you don't use the http event with the LAMBDA-PROXY
    # integration
    """
    return {
        "message": "Go Serverless v1.0! Your function executed successfully!",
        "event": event
    }
    """
