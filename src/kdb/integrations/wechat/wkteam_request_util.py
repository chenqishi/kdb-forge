import requests
import json
try:
    from common.log import logger
    from common import qr_utils
except:
    import logging
    logger = logging.getLogger(__name__)

import time
import re
import os
from urllib.parse import unquote, urlparse
import random

# 全局请求配置
CONNECT_TIMEOUT = 3  # 连接超时3秒
READ_TIMEOUT = 40    # 读取超时20秒
MAX_RETRIES = 3
POOL_CONNECTIONS = 20
POOL_MAXSIZE = 20

# 配置全局连接池
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(
    max_retries=MAX_RETRIES,
    pool_connections=POOL_CONNECTIONS,
    pool_maxsize=POOL_MAXSIZE,
    pool_block=False  # 当连接池满时不阻塞，而是抛出异常
)
session.mount('http://', adapter)
session.mount('https://', adapter)

def clear_connection_pool():
    """清空连接池"""
    global session
    try:
        session.close()  # 关闭所有连接
    except Exception as e:
        logger.error(f"关闭连接池发生错误: {str(e)}")
    finally:
        # 重新创建session和adapter
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            max_retries=MAX_RETRIES,
            pool_connections=POOL_CONNECTIONS,
            pool_maxsize=POOL_MAXSIZE,
            pool_block=False  # 当连接池满时不阻塞，而是抛出异常
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)

def safe_request(method, url, **kwargs):
    """
    安全的请求包装器，确保响应对象被正确关闭
    """
    kwargs.setdefault('timeout', (CONNECT_TIMEOUT, READ_TIMEOUT))
    try:
        with session.request(method, url, **kwargs) as response:
            response.raise_for_status()
            return response.json()
    except requests.exceptions.ConnectionError as e:
        logger.error(f"连接错误: {str(e)}")
        clear_connection_pool()
        raise
    except requests.exceptions.Timeout as e:
        logger.error(f"请求超时: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"请求发生错误: {str(e)}")
        raise

class WxWkteamRequestUtil(object):
    def __init__(self, base_url=None, account=None, 
                 password=None, proxy=None, wcId=''):
        """
        初始化请求工具类
        """
        self.config_dict = {
            'base_url': base_url,
            'account': account,
            'password': password,
            'proxy': proxy,
            'wcId': wcId,
            'wId': '',
            'auth_token': None
        }
        self.qr_download_times = 0
        self.login_status = {}
        self.user_info_management_dict = {'id_to_user_info': dict(),  # 值为list
                                       'name_to_user_info': dict()}  # 值为list

        

    def init_config(self, config_path):
        config_dict = json.load(open(config_path, 'r', encoding='utf-8'))
        self.config_dict.update(config_dict)
        self.login_status = config_dict
        if not self.config_dict['base_url'] or not self.config_dict['account'] \
            or not self.config_dict['password'] or not self.config_dict['proxy']:
            logger.error(f"配置文件读取失败, 请检查配置文件")
            return False
        if 'magnagement_dict_path' in config_dict and os.path.exists(config_dict['magnagement_dict_path']):
            self.user_info_management_dict = json.load(open(config_dict['magnagement_dict_path'], 'r', encoding='utf-8'))
        
            
        return True 

    def login_eyun(self, username=None, password=None):
        """
        登录易云平台
        Args:
            username: 用户名
            password: 密码
        Returns:
            bool: 登录成功返回True，失败返回False
        """
        headers = {
            'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
            'Content-Type': 'application/json'
        }
        
        login_url = f"{self.config_dict['base_url']}/member/login"
        if username is None:
            username = self.config_dict['account']
        if password is None:
            password = self.config_dict['password']
        # 构建请求体
        payload = {
            "account": username,
            "password": password
        }
        
        try:
            response_data = safe_request('POST', login_url, headers=headers, json=payload)
            if response_data.get('code') == '1000':
                # 登录成功，保存token
                self.config_dict['auth_token'] = response_data['data']['Authorization']
                return True
            else:
                # 登录失败
                self.config_dict['auth_token'] = None
                return False
                
        except Exception as e:
            logger.error(f"登录请求发生错误: {str(e)}")
            self.config_dict['auth_token'] = None
            return False

    def login_wechat(self):
        """
        登录微信
        Returns:
            dict: 返回登录结果，包含状态码、消息和数据
        """
        headers = {
            'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
            'Content-Type': 'application/json'
        }
        
        # 如果已经获取到auth_token，添加到请求头中
        if self.config_dict['auth_token']:
            headers['Authorization'] = self.config_dict['auth_token']
            
        login_url = f"{self.config_dict['base_url']}/iPadLogin"
        
        # 构建请求体
        payload = {
            "proxy": self.config_dict['proxy'],
            "wcId": self.config_dict['wcId']
        }
        
        try:
            response = session.post(
                login_url,
                headers=headers,
                json=payload
            )
            
            response_data = response.json()
            
            if response_data.get('code') == '1000':
                # 登录成功，保存wId
                self.config_dict['wId'] = response_data['data']['wId']
            
            return response_data
                
        except Exception as e:
            logger.error(f"微信登录请求发生错误: {str(e)}")
            return {
                "message": f"请求异常: {str(e)}",
                "code": "9999",
                "data": None
            }

    def check_login(self):
        """
        检查微信登录状态
        Returns:
            dict: 返回登录状态信息，包含状态码、消息和数据
        """
        headers = {
            'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
            'Content-Type': 'application/json'
        }
        
        if self.config_dict['auth_token']:
            headers['Authorization'] = self.config_dict['auth_token']
            
        check_url = f"{self.config_dict['base_url']}/getIPadLoginInfo"
        
        payload = {
            "wId": self.config_dict['wId']
        }
        
        try:
            response = session.post(
                check_url,
                headers=headers,
                json=payload
            )
            
            response_data = response.json()
            
            if response_data.get('code') == '1000':
                self.config_dict['wcId'] = response_data['data']['wcId']
            
            return response_data
                
        except Exception as e:
            logger.error(f"检查登录状态请求发生错误: {str(e)}")
            return {
                "message": f"请求异常: {str(e)}",
                "code": "9999",
                "data": None
            }

    def auto_login(self, time_sleep=2, 
                   qrCallback=None, 
                   enableCmdQR=2,
                   hotReload=False,
                   save_config_path=None, 
                   retry_count=3):
        """
        循环检查登录状态
        """
        self.qr_download_times += 1
        if not self.login_eyun(self.config_dict['account'], self.config_dict['password']):
            logger.error(f"登录易云平台失败, 请检查原因, 账号={self.config_dict['account']} 密码={self.config_dict['password']}")
            return None
        else:
            logger.info(f"登录易云平台成功, 账号={self.config_dict['account']} 授权={self.config_dict['auth_token']}")

        if self.is_alive():
            status_info = self.check_login()
            self.login_status.update(status_info['data'])
            return self.login_status
        
        logger.info(f"微信未登陆，进行微信登陆")
        result_dict = dict() 

        for i in range(retry_count):
            status_info = self.login_wechat()
            if status_info.get('code') != '1000':
                logger.error(f"登录微信失败, 请检查原因, status_info={status_info}")
                return None
            
            
            qr_download_url = status_info['data']['qrCodeUrl']
            qr_url = status_info['data']['url']
            qrStorage = qr_utils.get_QR(qr_url, qr_download_url,
                            enableCmdQR=enableCmdQR,
                            qrCallback=qrCallback)
            result_dict.update(status_info['data'])

            status_info = self.check_login()
            if status_info.get('code') == '1000':
                result_dict.update(status_info['data'])
                self.login_status = result_dict
                if save_config_path:
                    with open(save_config_path, 'w', encoding='utf-8') as f:
                        json.dump(self.config_dict, f, ensure_ascii=False)
                return result_dict            
            time.sleep(time_sleep)
        return None

    def _make_request(self, endpoint, payload, error_msg_prefix="请求", retry_count=2):
        """
        通用请求处理方法，包含重试逻辑
        Args:
            endpoint: API端点
            payload: 请求体
            error_msg_prefix: 错误信息前缀
            retry_count: 重试次数，默认2次
        Returns:
            tuple: (success, data) success表示是否成功，data为响应数据
        """
        headers = self._get_common_headers()
        url = f"{self.config_dict['base_url']}/{endpoint}"
        
        for attempt in range(retry_count + 1):
            try:
                response_data = safe_request('POST', url, headers=headers, json=payload)
                if response_data.get('code') == '1000':
                    return True, response_data.get('data')
                else:
                    logger.error(f"第{attempt + 1}次请求: url={url} headers={headers} payload={payload} {error_msg_prefix}失败: {response_data.get('message')}")
                    if attempt < retry_count:
                        time.sleep(1 * (attempt + 1))  # 递增等待时间
                        continue
                    return False, None
                
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                logger.warning(f"第{attempt + 1}次请求发生网络错误: {str(e)}")
                if attempt < retry_count:
                    time.sleep(1 * (attempt + 1))
                    continue
                return False, None
            except Exception as e:
                logger.error(f"第{attempt + 1}次{error_msg_prefix}发生错误: {str(e)}")
                if attempt < retry_count:
                    time.sleep(1 * (attempt + 1))
                    continue
                return False, None
        
        return False, None

    def set_callback_url(self, call_back_url):
        """
        设置回调URL
        Args:
            call_back_url: 回调URL地址
        Returns:
            bool: 设置成功返回True，失败返回False
        """
        payload = {
            "httpUrl": call_back_url,
            "type": 2
        }
        
        success, _ = self._make_request(
            "setHttpCallbackUrl",
            payload,
            "设置回调URL"
        )
        return success
        
    def set_inner_foward_url(self, call_back_url):
        """
        设置内部转发URL
        Args:
            call_back_url: 回调URL地址
        Returns:
            bool: 设置成功返回True，失败返回False
        """
        headers = self._get_common_headers()
        payload = {
            "messageType": "set_inner_forward",
            "httpUrl": call_back_url,
            "wcId": self.config_dict['wcId']
        }
        req_url = self.config_dict.get('inner_forward_url', 'https://www.lufitglobalselling.com/wkteam_forward/')
        try:
            safe_request('POST', req_url, headers=headers, json=payload)
            return True
        except Exception as e:
            logger.error(f"设置内部转发URL失败: {str(e)}")
            return False

    def get_detail_info_by_ids(self, user_ids):
        """
        根据用户ID获取用户信息
        Args:
            user_ids: 用户ID列表或字符串，多个ID用逗号分隔
        Returns:
            list: 成功返回用户信息列表，失败返回空列表
        """
        # 如果传入的是列表，将其转换为逗号分隔的字符串
        if isinstance(user_ids, list):
            wcId = ','.join(user_ids)
        else:
            wcId = user_ids
            
        payload = self._get_common_payload()
        payload["wcId"] = wcId
        
        success, data = self._make_request(
            "getContact",
            payload,
            "获取用户详细信息"
        )
        return data if success else []

    def is_alive(self):
        """
        检查微信是否在线
        Returns:
            bool: 在线返回True，离线或请求失败返回False
        """
        payload = self._get_common_payload()
        success, data = self._make_request(
            "isOnline",
            payload,
            "检查在线状态"
        )
        #logger.info(f"检查在线状态 success={success} data={data}, playload={payload}")
        return success and data.get('isOnline', False)

    def init_contactlist(self):
        """
        初始化联系人列表
        Returns:
            bool: 初始化成功返回True，失败返回False
        """
        payload = self._get_common_payload()
        success, _ = self._make_request(
            "initAddressList",
            payload,
            "初始化联系人列表"
        )
        return success

    def get_contactlist(self):
        """
        获取联系人列表
        Returns:
            dict: 成功返回联系人列表数据，失败返回None
        """
        payload = self._get_common_payload()
        success, data = self._make_request(
            "getAddressList",
            payload,
            "获取联系人列表"
        )
        return data if success else None

    def _get_common_headers(self):
        """
        获取通用请求头
        Returns:
            dict: 包含通用headers的字典
        """
        headers = {
            'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
            'Content-Type': 'application/json'
        }
        
        if self.config_dict['auth_token']:
            headers['Authorization'] = self.config_dict['auth_token']
            
        return headers
    
    def _get_common_payload(self):
        """
        获取通用请求体
        Returns:
            dict: 包含通用payload的字典
        """
        return {
            "wId": self.config_dict['wId']
        }

    def forwardUrl(self, wcId, content):
        """
        转发URL请求
        Args:
            wcId: 用户ID
            content: XML格式的消息内容
        Returns:
            bool: 成功返回True，失败返回None
        """
        payload = self._get_common_payload()
        payload.update({
            "wcId": wcId,
            "content": content
        })
        
        success, _ = self._make_request(
            "forwardUrl",
            payload,
            "转发URL请求"
        )
        
        return True if success else None

    def run(self, call_back_url):
        """
        运行主流程
        Args:
            call_back_url: 回调URL地址
        Returns:
            dict: 成功返回联系人列表数据，失败返回None
        """
        #is_set_outer_callback = self.set_callback_url(self.config_dict['inner_forward_url'])
        #logger.debug(f"[WX] is_set_outer_callback={is_set_outer_callback}, call_back_url={self.config_dict['inner_forward_url']}")
        is_set_callback = self.set_inner_foward_url(call_back_url)
        logger.debug(f"[WX] is_set_callback={is_set_callback}, call_back_url={call_back_url}")
        if not is_set_callback:
            return None
        is_init_contactlist = self.init_contactlist()
        if not is_init_contactlist:
            return None
        result_dict = self.get_contactlist()
        self.init_management_dict(result_dict)
        return result_dict
    
    def init_management_dict(self, contact_list):
        """
        初始化用户信息管理字典
        Args:
            contact_list: 联系人列表数据
        """
        friends_list = contact_list.get('friends', [])
        # 使用id判断是否需要获取信息
        if friends_list:
            no_info_friend_list = filter(lambda friend: friend not in self.user_info_management_dict['id_to_user_info'], friends_list)
        else:
            no_info_friend_list = []

        chatrooms_list = contact_list.get('chatrooms', [])
        if chatrooms_list:
            no_info_chatroom_list = filter(lambda chatroom: chatroom not in self.user_info_management_dict['id_to_user_info'], chatrooms_list)
        else:
            no_info_chatroom_list = []

        def _supply_user_info_batch(user_list, batch_size=15, is_room=False):
            """
            批量获取用户信息并更新到user_info_management_dict中
            Args:
                user_list: 需要获取信息的用户ID列表
                batch_size: 每批处理的用户数量，默认15
                is_room: 是否为群聊，默认False
            """
            user_list = list(user_list)  # 将filter对象转换为列表
            for i in range(0, len(user_list), batch_size):
                batch_users = user_list[i:i + batch_size]
                # 将用户ID用逗号连接
                user_ids = ','.join(batch_users)
                # 获取用户信息
                user_info_list = self.get_detail_info_by_ids(user_ids)
                if not user_info_list:
                    continue
                time.sleep(0.1 * random.randint(1, 15))
                # 更新用户信息字典
                for user_info in user_info_list:
                    user_name = user_info.get('userName')
                    nick_name = user_info.get('nickName')
                    user_info['is_room'] = is_room
                    if nick_name:  # 没有nickname的都不缓存
                        # 初始化列表（如果不存在）且 检查是否已存在相同id的信息
                        if user_name not in self.user_info_management_dict['id_to_user_info']:
                            self.user_info_management_dict['id_to_user_info'][user_name] = []
                        else:
                            continue
                        self.user_info_management_dict['id_to_user_info'][user_name].append(user_info)                                                
                        if nick_name not in self.user_info_management_dict['name_to_user_info']:
                            self.user_info_management_dict['name_to_user_info'][nick_name] = []
                        # 检查是否已存在相同id的信息
                        if not any(info.get('userName') == user_name for info in self.user_info_management_dict['name_to_user_info'][nick_name]):
                            self.user_info_management_dict['name_to_user_info'][nick_name].append(user_info)

        # 分别处理好友和群聊
        _supply_user_info_batch(no_info_friend_list)
        _supply_user_info_batch(no_info_chatroom_list, is_room=True)
        
        # 如果配置了保存路径，保存更新后的用户信息
        self.save_management_dict()
        
    def save_management_dict(self):
        """
        保存用户信息管理字典
        """
        if 'magnagement_dict_path' in self.config_dict:
            with open(self.config_dict['magnagement_dict_path'], 'w', encoding='utf-8') as f:
                json.dump(self.user_info_management_dict, f, ensure_ascii=False, indent=2)
        else:
            logger.error(f"未配置保存路径, 无法保存用户信息管理字典")
        return True

    def sendText(self, wcId, content):
        """
        发送文本消息
        Args:
            wcId: 接收消息的微信ID
            content: 消息内容
        Returns:
            bool: 成功返回True，失败返回None
        """
        payload = self._get_common_payload()
        payload.update({
            "wcId": wcId,
            "content": content
        })
        
        success, _ = self._make_request(
            "sendText",
            payload,
            "发送文本消息"
            )
        return True if success else None

    def sendImage(self, wcId, image_url):
        """
        发送图片消息
        Args:
            wcId: 接收消息的微信ID
            image_url: 图片的URL地址
        Returns:
            bool: 发送成功返回True，失败返回None
        """
        payload = self._get_common_payload()
        payload.update({
            "wcId": wcId,
            "content": image_url
        })
        
        success, _ = self._make_request(
            "sendImage2",
            payload,
            "发送图片消息"
            )
        return True if success else None
            

    def sendFileUrl(self, wcId, file_url, file_name=None):
        """
        发送文件消息
        Args:
            wcId: 接收消息的微信ID
            file_url: 文件的URL地址
            file_name: 文件名称，如果为None则从URL中推导
        Returns:
            bool: 发送成功返回True，失败返回None
        """
        # 如果没有提供文件名，则从URL中推导
        if file_name is None:
            # 解析URL并获取路径
            parsed_url = urlparse(file_url)
            # 获取路径的最后一部分
            file_name = parsed_url.path.split('/')[-1]
            # 如果文件名是URL编码的，进行解码
            if '%' in file_name:
                file_name = unquote(file_name)
        
        payload = self._get_common_payload()
        payload.update({
            "wcId": wcId,
            "path": file_url,
            "fileName": file_name
        })
        
        success, _ = self._make_request(
            "sendFile",
            payload,
            "发送文件消息"
            )
        return True if success else None

    def sendFileBase64(self, wcId, file_path, file_name=None):
        """
        发送Base64编码的文件消息
        Args:
            wcId: 接收消息的微信ID
            file_path: 文件的本地路径
            file_name: 文件名称，如果为None则从路径中推导
        Returns:
            bool: 发送成功返回True，失败返回None
        """
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return None
            
        # 如果没有提供文件名，则从路径中推导
        if file_name is None:
            file_name = os.path.basename(file_path)
            
        try:
            # 读取文件并转换为Base64编码
            with open(file_path, 'rb') as file:
                import base64
                file_content = file.read()
                base64_content = base64.b64encode(file_content).decode('utf-8')
                
            # 构建请求体
            payload = self._get_common_payload()
            payload.update({
                "wcId": wcId,
                "fileName": file_name,
                "base64": base64_content
            })
            
            # 发送请求
            success, _ = self._make_request(
                "sendFileBase64",
                payload,
                "发送Base64文件消息"
            )
            return True if success else None
            
        except Exception as e:
            logger.error(f"发送Base64文件消息失败: {str(e)}")
            return None

    def getMsgImg(self, msgId, content, img_type=1):
        """
        获取消息图片的URL
        Args:
            msgId: 消息ID
            content: 消息内容（XML格式的字符串）
        Returns:
            str: 成功返回图片URL，失败返回None
        """
        payload = self._get_common_payload()
        payload.update({
            "msgId": msgId,
            "content": content,
            "imgType": img_type
        })
        
        success, data = self._make_request(
            "getMsgImg",
            payload,
            "获取消息图片"
            )
            
        return data.get('url') if success and data else None

    def getMsgFile(self, msgId, content):
        """
        下载消息中的文件
        Args:
            msgId: 消息ID
            content: 消息内容（XML格式的字符串）
        Returns:
            str: 成功返回文件URL，失败返回None
        """
        payload = self._get_common_payload()
        payload.update({
            "msgId": msgId,
            "content": content
        })
        
        success, data = self._make_request(
            "getMsgFile",
            payload,
            "下载消息文件"
            )
            
        return data.get('url') if success and data else None

    def search_user_info_by_id(self, uid, need_update=False):
        """
        通过用户ID搜索用户信息
        Args:
            uid: 用户ID
        Returns:
            list: 用户信息列表，如果不存在返回空列表
        """
        if uid in self.user_info_management_dict['id_to_user_info'] and not need_update:
            return self.user_info_management_dict['id_to_user_info'][uid]
        else:
            if uid.endswith('@openim'):                
                logger.info(f"[WX] get_openim_contact {uid}")
                user_infos = self.get_openim_contact(uid)
                if user_infos:
                    user_infos = [{}]                
            else:
                user_infos = self.get_detail_info_by_ids(uid)
            if user_infos:
                self.user_info_management_dict['id_to_user_info'][uid] = user_infos
                nick_name = user_infos[0].get('nickName')
                if nick_name:
                    self.user_info_management_dict['name_to_user_info'].setdefault(nick_name, [])
                    self.user_info_management_dict['name_to_user_info'][nick_name].extend(user_infos)
                return user_infos
            return []
    def search_user_info_by_name(self, name):
        """
        通过用户昵称搜索用户信息
        Args:
            name: 用户昵称
        Returns:
            list: 用户信息列表，如果不存在返回空列表
        """
        if name in self.user_info_management_dict['name_to_user_info']:
            return self.user_info_management_dict['name_to_user_info'][name]
        return []

    def acceptUser(self, v1, v2, type=3):
        """
        接受好友请求
        Args:
            v1: 加密的用户名v1
            v2: 加密的用户名v2（ticket）
            type: 验证类型，默认为3
        Returns:
            bool: 接受成功返回True，失败返回False
        """
        payload = self._get_common_payload()
        payload.update({
            "v1": v1,
            "v2": v2,
            "type": type
        })
        
        success, _ = self._make_request(
            "acceptUser",
            payload,
            "接受好友请求"
        )
        return success
    
    def modifyGroupName(self, chatRoomId, content):
        """
        修改群聊名称
        Args:
            chatRoomId: 群聊ID
            content: 新的群聊名称
        Returns:
            bool: 修改成功返回True，失败返回False
        """
        payload = self._get_common_payload()
        payload.update({
            "chatRoomId": chatRoomId,
            "content": content
        })
        
        success, _ = self._make_request(
            "modifyGroupName",
            payload,
            "修改群聊名称"
        )
        return success
    
    def get_openim_contact(self, wcId):
        """
        获取企业微信联系人信息
        Args:
            wcId: 企业微信联系人ID
        Returns:
            dict: 成功返回联系人信息，失败返回None
        """
        payload = self._get_common_payload()
        payload.update({
            "wcId": wcId
        })
        
        success, data = self._make_request(
            "getOpenImContact",
            payload,
            "获取企业微信联系人信息"
        )
        return data if success else None

    def getChatRoomMember(self, chatRoomId):
        """
        获取群成员列表
        Args:
            chatRoomId: 群聊ID（chatRoomId）
        Returns:
            list: 成功返回群成员信息列表，失败返回空列表
        """
        payload = self._get_common_payload()
        payload.update({
            "chatRoomId": chatRoomId
        })
        success, data = self._make_request(
            "getChatRoomMember",
            payload,
            "获取群成员列表"
        )
        return data if success else []



