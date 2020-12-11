import json
import os
import boto3
from pymfl.mfl import MFL


def handler(event, context):
    mfl = MFL(
        os.getenv('MFL_USERNAME'),
        os.getenv('MFL_PASSWORD'),
        os.getenv('MFL_LEAGUEID'),
        os.getenv('MFL_API_YEAR')
        )
    
    players = mfl.players()

    store_players_in_dynamodb(players)

    body = {
        'trades': players
    }

    response = {
        "statusCode": 201,
        "body": body
    }

    return response

def store_players_in_dynamodb(players):
    dynamodb = boto3.resource('dynamodb')

    players_table = dynamodb.Table('players')

    for player in players:
        players_table.update_item(
            Key={
                'id': player['id']
            },
            ExpressionAttributeNames={
                '#N': 'name',
                '#P': 'position',
                '#T': 'team'
            },
            ExpressionAttributeValues={
                ':n': format_name(player['name']) if 'name' in player.keys() else 'N/A', 
                ':p': player['position'] if 'position' in player.keys() else 'N/A',
                ':t': player['team'] if 'team' in player.keys() else 'N/A'
            },
            UpdateExpression='SET #N=:n, #P=:p, #T=:t'
        )

def format_name(player_name):
    
    name_list = player_name.split(',')
    formatted_name = name_list[1].strip() + ' ' + name_list[0].strip()

    return formatted_name
