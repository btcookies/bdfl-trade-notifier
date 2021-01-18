import json
import os
import boto3
from pymfl.mfl import MFL


def handler(event, context):
    mfl = MFL(
        os.getenv("MFL_USERNAME"),
        os.getenv("MFL_PASSWORD"),
        os.getenv("MFL_LEAGUEID"),
        os.getenv("MFL_API_YEAR"),
    )

    franchises = mfl.franchises()

    store_franchises_in_dynamodb(franchises)

    body = {"franchises": franchises.get_franchises()}

    response = {"statusCode": 201, "body": body}

    return response


def store_franchises_in_dynamodb(franchises):
    dynamodb = boto3.resource("dynamodb")

    franchise_table = dynamodb.Table("franchises")

    franchise_dict = franchises.get_franchises()

    for fid in franchise_dict.keys():
        franchise = franchise_dict[fid]
        franchise_table.update_item(
            Key={"id": fid},
            ExpressionAttributeNames={
                "#N": "name",
                "#D": "division_id",
                "#B": "blind_bid_dollars",
            },
            ExpressionAttributeValues={
                ":n": franchise.name,
                ":d": franchise.division_id,
                ":b": franchise.blind_bid_dollars,
            },
            UpdateExpression="SET #N=:n, #D=:d, #B=:b",
        )
