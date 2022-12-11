import asyncio
import json
import os
import uuid
from threading import Timer
from urllib import parse

import socketio
from aiohttp import web
from dotenv import load_dotenv

from PyChatGPT.src.pychatgpt import Chat, Options

load_dotenv()
env_dist = os.environ
adapter = env_dist.get('ADAPTER', '')
account_file_path = env_dist.get('ACCOUNT_FILE_PATH', '')

if adapter == 'local':
    user_uuid_set, using_uuid_set, logout_uuid_set, token_set, using_email_set = set(
    ), set(), set(), set(), set()
    timer_map, sid_uuid_map, token_email_map, email_chat_map = {}, {}, {}, {}

    options = Options()

    # [New] Enable, Disable logs
    options.log = False

    # Track conversation
    options.track = True

    if os.path.exists(account_file_path) is False:
        raise Exception('See the account.example.json file')

    with open("./account.json", 'r') as f:
        account_list = json.load(f)
        for i in account_list:
            email = i.get('email')
            password = i.get('password')
            email_chat_map[email] = Chat(email=email,
                                         password=password,
                                         options=options)
        account_list_len = len(account_list)
else:
    raise Exception('See the env.example file')
    # TODO: Redis operations

sio = socketio.AsyncServer(cors_allowed_origins='*')
app = web.Application()

sio.attach(app)


def logout(userUUID):
    if userUUID in logout_uuid_set:
        if userUUID in user_uuid_set: user_uuid_set.remove(userUUID)
        if userUUID in using_uuid_set: using_uuid_set.remove(userUUID)
        logout_uuid_set.remove(userUUID)
        del timer_map[userUUID]
        asyncio.run(broadcastSystemInfo())


async def broadcastSystemInfo():
    onlineUserNum = len(user_uuid_set)
    waitingUserNum = onlineUserNum - len(using_uuid_set)
    await sio.emit(
        'systemInfo', {
            'onlineUserNum': onlineUserNum if onlineUserNum > 1 else 1,
            'waitingUserNum': waitingUserNum if waitingUserNum > 0 else 0,
            'accountCount': account_list_len
        })


async def rushHandler(sid):
    if len(using_uuid_set) < account_list_len:  # System simultaneous load number
        token = str(uuid.uuid4())
        for i in email_chat_map.keys():
            if i not in using_email_set:
                using_email_set.add(i)
                token_email_map[token] = i
                token_set.add(token)
                userUUID = sid_uuid_map.get(sid)
                using_uuid_set.add(userUUID)
                await sio.emit('token', token, room=sid)
                return
    await sio.emit('restricted', room=sid)


def getAnswer(sid, text, token):
    try:
        print("You: " + text)
        email = token_email_map.get(token)
        if email is None:
            asyncio.run(sio.emit('answer', {
                'code': -3,
                'result': '请求超时，请刷新重试'
            }, room=sid))
        if email_chat_map[email] is None:
            asyncio.run(sio.emit('answer', {
                'code': -4,
                'result': '系统异常，请刷新重试'
            }, room=sid))
        answer, _, _ = email_chat_map[email].ask(text)
        if answer:
            print("AI: " + answer)
            asyncio.run(sio.emit('answer', {
                'code': 1,
                'result': answer
            }, room=sid))
        else:
            asyncio.run(sio.emit('answer', {
                'code': -2,
                'result': '网络错误'
            }, room=sid))
    except Exception as err:
        print('repr(err):\t', repr(err))
        asyncio.run(sio.emit('answer', {
            'code': -1,
            'msg': str(err)
        }, room=sid))


@sio.event
async def connect(sid, environ):
    queryDict = parse.parse_qs(environ['QUERY_STRING'])
    if 'userUUID' in queryDict.keys() and queryDict['userUUID'][0]:
        userUUID = queryDict['userUUID'][0]
        sid_uuid_map[sid] = userUUID
        if userUUID in logout_uuid_set:
            logout_uuid_set.remove(userUUID)
            try:
                timer_map[userUUID].cancel()
                del timer_map[userUUID]
            except:
                pass
        user_uuid_set.add(userUUID)
        print("connect ", userUUID)


@sio.event
async def rush(sid, data):
    await rushHandler(sid)


@sio.event
async def ready(sid, data):
    userUUID = sid_uuid_map.get(sid)
    if userUUID not in using_uuid_set: await rushHandler(sid)
    await broadcastSystemInfo()


@sio.event
def disconnect(sid):
    userUUID = sid_uuid_map[sid]
    logout_uuid_set.add(userUUID)
    timer_map[userUUID] = Timer(3, logout, (userUUID, ))
    timer_map[userUUID].start()
    del sid_uuid_map[sid]
    print('disconnect uuid:', userUUID)


@sio.event
async def chatgpt(sid, data):
    text = data.get('text')
    token = data.get('token')
    # userUUID = sid_uuid_map[sid]
    if token is None or token not in token_set:
        await sio.emit('restricted', room=sid)
    task = Timer(3, getAnswer, (
        sid,
        text,
        token,
    ))

    task.start()


async def index(request):
    return web.json_response({'error': -1})


app.router.add_get('/', index)

if __name__ == '__main__':
    web.run_app(app, host="0.0.0.0", port=50000)
