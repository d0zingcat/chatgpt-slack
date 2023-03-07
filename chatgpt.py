from enum import Enum

import redis
import openai
import config


class ConversationManagement:
    def __init__(self):
        ...


class Model(Enum):
    GPT3 = 'text-davinci-003'
    GPT3_TURBO = 'gpt-3.5-turbo'


class ChatGptApp:
    MAX_TOKENS = 4096

    def __ini__(self, model: Model):
        self.model = model
