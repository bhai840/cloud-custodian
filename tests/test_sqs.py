# Copyright 2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from .common import BaseTest, functional
from botocore.exceptions import ClientError
import json, time



class TestSqsAction(BaseTest):

    @functional
    def test_sqs_delete(self):
        session_factory = self.replay_flight_data(
            'test_sqs_delete')
        client = session_factory().client('sqs')
        client.create_queue(QueueName='test-sqs')
        queue_url = client.get_queue_url(QueueName='test-sqs')['QueueUrl']

        p = self.load_policy({
            'name': 'sqs-delete',
            'resource': 'sqs',
            'filters': [{'QueueUrl': queue_url}],
            'actions': [
                {'type': 'delete'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertRaises(
            ClientError,
            client.purge_queue, QueueUrl=queue_url)


    @functional
    def test_sqs_set_encryption(self):
        session_factory = self.replay_flight_data(
            'test_sqs_set_encryption')

        client_sqs = session_factory().client('sqs')
        client_sqs.create_queue(QueueName='sqs-test')
        queue_url = client_sqs.get_queue_url(QueueName='sqs-test')['QueueUrl']
        self.addCleanup(client_sqs.delete_queue, QueueUrl=queue_url)

        client_kms = session_factory().client('kms')
        key_id = client_kms.create_key(Description='West SQS encryption key')['KeyMetadata']['KeyId']
        client_kms.create_alias(
            AliasName='alias/new-key-test-sqs',
            TargetKeyId=key_id)
        self.addCleanup(client_kms.disable_key, KeyId=key_id)

        p = self.load_policy({
            'name': 'sqs-delete',
            'resource': 'sqs',
            'filters': [{'QueueUrl': queue_url}],
            'actions': [
                {'type': 'set-encryption',
                 'key': 'new-key-test-sqs'}]},
            session_factory=session_factory)
        resources = p.run()

        check_master_key = client_sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['All'])['Attributes']['KmsMasterKeyId']
        self.assertEqual(check_master_key, 'c4816d44-73c3-4eed-a7cc-d52a74fa3294')


    @functional
    def test_sqs_remove_matched(self):
        session_factory = self.replay_flight_data('test_sqs_remove_matched')
        client = session_factory().client('sqs')
        name = 'test-sqs-remove-matched-1'
        queue_url = client.create_queue(QueueName=name)['QueueUrl']
        self.addCleanup(client.delete_queue, QueueUrl=queue_url)

        client.set_queue_attributes(
            QueueUrl=queue_url,
            Attributes={'Policy':json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "SpecificAllow",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": "arn:aws:iam::123456789012:root"
                        },
                        "Action": [
                            "sqs:Subscribe"
                        ]
                    },
                    {
                        "Sid": "Public",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": [
                            "sqs:GetqueueAttributes"
                        ]
                    }
                ]
            })}
        )

        p = self.load_policy({
            'name': 'sqs-rm-matched',
            'resource': 'sqs',
            'filters': [
                {'QueueUrl': queue_url},
                {'type': 'cross-account',
                 'whitelist': ["123456789012"]}
            ],
            'actions': [
                {'type': 'remove-statements',
                 'statement_ids': 'matched'}]
            },
            session_factory=session_factory)
        resources = p.run()

        self.assertEqual([r['QueueUrl'] for r in resources], [queue_url])

        data = json.loads(client.get_queue_attributes(QueueUrl=resources[0]['QueueUrl'], AttributeNames=['Policy'])['Attributes']['Policy'])
        self.assertEqual(
            [s['Sid'] for s in data.get('Statement', ())],
            ['SpecificAllow'])


    @functional
    def test_sqs_remove_named(self):
        session_factory = self.replay_flight_data('test_sqs_remove_named')
        client = session_factory().client('sqs')
        name = 'test-sqs-remove-named'
        queue_url = client.create_queue(QueueName=name)['QueueUrl']
        self.addCleanup(client.delete_queue, QueueUrl=queue_url)

        client.set_queue_attributes(
            QueueUrl=queue_url,
            Attributes={'Policy':json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "SpecificAllow",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": "arn:aws:iam::644160558196:root"
                        },
                        "Action": ["sqs:Subscribe"]
                    },
                    {
                        "Sid": "RemoveMe",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": ["sqs:GetqueueAttributes"]
                    }
                ]
            })}
        )

        p = self.load_policy({
            'name': 'sqs-rm-named',
            'resource': 'sqs',
            'filters': [{'QueueUrl': queue_url}],
            'actions': [
                {'type': 'remove-statements',
                 'statement_ids': ['RemoveMe']}]
            },
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 1) 

        data = json.loads(client.get_queue_attributes(QueueUrl=resources[0]['QueueUrl'], AttributeNames=['Policy'])['Attributes']['Policy'])
        self.assertTrue('RemoveMe' not in [s['Sid'] for s in data.get('Statement', ())])
       