import time
import random
import ssl
import json
import requests
import loguru
import websocket
from redis import StrictRedis, connection
from urllib.parse import urlencode

from signature.sign import get_x_sign
from barrage.library.barrageParser import *


# logger = logging.getLogger(__name__)
#
# logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')

class Client:

    _base_headers = {
        "Host": "webcast5-normal-c-hl.amemv.com",
        "response-format": "json",
        "sdk-version": "2",
        "passport-sdk-version": "18",
        "x-vc-bdturing-sdk-version": "2.1.0.cn",
        "x-ss-dp": "1128",
        "user-agent": "com.ss.android.ugc.aweme/150901 (Linux; U; Android 8.1.0; zh_CN_#Hans; Pixel; Build/OPM4.171019.021.D1; Cronet/TTNetVersion:f5cbac28 2021-04-21 QuicVersion:47946d2a 2020-10-14)",
    }

    def __init__(self, room_id, logger=None):
        self.room_id = room_id
        self.logger = logger or loguru.logger
        self.imp_id = None
        self.cursor = None
        self.device_id = f"4402404091555{random.randint(0, 10)}"
        self.barrage_key = f'(queue){room_id}'
        self.state_key = f'(state){room_id}'
        self.redis_client = StrictRedis(**self.redis_config)
        self.redis_client.delete(self.barrage_key)
        self.redis_client.delete(self.state_key)
        self.redis_client.hmset(
            self.state_key,
            {'state': 'start', 'count': 0, 'error': 'normal'}
        )

    def _http(self, ticket=int(time.time()*1e3)):
        url = "https://webcast3-normal-c-hl.amemv.com/webcast/im/fetch/"
        params = {
            "_rticket": ticket,
            "app_type": "normal",
            "update_version_code": "15509900",
            "os_api": "27",
            "device_id": self.device_id,
            "os_version": "8.1.0",
            "version_code": "150500",
            "app_name": "aweme",
            "version_name": "15.5.0",
            "device_platform": "android",
            "aid": "1128",
            "ts": int(time.time())
        }
        data = {
            "room_id": self.room_id,
            "fetch_rule": "1",
            "cursor": "0",
            "resp_content_type": "protobuf",
            "get_history": '1',
            "last_rtt": "0",
            "live_id": "1",
            "user_id": "0",
            "room_tag": "external",
            "identity": "audience",
            "recv_cnt": "0",
            "parse_cnt": "0"
        }
        x_sign = get_x_sign(url=urlencode(params))
        headers = self._base_headers.copy()
        headers['x-ss-req-ticket'] = str(ticket)
        headers['x-gorgon'] = x_sign['x-gorgon']
        headers['x-khronos'] = x_sign['x-khronos']
        try:
            response = requests.post(url, headers=headers, params=params, data=data)
            live_config = configParser(response.content)
            self.imp_id = live_config['impId']['imprp']
            self.cursor = live_config['cursor']
        except Exception as e:
            self.logger.warning('抖音直播间http请求错误：{}'.format(e))

    def _wss(self):
        wss = "wss://webcast100-ws-c-lf.amemv.com/webcast/im/push/"
        params = {
            "room_id": self.room_id,
            "cursor": self.cursor,
            "manifest_version_code": "150501",
            "_rticket": int(time.time()),
            "room_tag": "video",
            "rid": self.room_id,
            "device_id": self.device_id,
            "os_version": "8.1.0",
            "version_code": "150500",
            "webcast_sdk_version": "1960",
            "imprp": self.imp_id,
            "app_name": "aweme",
            "live_id": "1",
            "version_name": "15.5.0",
            "device_platform": "android",
            "aid": "1128",
            "ts": int(time.time())
        }
        return wss + '?' + urlencode(params)

    def connect_server(self):
        if not self.wss:
            return
        self.client = websocket.WebSocketApp(
            self.wss,
            on_open=self.on_open,
            on_error=self.on_error,
            on_message=self.on_message,
            on_close=self.on_close,
        )
        # 主线程会阻塞在这里
        self.client.run_forever(
            ping_payload=b'\x08\x01\x10\x01\x18\x01 \x01:\x02hbB\x00',
            ping_interval=20,
            sslopt={"cert_reqs": ssl.CERT_NONE},
            ping_timeout=10,
        )

    """websocket回调函数"""
    def on_open(self, client):
        self.logger.info(f'连接抖音{self.room_id}弹幕服务器')

    def on_message(self, client, message):
        if self.redis_client.hget(self.state_key, 'state').decode() == 'start':
            self.redis_client.hset(self.state_key, 'state', 'success')
        # print(f'message => {type(message)}',)
        messages = payloadEncode(message)
        messages = danmuParser(messages)
        for message in messages:
            if message.get('method') == 'WebcastChatMessage':
                barrage = {
                    'method': message.get('method'),
                    'content': message.get('content', ''),
                    'nick_name': message.get('userInfo', {}).get('nickName', ''),
                    'gender': message.get('userInfo', {}).get('gender', 0)
                }
                print(barrage)
                self.redis_client.lpush(
                    self.barrage_key,
                    json.dumps(barrage, ensure_ascii=False)
                )
            if message.get('method') == 'WebcastLikeMessage':
                barrage = {
                    'method': message.get('method'),
                    'nick_name': message.get('userInfo', {}).get('nickName', ''),
                    'count': message.get('count', 0),
                    'gender': message.get('userInfo', {}).get('gender', 0)
                }
                self.redis_client.lpush(
                    self.barrage_key,
                    json.dumps(barrage, ensure_ascii=False)
                )
            # if message.get('method') not in [
            #     'WebcastChatMessage', 'WebcastLikeMessage'
            #
            #     self.redis_client.hincrby(self.state_key, 'count', 1)
            #     self.logger.debug(message.get('content'))
            # # logger.debug(message)
            self.redis_client.lpush(
                self.barrage_key,
                json.dumps(message, ensure_ascii=False)
            )

    def on_error(self, client, error):
        self.redis_client.hset(self.state_key, 'error', str(error) or 'normal')
        self.logger.warning(f'连接幕服务器错误::{error}')

    def on_close(self, client, status, message):
        self.redis_client.hset(self.state_key, 'state', 'close')
        self.logger.info(f'连接关闭｜code:{status}｜msg:{message}')

    def run(self):
        self.logger.info(f'监控直播间::{self.room_id}')
        while not self.imp_id:
            self._http()
        self.wss = self._wss()
        self.connect_server()
        self.logger.info(f'监控结束::{self.room_id}')

    def close_connect(self):
        self.redis_client.hset(self.state_key, 'state', 'close')
        self.client.close()

    def get_barrage(self, count=100):
        barrage_list = list()
        for _ in range(count):
            barrage = self.redis_client.rpop(self.barrage_key)
            if not barrage:
                break
            barrage_list.append(barrage.decode())
        return barrage_list


if __name__ == '__main__':
    Client(room_id='7056643849925511951').run()

