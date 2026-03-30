import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import run_phase3
from tools.slack_client import slack_client

class TestSlackNotification(unittest.TestCase):
    @patch('run_phase3.check_prerequisites')
    @patch('tools.ingest_companies.ingest')
    @patch('tools.slack_client.slack_client.send_message')
    @patch('tools.slack_client.slack_client.send_blocks')
    def test_no_companies_notification(self, mock_send_blocks, mock_send_message, mock_ingest, mock_prereq):
        # Setup mocks
        mock_prereq.return_value = None
        mock_ingest.return_value = []
        
        # Test parameters
        sheet_url = "https://docs.google.com/spreadsheets/d/test"
        thread_ts = "1234.5678"
        channel_id = "C12345"
        
        # Run logic
        run_phase3.run_phase3_logic(sheet_url, thread_ts=thread_ts, channel_id=channel_id)
        
        # Verify notification
        # Calls to slack_client.send_message
        msg_calls = [call.args[0] for call in mock_send_message.call_args_list]
        
        self.assertIn("No matching companies found in this sheet. Try a new export.", msg_calls)
        
        # Also check that it was sent to the correct thread/channel
        mock_send_message.assert_any_call(
            "No matching companies found in this sheet. Try a new export.",
            thread_ts=thread_ts,
            channel_id=channel_id
        )

if __name__ == '__main__':
    unittest.main()
