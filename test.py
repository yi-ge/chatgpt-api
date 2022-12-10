import os

from dotenv import load_dotenv

from PyChatGPT.src.pychatgpt import Chat

load_dotenv()
env_dist = os.environ

email = env_dist.get('EMAIL')
password = env_dist.get('PASSWORD')

if email is None or password is None:
    raise Exception('Email and password are not set')

chat = Chat(email=email, password=password)
chat.cli_chat()