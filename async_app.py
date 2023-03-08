from enum import Enum
from typing import List
import json
import logging
import re

from slack_bolt.async_app import AsyncApp
from slack_bolt.middleware.message_listener_matches.async_message_listener_matches import AsyncMessageListenerMatches
import redis.asyncio as redis
import openai

import config


class Models(Enum):
    TURBO = 'gpt-3.5-turbo'


class ChatGPT:
    def __init__(self, api_key: str):
        self._api_key = api_key
        self.temperature = 0
        self.max_tokens = 4096
        openai.api_key = self._api_key

    async def chat_completion(self, messages: List[any], temperature: float = 0, max_tokens: int = 0):
        temperature = temperature or self.temperature
        completion_resp = openai.ChatCompletion.create(
            model=Models.TURBO.value,
            messages=messages,
            temperature=temperature,
        )
        usage = completion_resp['usage']
        logging.debug(usage)
        return completion_resp['choices'][0].message

    async def chat_completion_stream(self, messages: List[any], temperature: float = 0, max_tokens: int = 0):
        temperature = temperature or self.temperature
        max_tokens = max_tokens or self.max_tokens
        events = await openai.ChatCompletion.acreate(
            model=Models.TURBO.value,
            messages=messages,
            temperature=temperature,
            stream=True
        )
        for event in events:
            yield event['choices'][0].message


gpt = ChatGPT(config.OPENAI_API_KEY)


class ConversationManager:
    r = redis.from_url(config.REDIS_URL, decode_responses=True)

    DEFAULT_TTL = 60 * 60 * 24 * 30  # 30 days
    MAX_CONVERSATIONS = 10

    CONVERSATION_ID_KEY = 'conversation_id'
    CONVERSATION_CONTENT_KEY = 'conversation_content'
    CONVERSATION_DICT_KEY = 'conversation_dict'
    CONVERSATION_CURRENT_KEY = 'conversation_current'

    DEFAULT_CONVERSATION = [{'role': 'system', 'content': 'You are a helpful assistant.'}, ]
    _storage = dict()

    def _marshal(self, data: any):
        return json.dumps(data)

    def _unmarshal(self, data: bytes):
        if not data:
            return None
        return json.loads(data)

    async def get_current_conversation_id(self, user_id: str):
        return await self.r.get(f'{self.CONVERSATION_CURRENT_KEY}:{user_id}') or '0'

    async def set_current_conversation_id(self, user_id: str, conversation_id: str | int):
        await self.r.set(f'{self.CONVERSATION_CURRENT_KEY}:{user_id}', conversation_id)
        return True

    async def flush_conversation(self, user_id: str):
        await self.r.delete(f'{self.CONVERSATION_ID_KEY}:{user_id}')
        await self.r.delete(f'{self.CONVERSATION_DICT_KEY}:{user_id}')
        await self.r.delete(f'{self.CONVERSATION_CONTENT_KEY}:{user_id}')
        await self.r.delete(f'{self.CONVERSATION_CURRENT_KEY}:{user_id}')

    async def get_conversation_dict(self, user_id: str):
        conversation_names = await self.r.hgetall(f'{self.CONVERSATION_DICT_KEY}:{user_id}')
        return conversation_names

    async def create_conversation(self, user_id: str) -> (str, bool):
        lgth = await self.r.llen(f'{self.CONVERSATION_ID_KEY}:{user_id}')
        if not lgth:
            await self.r.rpush(f'{self.CONVERSATION_ID_KEY}:{user_id}', 0)
            return 0, True
        max_converastion_id = int(await self.r.lindex(f'{self.CONVERSATION_ID_KEY}:{user_id}', lgth - 1))
        if max_converastion_id >= self.MAX_CONVERSATIONS - 1:
            logging.warn('too many conversations!')
            return -1, False
        new_conversation_id = max_converastion_id + 1
        await self.r.rpush(f'{self.CONVERSATION_ID_KEY}:{user_id}', new_conversation_id)
        await self.r.hset(f'{self.CONVERSATION_DICT_KEY}:{user_id}', new_conversation_id, 'Default Conversation')
        current_key = f'{self.CONVERSATION_CURRENT_KEY}:{user_id}'
        await self.r.set(current_key, new_conversation_id)
        content_key = f'{self.CONVERSATION_CONTENT_KEY}:{user_id}'
        # no need to set ttl for meta/conversation_id as it occupies very little space
        await self.r.hset(content_key, new_conversation_id, self._marshal(self.DEFAULT_CONVERSATION))
        await self.r.expire(content_key, self.DEFAULT_TTL)
        return new_conversation_id, True

    async def get_conversation(self, user_id: str, conversation_id: str = None):
        conversation_id = conversation_id or '0'
        r = self._unmarshal(await self.r.hget(f'{self.CONVERSATION_CONTENT_KEY}:{user_id}', conversation_id))
        if r:
            return r, True
        return None, False

    async def get_create_conversation(self, user_id: str, conversation_id: str = None):
        conversation_id = conversation_id or '0'
        conversation, flag = await self.get_conversation(user_id, conversation_id=conversation_id)
        if flag:
            return conversation, True
        conversation_id, flag = await self.create_conversation(user_id)
        if not flag:
            return None, False
        return await self.get_conversation(user_id, conversation_id=conversation_id)

    async def set_conversation(self, user_id: str, conversation_id: str = None, messages: List[any] = None):
        conversation_id = conversation_id or '0'
        content_key = f'{self.CONVERSATION_CONTENT_KEY}:{user_id}'
        await self.r.hset(content_key, conversation_id, self._marshal(messages))
        await self.r.expire(content_key, self.DEFAULT_TTL)
        return True

    async def clear_conversation(self, user_id: str, conversation_id: str = None):
        conversation_id = conversation_id or '0'
        await self.r.hdel(f'{self.CONVERSATION_CONTENT_KEY}:{user_id}', conversation_id)

    async def name_conversation(self, user_id: str, name: str, conversation_id: str = None):
        conversation_id = conversation_id or self.get_current_conversation_id(user_id)
        await self.r.hset(f'{self.CONVERSATION_DICT_KEY}:{user_id}', conversation_id, name)


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


@app.command('/flush')
async def flush_command(ack, body):
    user_id = body["user_id"]
    await manager.flush_conversation(user_id)
    await ack(text='All conversations flushed.')


# @app.command('/terminate')
# async def terminate_command(ack, body):
#     user_id = body["user_id"]
#     conversation_id = body.get('text')
#     await manager.clear_conversation(user_id, conversation_id)
#     await ack(text=f'Conversation {conversation_id or 0} terminated.')


@app.command('/nameit')
async def nameit_command(ack, body):
    user_id = body["user_id"]
    name = body.get('text')
    if not name:
        await ack(text='Please provide a name for the conversation.')
    conversation_id = await manager.get_current_conversation_id(user_id)
    await manager.name_conversation(user_id, name, conversation_id=conversation_id)
    await ack(text=f'Conversation {conversation_id} is now named {name}.')


@app.command("/ls")
async def hello_command(ack, body):
    user_id = body["user_id"]
    # await ack(f"Hi <@{user_id}>! {body['text']}")
    conversations = await manager.get_conversation_dict(user_id)
    current_conversation_id = await manager.get_current_conversation_id(user_id)
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
                        "text": f"*{key}*. {value}{' *<----Current Conversation---->*' if key == current_conversation_id else ''}"
                },
                "accessory": {
                    "type": "button",
                    "text": {
                            "type": "plain_text",
                        "emoji": True,
                        "text": "Enter"
                    },
                    "value": f"{key}",
                    "action_id": f"ls_enter_{key}"
                }
            }
            for key, value in conversations.items() if conversations
        ] + [{
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Create a new conversation",
                        "emoji": True
                    },
                    "value": "new",
                    "action_id": "ls_enter_new"
                }
            ]
        }]
    )


@app.action(re.compile(r'ls_enter_([0-9]+|new)'))
async def handle_conversation_switch(ack, context, body, say):
    print(body, context)
    user_id = body['user']['id']
    val = body['actions'][0]['value']
    await ack()
    if val == 'new':
        # create a new conversation
        conversation_id, flag = await manager.create_conversation(user_id)
        if not flag:
            await say(text='Failed to create a new conversation, allow no more than 10 conversations and please terminate one before creating a new one.')
            return
        await say(text=f'Conversation {conversation_id} created.')
    else:
        # switch to the conversation
        conversation_id = int(val)
        if conversation_id > 9:
            await say(text='Invalid conversation id.')
        await manager.set_current_conversation_id(user_id, conversation_id)
        await say(text=f'Conversation {conversation_id} attached.')


@ app.event("message")
async def handle_message_events(body, say):
    event = body['event']

    user_id = event['user']
    text = event['text']
    channel_id = event['channel']
    thread_ts = event.get('thread_ts')
    channel_type = event.get('channel_type')
    channel = event.get('channel')

    conversation_id = await manager.get_current_conversation_id(user_id)
    c, flag = await manager.get_create_conversation(user_id, conversation_id)
    if not c and not flag:
        await say(text='[System] Something went wrong, please try again later.')
        return
    if len(c) == 1:
        await say(text='[System] Hi! You\'ve started a new conversation! Please be patient and wait for ChatGPT to reply...')
    c.append({'role': 'user', 'content': text})
    message = await gpt.chat_completion(c)
    c.append({'role': message.role, 'content': message.content})
    await manager.set_conversation(user_id, conversation_id, messages=c)
    await say(text=message.content)


# @app.event("app_mention")
# async def event_test(event, say):
#     await say(f"Hi there, <@{event['user']}>!")
