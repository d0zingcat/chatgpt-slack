import logging
import os
from slack_bolt import App
from chatgpt import chatgpt


logging.basicConfig(level=logging.DEBUG)

# SLACK_SIGNING_SECRET = os.environ.get('SLACK_SIGNING_SECRET')
# SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')

app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)

# Add functionality here


@app.options('menu_selection')
def show_menu_options(ack):
    options = [{"text": {"type": "plain_text", "text": "Option 1"}, "value": "1-1", }, {"text": {"type": "plain_text", "text": "Option 2"}, "value": "1-2", }, ]
    ack(options=options)


@app.command("/start")
def handle_some_command(ack, body, logger):
    ack()
    logger.info(body)


@app.event("message")
def handle_message_events(body, logger, say):
    event = body['event']
    logger.info(body)

    channel_id = event['channel']
    user = event['user']
    text = event['text']
    thread_ts = event.get('thread_ts')
    if not thread_ts:
        return
    resp = chatgpt.ask(text, f'{user}-{thread_ts}')
    # say(
    #     blocks=[
    #         {
    #             "type": "section",
    #             "text": {"type": "mrkdwn", "text": f"Hey there <@{user}>!"},
    #             "accessory": {
    #                 "type": "button",
    #                 "text": {"type": "plain_text", "text": "Click Me"},
    #                 "action_id": "button_click",
    #             },
    #         }
    #     ],
    #     text=f"Hey there <@{user}>!",
    #     thread_ts=thread_ts
    #     # channel_id=channel_id
    # )
    say(text=resp, channel_id=channel_id, thread_ts=thread_ts)


@app.event('app_mention')
def mention_events(event, say, logger):
    logger.info(event)

    user_id = event['user']
    channel_id = event['channel']
    ts = event['ts']

    text = f"Welcome to the chat, <@{user_id}>! :tada: Happy chatting!."
    say(text=text, channel=channel_id, thread_ts=ts)


if __name__ == "__main__":
    app.start(port=int(os.environ.get("PORT", 4000)))  # POST http://localhost:3000/slack/events
