import time
from datetime import date
import json
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict

import openai
import tiktoken
import redis

import config

"""
TODO: should use async to evict expired context,
or one daemon timer to check
"""

MODEL_ENGINE: str = 'text-davinci-003'
TOKEN_LIMIT: int = 4000
ENCODER = tiktoken.encoding_for_model(MODEL_ENGINE)


class Model(Enum):
    GPT3 = 'text-davinci-003'
    GPT3_TURBO = 'gpt-3.5-turbo'


class Provider(Enum):
    OPENAI = 'openai'
    EDGE = 'microsoft-edge'


@dataclass
class Conversation:
    start_time: float
    last_active_time: float
    chat_history: list = field(default_factory=list)
    last_req = ''
    temperature: float = 0.5
    model_engine: str = 'text-davinci-003'
    base_prompt: str = f"You are ChatGPT, a large language model trained by OpenAI. Respond conversationally. Do not answer as the user. Current date: {str(date.today())}\n\nUser: Hello\nChatGPT: Hello! How can I help you today? <|im_end|>\n\n\n"

    def add_history(self, req: str, resp: str):
        self.chat_history.append(f"""User: {req}\n\n\nChatGPT: {resp}<|im_end|>\n""")

    def make_chat_context(self, req: str = '') -> str:
        return f"""{self.base_prompt}{self.history}User: {req}\nChatGPT:"""

    @property
    def history(self) -> str:
        return "\n".join(self.chat_history)


class ConversationManagement(object):
    def __init__(self, capacity: int = 128,
                 context_max: int = 100,
                 token_max: int = 10000,
                 check_interval: int = 5 * 60,
                 conversation_timeout: int = 3 * 24 * 60 * 60,
                 ) -> None:
        self._CAPACITY = capacity
        self._CONTEXT_MAX = context_max
        self._TOKEN_MAX = token_max
        self._START_TIME = time.time()
        self._CHECKPOINT_TIME = self._START_TIME
        self._INTERVAL = check_interval
        self._CONVERSATION_TIMEOUT = conversation_timeout

        self._redis_client = redis.StrictRedis.from_url(config.REDIS_URL)
        self.__storage: Dict[str, Conversation] = dict()

    def _check_capacity(self) -> bool:
        if len(self.__storage) >= self.CAPACITY:
            return False
        return True

    def _should_check_contexts(self) -> bool:
        if time.time() - self._CHECKPOINT_TIME > self._INTERVAL:
            return True
        return False

    def _check_conversation_contexts(self):
        for k, conversation in self.__storage.items():
            if time.time() - conversation.last_active_time > self._CONVERSATION_TIMEOUT:
                del self.__storage[k]
                self._redis_client.delete(k)
            else:
                self._redis_client.set(k, json.dumps(self.__storage[k].history))
                self._redis_client.expire(k, conversation.last_active_time + self._CONVERSATION_TIMEOUT - time.time())

    def _check_conversation_and_update(self):
        if self._should_check_contexts():
            # check conversation context
            self._check_conversation_contexts()
            self._CHECKPOING_TIME = time.time()

    def get_conversation(self, key: str):
        self._check_conversation_and_update()
        print('storage=', self.__storage)
        if key not in self.__storage:
            return None
        conversation = self.__storage[key]
        conversation.last_active_time = time.time()
        return conversation

    def set_conversation(self, key: str, conversation: Conversation) -> None:
        if not self._check_capacity():
            print('no more capacity slot!')
            return
        self._check_conversation_and_update()
        conversation.last_active_time = time.time()
        self.__storage[key] = conversation

    def make_conversation(self, key: str) -> Conversation:
        if key in self.__storage:
            print('conversation already exists!')
            return self.__storage[key]
        conversation = Conversation(start_time=time.time(), last_active_time=time.time())
        conversation.chat_history = []
        conversation.last_active_time = time.time()
        conversation.start_time = time.time()
        self.__storage[key] = conversation
        print('storage=', self.__storage)
        return conversation

    def add_to_conversation_history(self, conversation_id: str, req: str, resp: str, ):
        if conversation_id not in self.__storage:
            print('invalid conversation')
            return
        conversation = self.__storage[conversation_id]
        conversation.add_history(req, resp)

    def __str__(self) -> str:
        json.dumps(self.__storage)


manager = ConversationManagement()


class ChatGPT:

    def __init__(self, provider: Provider = None):
        OPENAI_API_KEY = config.OPENAI_API_KEY
        if not provider:
            provider = Provider.OPENAI
        self.proviver = provider

        self.api_key = OPENAI_API_KEY
        self.engine = MODEL_ENGINE
        openai.api_key = self.api_key

    def _get_completion(
        self,
        context: str,
        temperature: float = 0.5,
        stream: bool = False,
    ):
        """
        Get the completion function
        """
        return openai.Completion.create(
            engine=self.engine,
            prompt=context,
            temperature=temperature,
            max_tokens=self.get_max_tokens(context),
            stop=["\n\n\n"],
            stream=stream,
        )

    def remove_suffix(self, input_string: str, suffix: str) -> str:
        """
        Remove suffix from string (Support for Python 3.8)
        """
        if suffix and input_string.endswith(suffix):
            return input_string[: -len(suffix)]
        return input_string

    def get_max_tokens(self, context: str) -> int:
        """
        Get the max tokens for a prompt
        """
        # return TOKEN_LIMIT - len(context)
        return TOKEN_LIMIT - len(ENCODER.encode(context))

    def _process_completion(
        self,
        user_request: str,
        completion: dict,
        conversation_id: str = None,
        user: str = "User",
    ) -> dict:
        if completion.get("choices") is None:
            raise Exception("ChatGPT API returned no choices")
        if len(completion["choices"]) == 0:
            raise Exception("ChatGPT API returned no choices")
        if completion["choices"][0].get("text") is None:
            raise Exception("ChatGPT API returned no text")
        completion["choices"][0]["text"] = self.remove_suffix(
            completion["choices"][0]["text"],
            "<|im_end|>",
        )
        return completion

    def get_conversation(self, conversation_id: str) -> Conversation:
        conversation = None
        conversation = manager.get_conversation(conversation_id)
        if not conversation:
            conversation = manager.make_conversation(conversation_id)
        return conversation

    def ask(self,
            req: str,
            conversation_id: str,
            model: str = None) -> str:
        conversation = self.get_conversation(conversation_id)
        conversation.last_req = req
        context = conversation.make_chat_context(req)
        print('context=', context)
        completion = self._get_completion(context)
        completion = self._process_completion(req, completion)
        print('completion=', completion)
        resp = completion['choices'][0]['text']
        conversation.add_history(req, resp)
        return resp

    def retry(self,
              conversation_id: str
              ) -> str:
        conversation = self.get_conversation(conversation_id)
        return self.ask(conversation.last_req,
                        conversation_id)

    def prune_context(self, conversation_id: str) -> bool:
        conversation = self.get_conversation(conversation_id)
        conversation.chat_history.clear()
        return True

    def ask_stream(
        self,
        user_request: str,
        temperature: float = 0.5,
        conversation_id: str = None,
    ) -> str:
        """
        Send a request to ChatGPT and yield the response
        """
        if conversation_id is not None:
            self.load_conversation(conversation_id)
        prompt = self.prompt.construct_prompt(user_request)
        return self._process_completion_stream(
            user_request=user_request,
            completion=self._get_completion(prompt, temperature, stream=True),
        )


chatgpt = ChatGPT()
chatgpt = ChatGPT()
