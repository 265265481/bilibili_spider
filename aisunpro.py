#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站视频AI总结获取
功能：根据Excel中的BV号，批量获取AI总结
"""

import requests
import hashlib
import time
import datetime
import json
import os
import re
import pandas as pd
from functools import reduce
from urllib.parse import urlencode
from openpyxl import Workbook, load_workbook
import urllib.parse
import traceback
import random
import threading

# --- 配置区域 ---
# 每次运行代码前修改这里的配置
CONFIG = {
    # ！！！请确保这个Excel文件路径是正确的！！！
    # 这个Excel文件包含要获取AI总结的BV号，BV号默认在第4列（索引为3）
    "excel_path": r"F:\Code\爬虫\1\有鱼友乐_55820229_20230701_to_20240131_视频列表.xlsx",
    "cookie_strings_pool": [
        # 第一个cookies,这里出问题最大的可能是忘加引号，忘加逗号，或者用成了中文标点符号～
        "buvid3=384BBEAA-858B-A2E9-5B83-849BC33FA9C630622infoc; b_nut=1741237430; _uuid=4BBF9EA4-1FE10-3ECA-B936-D37E18A4104B730789infoc; enable_web_push=DISABLE; buvid4=3EC2F346-3DDE-A9E7-79EC-DD96376E9C5931240-025030605-UEW7z%2Frhc9FUd5uaNwO%2FDQ%3D%3D; buvid_fp=0f85c81c4fa8403529178b71f34e4055; rpdid=0zbfVJ1vzQ|7Qh8tt0I|2lF|3w1U6854; enable_feed_channel=ENABLE; theme-tip-show=SHOWED; theme-avatar-tip-show=SHOWED; theme-switch-show=SHOWED; bp_t_offset_355987571=1087855640585437184; header_theme_version=OPEN; bp_t_offset_435641086=1092808085770076160; bili_ticket=eyJhbGciOiJIUzI1NiIsImtpZCI6InMwMyIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NTQ2MjA3MzIsImlhdCI6MTc1NDM2MTQ3MiwicGx0IjotMX0.HthfuyxINbFh1eFX5wF4oQ4exeKxXVeadrliEFJQJs4; bili_ticket_expires=1754620672; bp_t_offset_3546919328549020=1097463632750444544; CURRENT_QUALITY=0; bp_t_offset_3493111795812748=1097795796931182592; bp_t_offset_689753240=1097821227432542208; b_lsid=425B2C8D_198850230DA; bsource=search_bing; CURRENT_FNVAL=2000; SESSDATA=84e75601%2C1770130192%2Cb1350%2A82CjB1e30o40YeOrJe_Gq4umqQKooDlYCmEwpfSpk-2KDbwcU2oB8KXOiAZIG8e9khIP8SVjNDemt6ZFIwTG9FczJSUXRKaGFuWFVBOWttRnBhZW53dlVmS19DaE04ZUFQSzlTWmo0amRXSENFNTNHc2x0WTUwVnRJOUZJNVhxUEZ4d25NTWJwcGNBIIEC; bili_jct=1d36c704b2c94e559239b60e040014da; DedeUserID=3493111795812748; DedeUserID__ckMd5=387e3fa3022677d0; sid=o2emaw72; home_feed_column=4; browser_resolution=718-834",
        # 可以根据情况添加多个cookies，添加一个也行～建议使用无痕模式获取cookies，每次爬虫前都重新获取一次
    ],
    "cookie_rotate_interval_seconds": 300,  # Cookie轮换间隔，单位秒 (300秒 = 5分钟)这个时间可以自由调整

    # 处理Excel文件中的行范围（从1开始计数，None表示到文件末尾）
    "start_row": 1,  # 开始行号 (例如: 1表示第一行，2表示第二行的数据)
    "end_row": None,  # 结束行号 (例如: 10表示处理到第10行的数据)，保险起见，填50-80个，如果cookies多，填多一点也行，容易被B站制裁
}


# --- Bilibili AI 总结爬虫类 ---
class BilibiliAISummaryCrawler:
    DEFAULT_REQUEST_TIMEOUT = 30
    DEFAULT_RETRY_COUNT = 5
    DEFAULT_BACKOFF_FACTOR = 3

    def __init__(self, config):
        self.config = config

        self.cookie_strings_pool = config["cookie_strings_pool"]
        self.cookie_rotate_interval_seconds = config["cookie_rotate_interval_seconds"]
        self.current_cookie_index = 0
        self.last_cookie_change_time = time.time()
        self.cookies = {}  # requests library cookie jar

        # User-Agent池
        self.user_agent_pool = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/126.0.2592.56',
            'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.140 Mobile Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
        ]

        self.headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://www.bilibili.com/',  # 初始Referer，具体API请求中会更新
            'Origin': 'https://www.bilibili.com',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'Cookie': ''  # 初始为空，由_set_current_cookie设置
        }

        self.wbi_keys_summary = None  # 用于AI总结API
        # 确保 mixinKeyEncTab 在 __init__ 中被正确定义
        self.mixinKeyEncTab = [  # WBI签名用到的固定数组 (更新后的数组)
            46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
            33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
            61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
            36, 20, 34, 44, 52
        ]

        # 初始化时设置第一个 Cookie
        self._set_current_cookie()

        self.batch_stats = {
            'total_processed_bvids': 0,
            'ai_summary_success': 0,
            'ai_summary_no_summary': 0,  # 对应 data.code = 1 的情况
            'ai_summary_failed': 0
        }

    def _parse_cookies(self, cookie_string):
        """将Cookie字符串解析为字典"""
        cookies = {}
        for item in cookie_string.split(';'):
            if '=' in item:
                key, value = item.strip().split('=', 1)
                cookies[key] = value
        return cookies

    def _set_current_cookie(self):
        """设置当前使用的 Cookie"""
        if not self.cookie_strings_pool:
            print("❌ Cookie池为空，将无法进行Cookie轮换。")
            self.cookies = {}
            self.headers['Cookie'] = ""
            return

        cookie_string = self.cookie_strings_pool[self.current_cookie_index]
        self.cookies = self._parse_cookies(cookie_string)
        self.headers['Cookie'] = cookie_string
        self.last_cookie_change_time = time.time()
        print(f"✅ Cookie已切换至池中索引 {self.current_cookie_index} 的Cookie。")

    def _rotate_cookie_if_needed(self):
        """根据时间间隔轮换Cookie"""
        if not self.cookie_strings_pool or len(self.cookie_strings_pool) <= 1:
            return

        if (time.time() - self.last_cookie_change_time) >= self.cookie_rotate_interval_seconds:
            self.current_cookie_index = (self.current_cookie_index + 1) % len(self.cookie_strings_pool)
            self._set_current_cookie()
            print(
                f"🔄 Cookie 达到 {self.cookie_rotate_interval_seconds} 秒轮换周期，已切换到新 Cookie (索引: {self.current_cookie_index})。")

    def _make_request(self, url, method="GET", params=None, data=None, json_data=None, extra_headers=None):
        """
        发起HTTP请求，包含Cookie和User-Agent轮换，不使用代理。
        """
        self._rotate_cookie_if_needed()
        current_attempt = 0
        request_headers = self.headers.copy()

        request_headers['User-Agent'] = random.choice(self.user_agent_pool)

        if extra_headers:
            request_headers.update(extra_headers)

        while current_attempt < self.DEFAULT_RETRY_COUNT:
            print("ℹ️ 不使用代理 (使用本机IP)。")

            try:
                if method.upper() == "GET":
                    response = requests.get(
                        url,
                        headers=request_headers,
                        cookies=self.cookies,
                        params=params,
                        timeout=self.DEFAULT_REQUEST_TIMEOUT
                    )
                elif method.upper() == "POST":
                    response = requests.post(
                        url,
                        headers=request_headers,
                        cookies=self.cookies,
                        params=params,
                        data=data,
                        json=json_data,
                        timeout=self.DEFAULT_REQUEST_TIMEOUT
                    )
                else:
                    raise ValueError(f"不支持的HTTP方法: {method}")

                if response.status_code == 200:
                    return response
                elif response.status_code in [403, 412, 429, 500, 502, 503, 504]:
                    print(f"HTTP错误: {response.status_code}. 尝试重试...")
                    time.sleep(self.DEFAULT_BACKOFF_FACTOR ** current_attempt)  # 使用类属性
                else:
                    print(f"非200 HTTP状态码: {response.status_code}. 不重试。")
                    return response

            except requests.exceptions.Timeout:
                print("请求超时。尝试重试...")
                time.sleep(self.DEFAULT_BACKOFF_FACTOR ** current_attempt)
            except requests.exceptions.RequestException as e:
                print(f"请求异常: {e}. 尝试重试...")
                time.sleep(self.DEFAULT_BACKOFF_FACTOR ** current_attempt)
            except Exception as e:
                print(f"未知错误: {e}. 不重试。")
                return None

            current_attempt += 1

        print(f"❌ 达到最大重试次数，请求失败: {url}")
        return None

    def test_cookie_validity(self):
        """测试Cookie池中当前Cookie的有效性"""
        test_url = "https://api.bilibili.com/x/web-interface/nav"

        # 使用当前加载到self.cookies和self.headers['Cookie']的Cookie进行测试
        response = self._make_request(test_url)

        if response and response.status_code == 200:
            try:
                data = response.json()
                if data.get('code') == 0:
                    user_info = data.get('data', {})
                    return True, {
                        'username': user_info.get('uname', '未知'),
                        'uid': user_info.get('mid', '未知'),
                        'level': user_info.get('level_info', {}).get('current_level', 0),
                        'coins': user_info.get('money', 0),
                        'vip_status': user_info.get('vipStatus', 0)
                    }
                else:
                    return False, f"API返回错误: {data.get('message', '未知错误')} (Code: {data.get('code')})"
            except json.JSONDecodeError:
                return False, "无法解析Cookie测试API的响应为JSON。"
        else:
            status_code = response.status_code if response else 'N/A'
            return False, f"HTTP请求失败或无响应，状态码: {status_code}"

    # --- B站WBI签名算法 ---
    def get_mixin_key_for_summary(self, orig: str):

        return reduce(lambda s, i: s + orig[i], self.mixinKeyEncTab, '')[:32]

    def enc_wbi_for_summary(self, params: dict, img_key: str, sub_key: str):
        mixin_key = self.get_mixin_key_for_summary(img_key + sub_key)
        curr_time = round(time.time())
        params['wts'] = curr_time
        params = dict(sorted(params.items()))

        processed_params = {}
        for k, v in params.items():
            temp_val = str(v)

            temp_val = temp_val.replace("'", "") \
                .replace("!", "") \
                .replace("(", "") \
                .replace(")", "") \
                .replace("*", "")
            processed_params[k] = temp_val
        params = processed_params  # 将处理后的参数字典赋值回去
        query = urllib.parse.urlencode(params)
        wbi_sign = hashlib.md5((query + mixin_key).encode()).hexdigest()
        params['w_rid'] = wbi_sign
        return params

    def get_wbi_keys_for_summary(self):
        # 优化：每次只在需要时才获取 WBI 密钥，并缓存
        if hasattr(self, '_cached_wbi_keys_summary') and self._cached_wbi_keys_summary:
            return self._cached_wbi_keys_summary

        response = self._make_request(
            'https://api.bilibili.com/x/web-interface/nav'
        )  # 不再有use_proxy参数

        if response and response.status_code == 200:
            try:
                json_content = response.json()
                if json_content.get('code') == 0:
                    wbi_img = json_content['data']['wbi_img']
                    img_url: str = wbi_img['img_url']
                    sub_url: str = wbi_img['sub_url']
                    img_key = img_url.rsplit('/', 1)[1].split('.')[0]
                    sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
                    self._cached_wbi_keys_summary = (img_key, sub_key)  # 缓存密钥
                    return img_key, sub_key
                else:
                    print(
                        f"获取AI总结WBI密钥失败（API错误）: {json_content.get('message')} (Code: {json_content.get('code')})")
            except json.JSONDecodeError:
                print("获取AI总结WBI密钥响应JSON解析失败。")
        else:
            status_code = response.status_code if response else 'N/A'
            print(f"获取AI总结WBI密钥HTTP请求失败，状态码: {status_code}")

        return None, None

    # --- 获取视频信息（为了得到 CID 和 UP_MID） ---
    def get_video_info(self, bvid):
        headers = self.headers.copy()
        # Referer for basic video info API is usually just bilibili.com or space.bilibili.com
        headers['Referer'] = 'https://www.bilibili.com/'
        headers['Origin'] = 'https://www.bilibili.com'

        params = {'bvid': bvid}
        response = self._make_request('https://api.bilibili.com/x/web-interface/view', params=params,
                                      extra_headers=headers)  # 不再有use_proxy参数

        if not response or response.status_code != 200:
            print(f"获取视频 {bvid} 基础信息失败，HTTP状态码: {response.status_code if response else 'N/A'}")
            return None, None, None

        try:
            data = response.json()
            if data.get('code') == 0:
                video_data = data['data']
                cid = video_data['cid']
                owner_info = video_data['owner']
                up_mid = owner_info['mid']
                up_name = owner_info['name']
                return cid, up_mid, up_name
            else:
                print(
                    f"获取视频 {bvid} 基础信息API返回错误: {data.get('message', '未知错误')} (Code: {data.get('code')})")
                return None, None, None
        except json.JSONDecodeError:
            print(f"视频 {bvid} 基础信息响应JSON解析失败。")
            return None, None, None

    # --- 获取 AI 总结核心API请求 ---
    def get_video_summary_api(self, bvid, cid, up_mid):
        headers_summary = self.headers.copy()  # headers已包含User-Agent和当前Cookie
        headers_summary['Referer'] = f'https://www.bilibili.com/video/{bvid}'
        headers_summary['Origin'] = 'https://www.bilibili.com'

        params = {
            'bvid': bvid,
            'cid': cid,
            'up_mid': up_mid,
            'web_location': '333.788',
        }

        img_key, sub_key = self.get_wbi_keys_for_summary()
        if not img_key or not sub_key:
            # 返回一个明确的错误字典，以供get_ai_summary_for_bvid处理
            return {'code': -999, 'message': '无法获取AI总结WBI密钥'}

        signed_params = self.enc_wbi_for_summary(
            params=params,
            img_key=img_key,
            sub_key=sub_key,
        )

        response = self._make_request(
            'https://api.bilibili.com/x/web-interface/view/conclusion/get',
            method="GET",
            params=signed_params,
            extra_headers=headers_summary
        )

        if not response or response.status_code != 200:
            http_status_code = response.status_code if response else 'N/A'
            print(f"获取AI总结HTTP请求失败: {http_status_code}")
            # 返回一个明确的错误字典
            return {'code': -998, 'message': f'HTTP请求失败: {http_status_code}'}

        try:
            return response.json()
        except json.JSONDecodeError:
            print("AI总结响应JSON解析失败。")

            return {'code': -997, 'message': 'AI总结JSON解析失败'}

    # --- 获取 AI 总结结果并处理 ---
    def get_ai_summary_for_bvid(self, bvid, up_name="未知UP主"):
        print(f"\n--- 正在处理BV号: {bvid} ---")

        current_bvid_result = {
            'BV号': bvid,
            'AI总结': '',
            'AI要点个数': 0,
            'AI要点': '',
            '喜欢': 0,
            '不喜欢': 0,
            '状态码': 'N/A',
            'result_type': 'N/A',
            'stid': 'N/A',
            'stidstr': 'N/A'
        }

        try:
            print("🔍 获取视频基本信息 (用于AI总结的CID和UP_MID)...")
            cid, up_mid, _ = self.get_video_info(bvid)

            if not cid or not up_mid:
                print(f"❌ 无法获取视频 {bvid} 的 CID 或 UP_MID。")
                current_bvid_result.update({
                    'AI总结': '无法获取视频CID/UP_MID',
                    '状态码': -996,
                    'result_type': 0,
                    'stidstr': 'N/A'
                })
                self.batch_stats['ai_summary_failed'] += 1
                return current_bvid_result

            print(f"✅ CID: {cid}, UP主ID: {up_mid}")
            time.sleep(3)  # 短暂延时

            print("🔍 获取AI总结内容...")
            summary_response = self.get_video_summary_api(bvid, cid, up_mid)

            response_code = summary_response.get('code')
            data_content = summary_response.get('data', {})
            model_result = data_content.get('model_result', {})
            summary_text = model_result.get('summary', '')
            result_type_val = data_content.get('result_type', model_result.get('result_type',
                                                                               0))  # result_type可能在data层级或model_result层级
            dislike = data_content.get('dislike_num', 0)
            like = data_content.get('like_num', 0)
            stid = data_content.get('stid', 'N/A')

            print(f"ℹ️ data.stid: {stid}")
            current_bvid_result['stid'] = stid

            # 根据API文档计算 stidstr
            calculated_stidstr = 'N/A'
            if response_code == 0:  # 只有外层code为0时，internal_data_code和stidstr才有意义
                internal_data_code = data_content.get('code')
                if internal_data_code == 1:
                    if stid == '0':
                        calculated_stidstr = 0  # code=1, stid=0 -> 未入队处理
                    elif stid == '':  # API文档说的是空，所以判断空字符串
                        calculated_stidstr = 1  # code=1, stid为空 -> 语音未识别
                    elif stid == 'N/A' and data_content.get('message', '') == '无摘要（未识别到语音）':
                        # 这种情况通常是stid字段缺失，但message明确说明语音未识别
                        calculated_stidstr = 1
            current_bvid_result['stidstr'] = calculated_stidstr  # 存储计算后的stidstr

            if response_code == 0:  # 外层API请求成功 (HTTP 200, 且 B站返回 code 0)
                internal_data_code = data_content.get('code')  # B站内部业务状态码

                if internal_data_code == 0:  # 内层也成功，表示有摘要
                    point_count = 0
                    outline_text_list = []
                    if model_result.get('outline'):
                        for section in model_result['outline']:
                            outline_text_list.append(f"章节: {section.get('title', '无标题')}")
                            if 'part_outline' in section:
                                for point in section['part_outline']:
                                    point_count += 1
                                    timestamp_sec = point['timestamp']
                                    timestamp_str = f"{timestamp_sec // 60:02d}:{timestamp_sec % 60:02d}"
                                    point_text = f"{point_count}. [{timestamp_str}] {point['content']}"
                                    outline_text_list.append(point_text)

                    final_outline_text = "\n".join(outline_text_list)
                    print(f"📊 共提取到 {point_count} 个AI要点。")
                    print("-" * 40)
                    print(f"📝 AI总结: {summary_text[:100]}..." if summary_text else "📝 AI总结: (空)")
                    print(f"👍 喜欢: {like}    👎 不喜欢: {dislike}")
                    print("-" * 40)
                    current_bvid_result.update({
                        'AI总结': summary_text,
                        'AI要点个数': point_count,
                        'AI要点': final_outline_text,
                        '喜欢': like,
                        '不喜欢': dislike,
                        '状态码': internal_data_code,  # 使用 data.code 的值 (即 0)
                        'result_type': result_type_val
                    })
                    self.batch_stats['ai_summary_success'] += 1
                    print("✅ 处理完成")
                    return current_bvid_result

                elif internal_data_code == 1:  # 内层code=1，无摘要（未识别到语音）
                    error_message = summary_response.get('message', '无摘要（未识别到语音）')
                    print(
                        f"⚠️ 该视频没有AI总结：{error_message} (Data.Code: {internal_data_code}, ResultType: {result_type_val})")
                    current_bvid_result.update({
                        'AI总结': "无AI总结 (未识别到语音)",  # 明确提示
                        'AI要点个数': 0, 'AI要点': "",
                        '喜欢': 0, '不喜欢': 0,
                        '状态码': internal_data_code,  # 使用 data.code 的值 (即 1)
                        'result_type': result_type_val
                    })
                    self.batch_stats['ai_summary_no_summary'] += 1
                    return current_bvid_result  # 返回结果，以便保存

                elif internal_data_code == -1:  # 内层code=-1，不支持AI摘要（敏感内容等）或其他因素
                    error_message = summary_response.get('message', '不支持AI摘要或请求异常')
                    print(
                        f"❌ 获取失败：{error_message} (Data.Code: {internal_data_code}, ResultType: {result_type_val})")
                    print("🤔 可能是视频不支持AI总结，或触发了反爬限制。")
                    current_bvid_result.update({
                        'AI总结': f"不支持AI总结/请求异常: ({error_message})",
                        'AI要点个数': 0, 'AI要点': "",
                        '喜欢': 0, '不喜欢': 0,
                        '状态码': internal_data_code,  # 使用 data.code 的值 (即 -1)
                        'result_type': result_type_val
                    })
                    self.batch_stats['ai_summary_failed'] += 1
                    return current_bvid_result  # 返回失败结果，以便记录

                else:  # 外层code=0但内层data.code是其他未知情况
                    error_message = summary_response.get('message', '未知API错误')
                    print(
                        f"❌ 处理失败: {error_message} (Data.Code: {internal_data_code}, ResultType: {result_type_val})")
                    print(f"完整响应: {json.dumps(summary_response, ensure_ascii=False, indent=2)}")
                    current_bvid_result.update({
                        'AI总结': f"获取失败: {error_message}",
                        'AI要点个数': 0, 'AI要点': "",
                        '喜欢': 0, '不喜欢': 0,
                        '状态码': internal_data_code,  # 使用 data.code 的值
                        'result_type': result_type_val
                    })
                    self.batch_stats['ai_summary_failed'] += 1
                    return current_bvid_result  # 返回失败结果，以便记录

            # 以下是外层API请求失败的情况 (response_code != 0)
            elif response_code == -101:  # 账号未登录
                error_message = summary_response.get('message', '账号未登录或Cookie失效')
                print(f"❌ 获取失败：{error_message} (Code: {response_code})")
                print("🚨 警告：Cookie可能已失效，请尽快更新！后续AI总结请求可能也会失败。")
                current_bvid_result.update({
                    'AI总结': f"获取失败: Cookie失效 ({error_message})",
                    'AI要点个数': 0, 'AI要点': "",
                    '喜欢': 0, '不喜欢': 0,
                    '状态码': response_code,  # 外部错误码
                    'result_type': result_type_val
                })
                self.batch_stats['ai_summary_failed'] += 1
                return current_bvid_result

            elif response_code in [-400, -403]:  # 请求错误、访问权限不足
                error_message = summary_response.get('message', '请求错误或权限不足')
                print(f"❌ 获取失败：{error_message} (Code: {response_code})")
                current_bvid_result.update({
                    'AI总结': f"获取失败: {error_message}",
                    'AI要点个数': 0, 'AI要点': "",
                    '喜欢': 0, '不喜欢': 0,
                    '状态码': response_code,  # 外部错误码
                    'result_type': result_type_val
                })
                self.batch_stats['ai_summary_failed'] += 1
                return current_bvid_result

            else:  # 其他未知外层错误码
                error_message = summary_response.get('message', '未知API错误')
                print(f"❌ 处理失败: {error_message} (Code: {response_code}, ResultType: {result_type_val})")
                print(f"完整响应: {json.dumps(summary_response, ensure_ascii=False, indent=2)}")
                current_bvid_result.update({
                    'AI总结': f"获取失败: {error_message}",
                    'AI要点个数': 0, 'AI要点': "",
                    '喜欢': 0, '不喜欢': 0,
                    '状态码': response_code,  # 外部错误码
                    'result_type': result_type_val
                })
                self.batch_stats['ai_summary_failed'] += 1
                return current_bvid_result

        except Exception as e:
            print(f"❌ 处理 {bvid} 时发生意外错误: {str(e)}")
            print(traceback.format_exc())
            current_bvid_result.update({
                'AI总结': f"代码执行异常: {str(e)}",
                'AI要点个数': 0, 'AI要点': "",
                '喜欢': 0, '不喜欢': 0,
                '状态码': -999,  # 内部代码执行异常
                'result_type': 0,
                'stidstr': 'N/A'  # 异常情况下，stidstr无意义
            })
            self.batch_stats['ai_summary_failed'] += 1
            return current_bvid_result

        finally:
            self.batch_stats['total_processed_bvids'] += 1


# --- 文件读写与工具函数（独立于类） ---
def sanitize_filename(name):
    """移除文件名中的非法字符"""
    return re.sub(r'[\\/*?:"<>|]', "", name)


def read_bvids_from_excel(file_path, start_row=1, end_row=None):
    try:
        if not os.path.exists(file_path):
            print(f"❌ 错误: '{file_path}' 文件不存在!")
            return []
        print(f"📊 正在读取Excel文件: {file_path}")
        df = pd.read_excel(file_path)

        # Excel行号转为DataFrame索引（DataFrame索引从0开始，且不含表头）
        # 假设第一行是表头
        df_start_idx = max(0, start_row - 2)
        if end_row is None:
            df_end_idx = df.shape[0]  # 到DataFrame末尾
        else:
            df_end_idx = min(df.shape[0], end_row - 1)  # Excel行号减1是DataFrame的索引

        # ⚠️⚠️⚠️ BV号在第四列（索引为3）的修改已应用 ⚠️⚠️⚠️
        if df.shape[1] < 3:  # BV号在第四列，所以至少需要4列
            print("❌ 错误: Excel文件列数不足4列，无法读取BV号。")
            return []

        # 确保切片索引有效
        if df_start_idx >= df_end_idx and df_end_idx > 0:
            print(f"⚠️ 指定的行范围 [{start_row}:{end_row}] 在Excel数据中无效或为空。")
            return []
        elif df_start_idx >= df.shape[0]:
            print(f"⚠️ 指定的开始行 {start_row} 超出Excel数据总行数。")
            return []

        selected_bvids_series = df.iloc[df_start_idx:df_end_idx, 2]  # 索引3是第四列!!!!!!!!!!!!!!!!!!!!!!!!

        bvids = selected_bvids_series.tolist()
        # 移除空值和只含空格的字符串
        bvids = [str(bv).strip() for bv in bvids if pd.notna(bv) and str(bv).strip()]

        print(
            f"✅ 成功从Excel行 [{start_row}:{end_row if end_row is not None else df.shape[0] + 1}] 读取到 {len(bvids)} 个BV号。")
        return bvids
    except Exception as e:
        print(f"❌ 读取Excel文件失败: {str(e)}")
        return []


def write_results_to_excel(df: pd.DataFrame, file_path: str):
    """将DataFrame写入Excel文件"""
    try:
        df.to_excel(file_path, index=False)
        print(f"✅ 结果已更新到 '{file_path}'")
    except Exception as e:
        print(f"❌ 写入Excel出错: {str(e)}")


# --- 主程序执行逻辑 ---
def main():
    for i in range(2):
        print("=" * 60)
        print("🎬 哔哩哔哩视频AI总结批量获取工具 (独立版) 🎬")
        print("=" * 60)

        # 检查配置
        if not CONFIG['cookie_strings_pool'] or not any(c for c in CONFIG['cookie_strings_pool']):
            print("❌ 请在CONFIG字典中设置至少一个有效的Cookie字符串到 'cookie_strings_pool'!")
            return
        if not CONFIG['excel_path']:
            print("❌ 请在CONFIG字典中设置你的excel文件路径!")
            return

        print("\n--- 配置信息 ---")
        for key, value in CONFIG.items():
            if key == 'cookie_strings_pool':
                print(f"  {key}: 已配置 {len(value)} 个Cookie")
            else:
                print(f"  {key}: {value}")
        print("------------------\n")

        crawler = BilibiliAISummaryCrawler(CONFIG)

        # 重要的Cookie有效性测试
        print("\n🚀 正在测试Cookie有效性 (使用池中第一个Cookie)...")
        is_valid_cookie, cookie_check_info = crawler.test_cookie_validity()

        if not is_valid_cookie:
            print(f"❌ 第一个Cookie无效或无法连接到B站API: {cookie_check_info}")
            print("请检查您的网络连接或更新 'cookie_strings_pool' 中的Cookie字符串。程序将退出。")
            return
        else:
            print(
                f"✅ Cookie有效！当前登录用户: {cookie_check_info.get('username', '未知')} (UID: {cookie_check_info.get('uid', '未知')})")

        print(
            f"\n📊 正在读取BV号列表从 {CONFIG['excel_path']} (行范围: {CONFIG['start_row']} 到 {CONFIG['end_row'] if CONFIG['end_row'] is not None else '末尾'})...")
        bvids = read_bvids_from_excel(CONFIG['excel_path'], CONFIG['start_row'], CONFIG['end_row'])

        if not bvids:
            print("❌ 没有找到有效的BV号在指定范围内可处理！")
            return

        print(f"✅ 成功读取到 {len(bvids)} 个BV号进行处理。")
        if bvids:
            print(f"DEBUG: 待处理的第一个BV号是: {bvids[0]}")

        # --- 动态生成输出文件名 ---
        if i == 0:
            output_filename_base = os.path.splitext(os.path.basename(CONFIG['excel_path']))[0]

            output_filename = f"F:\Code\爬虫/{output_filename_base}_AI总结_rows_{CONFIG['start_row']}_to_{CONFIG['end_row'] if CONFIG['end_row'] is not None else 'end'}.xlsx"
            print(f"✅ AI总结结果将保存到文件: {output_filename}")
        if i == 1:
            output_filename_base = os.path.splitext(os.path.basename(CONFIG['excel_path']))[0]

            output_filename = f"F:\Code\爬虫/{output_filename_base}_有效AI总结_rows_{CONFIG['start_row']}_to_{CONFIG['end_row'] if CONFIG['end_row'] is not None else 'end'}.xlsx"
            print(f"✅ AI总结结果将保存到文件: {output_filename}")

            # --- 断点续传逻辑，适配保存所有结果 (包括 data.code=1) ---
        processed_bvids_in_excel = set()  # 记录Excel中已有的BV号
        results_list_for_df = []  # 存储本次运行及历史运行的所有结果
        if os.path.exists(output_filename):
            print(f"📂 发现已存在的输出文件 '{output_filename}'，将尝试读取历史结果。")
            try:
                done_df = pd.read_excel(output_filename)
                if 'BV号' in done_df.columns:
                    processed_bvids_in_excel = set(done_df['BV号'].tolist())
                    results_list_for_df = done_df.to_dict('records')
                    print(f"👍 已加载 {len(results_list_for_df)} 条历史结果。")
                else:
                    print("⚠️ 历史文件缺少'BV号'列，将创建新文件。")
            except Exception as e:
                print(f"⚠️ 读取历史文件失败: {e}。将创建新文件。")
            finally:
                if not results_list_for_df:
                    processed_bvids_in_excel = set()

        remaining_bvids = [bvid for bvid in bvids if bvid not in processed_bvids_in_excel]
        if not remaining_bvids:
            print("\n🎉 所有指定范围内的BV号AI总结均已处理完成或已存在！")
            return

        print(f"📝 剩下 {len(remaining_bvids)} 个新BV号待处理AI总结。")

        print(f"⏳ 单次请求超时时间: {BilibiliAISummaryCrawler.DEFAULT_REQUEST_TIMEOUT} 秒")
        print(f"⏳ API请求重试次数: {BilibiliAISummaryCrawler.DEFAULT_RETRY_COUNT} 次")
        print(f"⏳ API请求重试间隔因子: {BilibiliAISummaryCrawler.DEFAULT_BACKOFF_FACTOR}")

        for i, bvid in enumerate(remaining_bvids, 1):
            print(f"\n--- 进度: [{i}/{len(remaining_bvids)}] ---")
            current_result = crawler.get_ai_summary_for_bvid(bvid)

            results_list_for_df.append(current_result)
            print("💾 正在保存当前处理结果...")
            all_columns_to_save = ['BV号', 'AI总结', 'AI要点个数', 'AI要点', '喜欢', '不喜欢', '状态码', 'result_type',
                                   'stid', 'stidstr']
            temp_df = pd.DataFrame(results_list_for_df, columns=all_columns_to_save)
            write_results_to_excel(temp_df, output_filename)

            DEFAULT_AI_SUMMARY_VIDEO_SLEEP = 10
            print(f"\n⏳ 等待 {DEFAULT_AI_SUMMARY_VIDEO_SLEEP} 秒后继续下一个视频...")
            time.sleep(DEFAULT_AI_SUMMARY_VIDEO_SLEEP)

        print("\n✨ 所有指定BV号的AI总结处理完成 ✨")
        print("\n--- 最终处理报告 ---")
        print(f"总尝试处理BV号数: {crawler.batch_stats['total_processed_bvids']}")
        print(f"AI总结成功获取并已保存: {crawler.batch_stats['ai_summary_success']}")
        print(f"AI总结无摘要 (B站返回 Data.Code 1): {crawler.batch_stats['ai_summary_no_summary']}")
        print(f"AI总结获取失败 (外部Code -101, -400等或内部Data.Code -1等): {crawler.batch_stats['ai_summary_failed']}")
        print("--------------------\n")


if __name__ == "__main__":
    main()