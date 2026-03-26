import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

load_dotenv()

class SlackClient:
    def __init__(self):
        self.token = os.getenv("SLACK_BOT_TOKEN")
        self.channel_id = os.getenv("SLACK_CHANNEL_ID")
        self.client = WebClient(token=self.token)

    def send_message(self, text, thread_ts=None):
        """Sends a plain text message to the configured channel."""
        try:
            response = self.client.chat_postMessage(
                channel=self.channel_id,
                text=text,
                thread_ts=thread_ts
            )
            return response["ts"]
        except SlackApiError as e:
            print(f"Error sending message: {e}")
            return None

    def send_blocks(self, blocks, text="Notification from Jobify", thread_ts=None):
        """Sends a rich message with blocks (buttons, sections, etc.)."""
        try:
            response = self.client.chat_postMessage(
                channel=self.channel_id,
                blocks=blocks,
                text=text,
                thread_ts=thread_ts
            )
            return response["ts"]
        except SlackApiError as e:
            print(f"Error sending blocks: {e}")
            return None

    def update_message(self, ts, text=None, blocks=None):
        """Updates an existing message."""
        try:
            self.client.chat_update(
                channel=self.channel_id,
                ts=ts,
                text=text,
                blocks=blocks
            )
        except SlackApiError as e:
            print(f"Error updating message: {e}")

slack_client = SlackClient()
