import time
import requests
import random
import string
import json
from Crypto.Cipher import AES
from urllib.parse import urlencode
from requests.utils import dict_from_cookiejar

from device import Device
from signature.sign import get_x_sign, get_tt_sign, get_x_stub

from loguru import logger

class Register:

    @staticmethod
    def get_ticket():
        return int(time.time() * 1e3)

    @staticmethod
    def random_key_iv():
        src_digits = string.digits
        src_lowercase = string.ascii_lowercase
        random_seed = ''.join(src_digits + src_lowercase)
        key = ''.join(random.sample(random_seed, 32))
        random_seed = ''.join(src_digits + src_lowercase)
        iv = ''.join(random.sample(random_seed, 16))
        return key, iv

    def aes_decrypt(self, content, key=None, iv=None):
        cipher = AES.new((key or self.key).encode(), AES.MODE_CBC, (iv or self.iv).encode())
        aes_decode_bytes = cipher.decrypt(content)
        return aes_decode_bytes

    def base_headers(self, ticket):
        return {
            "activity_now_client": str(time.time() * 1e3),
            "sdk-version": "2",
            "passport-sdk-version": "18",
            "x-ss-req-ticket": str(ticket),
            "x-ss-dp": "1128",
            "user-agent": self.device.UserAgent,
        }

    def sign(self, url, params, ticket=int(time.time() * 1e3), headers=None):
        if not headers:
            headers = self.base_headers(ticket)
        else:
            headers['x-ss-req-ticket'] = str(ticket)
        x_sign = get_x_sign(urlencode(params))
        if not x_sign:
            return False
        headers["x-gorgon"] = x_sign["x-gorgon"]
        headers["x-khronos"] = str(x_sign["x-khronos"])
        return headers

    def register_api(self, url='https://log.snssdk.com/service/2/device_register/'):
        ticket = self.get_ticket()
        params = self.device.register_params()
        params['_rticket'] = str(ticket)
        data = self.device.register_data()
        enc_data = get_tt_sign(data)
        headers = self.sign(url, params, ticket=ticket)
        headers["Host"] = "log3-misc.amemv.com"
        headers["x-ss-stub"] = get_x_stub(json.dumps(data, ensure_ascii=False))
        headers["content-type"] = "application/octet-stream;tt-data=a"
        # print(self.proxy)
        try:
            self.register_result = requests.post(url, params=params, headers=headers, data=enc_data, proxies=self.proxy)
            result = self.register_result.json()
            if result.get('new_user') != 1:
                # logger.debug(f'register_api请求失败::{result}')
                return
            self.device_id = result['device_id']
            self.iid = result['install_id']
            self.device.device_id = self.device_id
            self.device.iid = self.iid
            cookies = dict_from_cookiejar(self.register_result.cookies)
            self.ttreq = cookies['ttreq']
            return True
        except Exception as e:
            # import traceback
            # traceback.print_exc()
            # logger.debug(f'register_api请求错误::{e}')
            pass

    def do_register(self, proxy=None):
        self.device = Device()
        self._proxy = proxy
        if isinstance(proxy, tuple):
            self.proxy, self.address = proxy
        else:
            self.address = None
            self.proxy = proxy
        self.key, self.iv = self.random_key_iv()
        if not self.register_api():
            # logger.debug(f'register_api未成功')
            return
        return self.device_info()

    def device_info(self):
        result = dict()
        result['device_id'] = self.device_id
        result['openudid'] = self.device.openudid
        result['cdid'] = self.device.cdid
        result['mac'] = self.device.mac
        result['iid'] = self.iid
        result['uuid'] = self.device.uuid
        result['channel'] = self.device.channel
        result['proxies'] = self.proxy
        result['device_type'] = self.device.type
        result['device_brand'] = self.device.brand
        result['os_api'] = self.device.os_api
        result['os_version'] = self.device.os_version
        result['resolution'] = self.device.resolution
        result['dpi'] = self.device.dpi
        result['aid'] = 1128
        result['app_name'] = 'aweme'
        result['ua'] = self.device.UserAgent
        result['version_name'] = self.device.version['version_name']
        result['version_code'] = self.device.version['version_code']
        result['manifest_version_code'] = self.device.version['manifest_version_code']
        result['update_version_code'] = self.device.version['update_version_code']
        result['proxy'] = self._proxy
        result['ttreq'] = self.ttreq
        return result


if __name__ == '__main__':
    device = Register().do_register()
    print(device)