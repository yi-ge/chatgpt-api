import asyncio
import os
import uuid
from threading import Timer
from urllib import parse

import aiohttp_cors
import socketio
from aiohttp import web
from dotenv import load_dotenv

from PyChatGPT.src.pychatgpt import Chat

load_dotenv()
env_dist = os.environ
sio = socketio.AsyncServer(cors_allowed_origins='*')
app = web.Application()
userUUIDSet, usingUUIDSet, logoutUUIDSet, tokenSet = set(), set(), set(), set()
timerMap, sidUUIDMap = {}, {}
email = env_dist.get('EMAIL')
password = env_dist.get('PASSWORD')

if email is None or password is None:
    raise Exception('Email and password are not set')

chat = Chat(email=email, password=password)

sio.attach(app)


def logout(userUUID):
    if userUUID in logoutUUIDSet:
        if userUUID in userUUIDSet: userUUIDSet.remove(userUUID)
        if userUUID in usingUUIDSet: usingUUIDSet.remove(userUUID)
        logoutUUIDSet.remove(userUUID)
        del timerMap[userUUID]
        asyncio.run(broadcastSystemInfo())


async def broadcastSystemInfo():
    onlineUserNum = len(userUUIDSet)
    waitingUserNum = onlineUserNum - len(usingUUIDSet)
    await sio.emit(
        'systemInfo', {
            'onlineUserNum': onlineUserNum if onlineUserNum > 1 else 1,
            'waitingUserNum': waitingUserNum if waitingUserNum > 0 else 0
        })


async def rushHandler(sid):
    if len(usingUUIDSet) < 1:  # System simultaneous load number
        token = str(uuid.uuid4())
        tokenSet.add(token)
        userUUID = sidUUIDMap.get(sid)
        usingUUIDSet.add(userUUID)
        await sio.emit('token', token, room=sid)
    else:
        await sio.emit('restricted', room=sid)


@sio.event
async def connect(sid, environ):
    queryDict = parse.parse_qs(environ['QUERY_STRING'])
    if 'userUUID' in queryDict.keys() and queryDict['userUUID'][0]:
        userUUID = queryDict['userUUID'][0]
        sidUUIDMap[sid] = userUUID
        if userUUID in logoutUUIDSet:
            logoutUUIDSet.remove(userUUID)
            try:
                timerMap[userUUID].cancel()
                del timerMap[userUUID]
            except:
                pass
        userUUIDSet.add(userUUID)
        print("connect ", userUUID)


@sio.event
async def rush(sid, data):
    await rushHandler(sid)


@sio.event
async def ready(sid, data):
    userUUID = sidUUIDMap.get(sid)
    if userUUID not in usingUUIDSet: await rushHandler(sid)
    await broadcastSystemInfo()


@sio.event
def disconnect(sid):
    userUUID = sidUUIDMap[sid]
    logoutUUIDSet.add(userUUID)
    timerMap[userUUID] = Timer(3, logout, (userUUID, ))
    timerMap[userUUID].start()
    del sidUUIDMap[sid]
    print('disconnect uuid:', userUUID)


async def index(request):
    return web.json_response({'error': -1})


async def chatgpt_get(request):
    text = parse.unquote(request.rel_url.query.get('text', ''))
    token = parse.unquote(request.rel_url.query.get('token', ''))
    userUUID = parse.unquote(request.rel_url.query.get('userUUID', ''))
    if token == '' or token not in tokenSet:
        uuidSidMap = {v: k for k, v in sidUUIDMap.items()}
        sid = uuidSidMap.get(userUUID)
        if sid is not None: await sio.emit('restricted', room=sid)
        return web.json_response({'code': -2})
    try:
        print("You: " + text)
        answer = chat.ask(text)
        print("AI: " + answer)
        return web.json_response({'code': 1, 'result': answer})
    except:
        return web.json_response({'code': -1})


# Configure default CORS settings.
cors = aiohttp_cors.setup(app,
                          defaults={
                              "*":
                              aiohttp_cors.ResourceOptions(expose_headers="*",
                                                           allow_headers="*")
                          })

app.router.add_get('/', index)
cors.add(app.router.add_get('/chatgpt', chatgpt_get))

if __name__ == '__main__':
    web.run_app(app, host="0.0.0.0", port=50000)
