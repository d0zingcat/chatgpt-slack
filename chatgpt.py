import os
import time
from datetime import date
import json
from dataclasses import dataclass, field
from typing import Dict

import openai
import tiktoken


"""
TODO: should use async to evict expired context,
or one daemon timer to check
"""

MODEL_ENGINE: str = 'text-davinci-003'
TOKEN_LIMIT: int = 4000
# ENCODER = tiktoken.get_encoding("gpt2")
ENCODER = tiktoken.encoding_for_model("text-davinci-003")


@dataclass
class Conversation:
    start_time: float
    last_active_time: float
    chat_history: list = field(default_factory=list)
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
                 conversation_timeout: int = 30 * 60
                 ) -> None:
        self._CAPACITY = capacity
        self._CONTEXT_MAX = context_max
        self._TOKEN_MAX = token_max
        self._START_TIME = time.time()
        self._CHECKPOINT_TIME = self._START_TIME
        self._INTERVAL = check_interval
        self._CONVERSATION_TIMEOUT = conversation_timeout
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

    def _check_conversation_and_update(self):
        if self._should_check_contexts():
            # check conversation context
            self._check_conversation_contexts()
            self._CHECKPOING_TIME = time.time()

    def get_conversation(self, key: str):
        self._check_conversation_and_update()
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
    def __init__(self):
        OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
        self.api_key = OPENAI_API_KEY
        self.engine = MODEL_ENGINE

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

    def ask(self,
            req: str,
            conversation_id: str,
            model: str = None) -> str:
        openai.api_key = self.api_key
        conversation = None
        conversation = manager.get_conversation(conversation_id)
        if not conversation:
            conversation = manager.make_conversation(conversation_id)
        context = conversation.make_chat_context(req)
        print('context=', context)
        completion = self._get_completion(context)
        completion = self._process_completion(req, completion)
        print('completion=', completion)
        resp = completion['choices'][0]['text']
        conversation.add_history(req, resp)
        return resp


chatgpt = ChatGPT()
