import unittest
from unittest.mock import Mock

import httpx

from .probe import ENDPOINT, FEATURE, plan, request_document


class VisionProbeTests(unittest.TestCase):
    def test_three_samples_are_seven_units(self):
        result = plan()
        self.assertEqual(result['units'], 7)
        self.assertEqual(result['mode'], 'LOCAL_PLAN_NO_API')

    def test_duplicate_case_rejected_before_network(self):
        with self.assertRaises(ValueError):
            plan(('r03', 'r03'))

    def test_only_page_image_and_one_feature_are_sent(self):
        client = Mock()
        client.post.return_value = httpx.Response(200, json={'responses': [{'fullTextAnnotation': {'text': 'SYNTHETIC OCR'}}]})
        result, _ = request_document(client, 'hidden-test-key', [b'png-test'])
        args, kwargs = client.post.call_args
        self.assertEqual(args[0], ENDPOINT)
        self.assertNotIn('hidden-test-key', args[0])
        self.assertEqual(kwargs['headers'], {'X-Goog-Api-Key': 'hidden-test-key'})
        self.assertEqual(set(kwargs['json']['requests'][0]), {'image', 'features'})
        self.assertEqual(kwargs['json']['requests'][0]['features'], [{'type': FEATURE}])
        self.assertEqual(result['execution'], 'COMPLETED')
        self.assertNotIn('hidden-test-key', str(result))

    def test_billing_error_is_terminal_and_secret_message_not_returned(self):
        client = Mock()
        client.post.return_value = httpx.Response(403, json={'error': {'status': 'PERMISSION_DENIED',
            'message': 'secret-from-server', 'details': [{'reason': 'BILLING_DISABLED'}]}})
        result, _ = request_document(client, 'hidden-key', [b'png'])
        self.assertEqual(result['execution'], 'API_ERROR')
        self.assertEqual(result['error_reasons'], ['BILLING_DISABLED'])
        self.assertNotIn('secret-from-server', str(result))
        self.assertEqual(client.post.call_count, 1)

    def test_missing_page_response_cannot_be_complete(self):
        client = Mock()
        client.post.return_value = httpx.Response(200, json={'responses': [{'fullTextAnnotation': {'text': 'Page one'}}]})
        result, _ = request_document(client, 'hidden-key', [b'one', b'two'])
        self.assertEqual(result['execution'], 'PARTIAL_OR_EMPTY_OCR')

    def test_timeout_is_not_retried(self):
        client = Mock()
        client.post.side_effect = httpx.ReadTimeout('message with private credential')
        result, _ = request_document(client, 'hidden-key', [b'one'])
        self.assertEqual(result['execution'], 'TRANSPORT_OR_JSON_ERROR')
        self.assertEqual(result['error_type'], 'ReadTimeout')
        self.assertNotIn('private credential', str(result))
        self.assertEqual(client.post.call_count, 1)


if __name__ == '__main__':
    unittest.main()
