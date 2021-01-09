import pytest
import boto3
import time
from moto import mock_dynamodb2, mock_sqs
from get_waivers import *
import os
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'


@pytest.fixture
def setup_sqs():
    with mock_sqs():
        sqs_client = boto3.client('sqs')
        sqs_client.create_queue(QueueName='BDFLMessageQueue')
        yield sqs_client

@pytest.fixture
def setup_dynamodb():
    with mock_dynamodb2():
        dynamodb_client = boto3.client('dynamodb')
        dynamodb_client.create_table(
            TableName='waivers',
            AttributeDefinitions=[
                {
                    'AttributeName': 'key',
                    'AttributeType': 'S'
                },
            ],
            KeySchema=[
                {
                    'AttributeName': 'key',
                    'KeyType': 'HASH'
                }
            ]
        )
        dynamodb_client.create_table(TableName='players',
            AttributeDefinitions=[
                {
                    'AttributeName': 'id',
                    'AttributeType': 'S'
                }
            ],
            KeySchema=[
                {
                    'AttributeName': 'id',
                    'KeyType': 'HASH'
                }
            ]
        )
        dynamodb_client.create_table(TableName='franchises',
            AttributeDefinitions=[
                {
                    'AttributeName': 'id',
                    'AttributeType': 'S'
                }
            ],
            KeySchema=[
                {
                    'AttributeName': 'id',
                    'KeyType': 'HASH'
                }
            ]
        )

        dynamodb_resource = boto3.resource('dynamodb')

        waivers_table = dynamodb_resource.Table('waivers')
        waivers_table.update_item(
            Key={
                'key': '1608890400-Josh-Oliver-JAC-TE'
            },
            ExpressionAttributeNames={
                '#FID': 'franchise_id',
                '#RT': 'raw_transaction',
                '#FT': 'formatted_transaction',
                '#FN': 'franchise_name',
                '#T': 'type',
                '#TS': 'timestamp'
            },
            ExpressionAttributeValues={
                ':fid': '0003',
                ':rt': '14209,|1.00|', 
                ':ft': ["$1.00", "Josh Oliver, JAC TE", None],
                ':fn': 'Jeff Janis Fan Club', 
                ':t': 'BBID_WAIVER',
                ':ts': '1608890400',
            },
            UpdateExpression='SET #FID=:fid, #RT=:rt, #FT=:ft, #FN=:fn, #T=:t, #TS=:ts'
        )

        players_table = dynamodb_resource.Table('players')
        players_table.update_item(
            Key={
                'id': '14209'
            },
            ExpressionAttributeNames={
                '#N': 'name',
                '#P': 'position',
                '#T': 'team'
            },
            ExpressionAttributeValues={
                ':n': 'Josh Oliver', 
                ':p': 'TE',
                ':t': 'JAC'
            },
            UpdateExpression='SET #N=:n, #P=:p, #T=:t'
        )
        players_table.update_item(
            Key={
                'id': '11247'
            },
            ExpressionAttributeNames={
                '#N': 'name',
                '#P': 'position',
                '#T': 'team'
            },
            ExpressionAttributeValues={
                ':n': 'Zach Ertz', 
                ':p': 'TE',
                ':t': 'PHI'
            },
            UpdateExpression='SET #N=:n, #P=:p, #T=:t'
        )

        franchise_table = dynamodb_resource.Table('franchises')
        franchise_table.update_item(
            Key={
                'id': '0003'
            },
            ExpressionAttributeNames={
                '#N': 'name',
                '#D': 'division_id',
                '#B': 'blind_bid_dollars'
            },
            ExpressionAttributeValues={
                ':n': 'Jeff Janis Fan Club', 
                ':d': '01',
                ':b': '12.00', 
            },
            UpdateExpression='SET #N=:n, #D=:d, #B=:b'
        )
        yield dynamodb_client, dynamodb_resource

def test_send_sqs_message_correctly(setup_sqs):
    message_to_send = 'test message'
    
    sent_message = send_sqs_message('BDFLMessageQueue', message_to_send)

    assert sent_message['ResponseMetadata']['HTTPStatusCode'] == 200

def test_send_sqs_messages_correctly(setup_sqs):
    messages_to_send = ['test message1', 'test message2']
    
    send_sqs_messages(messages_to_send)

    # if send_sqs_messages raises exception, test will fail

def test_format_add_drop_string_player_dropped():
    bid_amt = 130
    player_added_name = 'Patrick Mahomes'
    player_dropped_name = 'Philip Rivers'
    transaction = [bid_amt, player_added_name, player_dropped_name]

    expected_string = f'won {player_added_name} with a {bid_amt} bid and dropped {player_dropped_name}'
    returned_string = format_add_drop_string(transaction)

    assert returned_string == expected_string

def test_format_add_drop_string_no_player_dropped():
    bid_amt = 130
    player_added_name = 'Patrick Mahomes'
    player_dropped_name = None
    transaction = [bid_amt, player_added_name, player_dropped_name]

    expected_string = f'won {player_added_name} with a {bid_amt} bid'
    returned_string = format_add_drop_string(transaction)

    assert returned_string == expected_string

def test_format_waiver_message_correctly():
    franchise_name = 'Kansas City Chiefs'
    bid_amt = 130
    player_added_name = 'Patrick Mahomes'
    player_dropped_name = 'Philip Rivers'
    transaction = [bid_amt, player_added_name, player_dropped_name]

    expected_string = f'{franchise_name} won {player_added_name} with a {bid_amt} bid and dropped {player_dropped_name}\n'
    returned_string = format_waiver_message(franchise_name, transaction)

    assert returned_string == expected_string

def test_create_waiver_object(setup_dynamodb):
    test_waiver = {
        "timestamp": "1608890400",
        "franchise": "0003",
        "transaction": "14209,|1.00|",
        "type": "BBID_WAIVER"
    }

    expected_waiver_obj = {
        'key': '1608890400-Josh-Oliver-JAC-TE',
        'timestamp': '1608890400',
        'franchise_id': '0003',
        'raw_transaction': '14209,|1.00|',
        'formatted_transaction': ['$1.00', 'Josh Oliver, JAC TE', None],
        'franchise_name':  'Jeff Janis Fan Club',
        'type': 'BBID_WAIVER'
    }
    returned_waiver_obj = create_waiver_object(test_waiver)

    assert returned_waiver_obj == expected_waiver_obj

def test_store_waivers_if_not_exist_in_db(setup_dynamodb):
    waivers = [{
        "timestamp": str(int(time.time())),
        "franchise": "0003",
        "transaction": "11247,|69.00|",
        "type": "BBID_WAIVER"
    }]

    expected_message = ['✅WAIVER CLAIMS COMPLETED✅\n\nJeff Janis Fan Club won Zach Ertz, PHI TE with a $69.00 bid\n']
    returned_message = store_waivers_if_not_exist(waivers)

    assert expected_message == returned_message

def test_store_waivers_if_exist_in_db(setup_dynamodb):
    waivers = [{
        "timestamp": '1608890400',
        "franchise": "0003",
        "transaction": "14209,|10.00|",
        "type": "BBID_WAIVER"
    }]

    expected_message = []
    returned_message = store_waivers_if_not_exist(waivers)

    assert expected_message == returned_message

def test_store_waivers_drop_player(setup_dynamodb):
    waivers = [{
        "timestamp": str(int(time.time())),
        "franchise": "0003",
        "transaction": "14209,|10.00|11247",
        "type": "BBID_WAIVER"
    }]

    expected_message = ['✅WAIVER CLAIMS COMPLETED✅\n\nJeff Janis Fan Club won Josh Oliver, JAC TE with a $10.00 bid and dropped Zach Ertz, PHI TE\n']
    returned_message = store_waivers_if_not_exist(waivers)

    assert expected_message == returned_message

