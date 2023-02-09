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

ERROR_MSG = 'Sorry something\'s wrong(RateLimit or server overload or anything), please enter the message above again!'


def make_command_conversation_id(channel_id: str, user_id: str, channel_name: str) -> str:
    conversation_id = None
    if channel_name == 'directmessage':
        conversation_id = f'{user_id}-{channel_id}'
        # TODO:
    # elif channel_type == 'group' or channel_type == 'channel':
    #     if not thread_ts and not conversation_id:
    #         return
    #     conversation_id = f'{user}-{channel}-{thread_ts}'
    return conversation_id


@app.middleware  # or app.use(log_request)
def log_request(logger, body, next):
    logger.debug(body)
    return next()


@app.options('menu_selection')
def show_menu_options(ack):
    options = [{"text": {"type": "plain_text", "text": "Option 1"}, "value": "1-1", }, {"text": {"type": "plain_text", "text": "Option 2"}, "value": "1-2", }, ]
    ack(options=options)


@app.command('/start')
def handle_start_command(ack, say, body, logger):
    ack()
    channel_id = body['channel_id']
    user_id = body['user_id']
    channel_name = body['channel_name']
    say(text=f'Hi! <@{user_id}> :laughing: Happy chatting!', channel_id=channel_id)


@app.command("/terminate")
def handle_terminate_command(ack, body, logger, say):
    ack()
    channel_id = body['channel_id']
    user_id = body['user_id']
    channel_name = body['channel_name']
    conversation_id = make_command_conversation_id(channel_id, user_id, channel_name)
    chatgpt.prune_context(conversation_id)
    say(text='Clear context successfully!', channel_id=channel_id)


@app.command('/retry')
def handle_retry_command(ack, say, body, logger):
    ack()
    channel_id = body['channel_id']
    user_id = body['user_id']
    channel_name = body['channel_name']
    conversation_id = make_command_conversation_id(channel_id, user_id, channel_name)
    try:
        resp = chatgpt.retry(conversation_id)
    except Exception as e:
        print(e)
        resp = ERROR_MSG + "\n\n" + str(e)
    say(text=resp, channel_id=channel_id)


@app.event("message")
def handle_message_events(body, logger, say):
    event = body['event']
    logger.info(body)

    channel_id = event['channel']
    user = event['user']
    text = event['text']
    thread_ts = event.get('thread_ts')
    channel_type = event.get('channel_type')
    channel = event.get('channel')

    conversation_id = None
    if channel_type == 'im':
        conversation_id = f'{user}-{channel}'
    elif channel_type == 'group' or channel_type == 'channel':
        if not thread_ts and not conversation_id:
            return
        conversation_id = f'{user}-{channel}-{thread_ts}'
    try:
        resp = chatgpt.ask(text, conversation_id)
    except Exception as e:
        print(e)
        resp = ERROR_MSG + "\n\n" + str(e)
    say(text=resp, channel_id=channel_id, thread_ts=thread_ts)


@app.event('app_mention')
def mention_events(event, say, logger):
    logger.info(event)

    user_id = event.get('user')
    channel_id = event.get('channel')
    ts = event.get('ts')

    text = f"Welcome to the chat, <@{user_id}>! :tada: Happy chatting!."
    if ts:
        say(text=text, channel=channel_id, thread_ts=ts)
    else:
        say(text=text, channel=channel_id)


if __name__ == "__main__":
    app.start(port=int(os.environ.get("PORT", 4000)))  # POST http://localhost:3000/slack/events
