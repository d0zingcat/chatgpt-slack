from enum import Enum
from typing import List
import json
import logging

import redis.asyncio as redis
import openai
from slack_bolt.async_app import AsyncApp

import config


class Models(Enum):
    TURBO = 'gpt-3.5-turbo'


class ChatGPT:
    def __init__(self, api_key: str):
        self._api_key = api_key
        self.temperature = 0
        openai.api_key = self._api_key

    def chat_completion(self, messages: List[any], temperature: float = 0, max_tokens: int = 0):
        temperature = temperature or self.temperature
        completion_resp = openai.ChatCompletion.create(model=Models.TURBO.value, messages=messages, temperature=temperature)
        usage = completion_resp['usage']
        logging.debug(usage)
        return completion_resp['choices'][0].message


gpt = ChatGPT(config.OPENAI_API_KEY)


class ConversationManager:
    r = redis.from_url(config.REDIS_URL, decode_responses=True)

    CONVERSATION_NAME_KEY = 'conversation_name'
    CONVERSATION_CONTENT_KEY = 'conversation_content'
    CONVERSATION_META_KEY = 'conversation_meta'

    _storage = dict()

    def _marshal(self, data: any): return json.dumps(data)

    def _unmarshal(self, data: bytes):
        if not data:
            return None
        return json.loads(data)

    def __init__(self):
        return

    async def get_current_conversation_meta(self, user_id: str):
        return await self.r.hget(self.CONVERSATION_META_KEY, user_id) or {}

    async def get_conversations_by_user(self, user_id: str):
        return self._unmarshal(await self.r.hgetall(f'{self.CONVERSATION_NAME_KEY}:{user_id}'))

    async def get_conversation(self, user_id: str, conversation_id: str = None):
        conversation_id = conversation_id or '0'
        r = self._unmarshal(await self.r.hget(f'{self.CONVERSATION_CONTENT_KEY}:{user_id}', conversation_id))
        if r:
            return r
        default_conversation = [{'role': 'system', 'content': 'You are a helpful assistant.'},]
        await self.r.hset(f'{self.CONVERSATION_CONTENT_KEY}:{user_id}', conversation_id, self._marshal(default_conversation))
        return default_conversation

    async def set_conversation(self, user_id: str, conversation_id: str = None, messages: List[any] = None):
        conversation_id = conversation_id or '0'
        await self.r.hset(f'{self.CONVERSATION_CONTENT_KEY}:{user_id}', conversation_id, self._marshal(messages))
        return True

    async def clear_conversation(self, user_id: str, conversation_id: str = None):
        conversation_id = conversation_id or '0'
        await self.r.hdel(f'{self.CONVERSATION_CONTENT_KEY}:{user_id}', conversation_id)


manager = ConversationManager()


def init_async_app():
    return AsyncApp(
        token=config.SLACK_BOT_TOKEN,
        signing_secret=config.SLACK_SIGNING_SECRET,
    )


app = init_async_app()


@app.middleware  # or app.use(log_request)
async def log_request(logger, body, next):
    logger.debug(body)
    await next()


@app.command('/terminate')
async def terminate_command(ack, body):
    user_id = body["user_id"]
    conversation_id = body.get('text')
    await manager.clear_conversation(user_id, conversation_id)
    await ack(text='Conversation terminated.')


@app.command("/ls")
async def hello_command(ack, body):
    user_id = body["user_id"]
    # await ack(f"Hi <@{user_id}>! {body['text']}")
    conversations = await manager.get_conversations_by_user(user_id)
    await ack(
        blocks=[
            {
                "type": "section",
                "text": {
                        "type": "mrkdwn",
                        "text": "*Select a conversation:*"
                }
            },
        ] + [
            {
                "type": "section",
                "text": {
                        "type": "mrkdwn",
                        "text": f"{value}"
                },
                "accessory": {
                    "type": "button",
                    "text": {
                            "type": "plain_text",
                        "emoji": True,
                        "text": "Choose"
                    },
                    "value": "key"
                }
            }
            for key, value in conversations.items()
        ], text="Hi there!"
    )


@ app.event("message")
async def handle_message_events(body, say):
    event = body['event']

    user_id = event['user']
    text = event['text']
    channel_id = event['channel']
    thread_ts = event.get('thread_ts')
    channel_type = event.get('channel_type')
    channel = event.get('channel')

    conversation_id = (await manager.get_current_conversation_meta(user_id)).get('conversation_id')
    c = await manager.get_conversation(user_id, conversation_id)
    c.append({'role': 'user', 'content': text})
    message = gpt.chat_completion(c)
    c.append({'role': message.role, 'content': message.content})
    await manager.set_conversation(user_id, conversation_id, messages=c)
    await say(text=message.content)


# @app.event("app_mention")
# async def event_test(event, say):
#     await say(f"Hi there, <@{event['user']}>!")
