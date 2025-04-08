import urllib.request
import re
import sys
from subprocess import call
import json
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from queue import Queue
import time
import logging
from datetime import datetime
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
import qrcode_terminal
import hashlib
import requests
import io
import qrcode
from PIL import ImageTk, Image


class Bili_fav:

    video_ids = []
    video_titles = []

    # get url address 获取收藏夹地址
    def __init__(self, user_id, favorites_id):
        # 更新API地址
        self.favurl = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={favorites_id}&pn={{page}}&ps=20&keyword=&order=mtime&type=0&tid=0&platform=web"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.bilibili.com'
        }
        self.paused = False
        self.cancelled = False
        self.current_downloads = {}  # 记录当前正在下载的视频 {thread_id: video_id}
        
        # 设置日志
        self.setup_logger()

        # 添加线程池
        self.format_pool = ThreadPoolExecutor(max_workers=3)

        # 确保config目录存在
        if not os.path.exists('config'):
            os.makedirs('config')
            
        # 文件路径
        self.you_get_path = 'you-get'
        self.cookies_file = os.path.join('config', 'cookies.txt')
        self.config_file = os.path.join('config', 'config.json')
        self.formats_cache_file = os.path.join('config', 'formats_cache.json')  # 添加格式缓存文件
        
        # 加载格式缓存
        self.formats_cache = self.load_formats_cache()
        
        # 初始化GUI回调
        self.gui_callback = None

    def setup_logger(self):
        """设置日志记录器"""
        # 创建logs目录（如果不存在）
        logs_dir = os.path.join('config', 'logs')
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
            
        # 创建日志文件名（使用当前时间）
        log_filename = os.path.join(logs_dir, f'download_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        
        # 配置日志记录器
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filename, encoding='utf-8'),
                logging.StreamHandler()  # 同时输出到控制台
            ]
        )
        self.logger = logging.getLogger(__name__)

    def login(self, sessdata, bili_jct, buvid3):
        """
        使用Cookie登录
        :param sessdata: Cookie中的SESSDATA值
        :param bili_jct: Cookie中的bili_jct值
        :param buvid3: Cookie中的buvid3值
        """
        self.headers['Cookie'] = f'SESSDATA={sessdata}; bili_jct={bili_jct}; buvid3={buvid3}'
        
        # 验证登录状态
        try:
            nav_url = 'https://api.bilibili.com/x/web-interface/nav'
            request = urllib.request.Request(nav_url, headers=self.headers)
            response = urllib.request.urlopen(request)
            content = response.read().decode('utf-8')
            user_info = json.loads(content)
            
            if user_info['code'] == 0:
                print(f"登录成功！用户名：{user_info['data']['uname']}")
                return True
            else:
                print("登录失败，请检查Cookie信息")
                return False
        except Exception as e:
            print(f"登录验证出错：{str(e)}")
            return False

    # load videos addresses 读取视频地址
    def load_favorites(self):
        """加载收藏夹内容"""
        try:
            # 检查必要参数
            user_id = self.user_id.get().strip()
            favorites_id = self.favorites_id.get().strip()
            
            if not user_id or not favorites_id:
                raise ValueError("请填写用户ID和收藏夹ID")
            
            # 读取cookie信息
            if not os.path.exists(self.cookies_file):
                raise ValueError("请先登录")
                
            with open(self.cookies_file, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            
            # 构建请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Cookie': f"SESSDATA={cookies['SESSDATA']}; bili_jct={cookies['bili_jct']}; buvid3={cookies['buvid3']}"
            }
            
            # 获取收藏夹内容
            page = 1
            self.video_ids = []
            self.video_titles = []
            
            while True:
                url = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={favorites_id}&pn={page}&ps=20&keyword=&order=mtime&type=0&tid=0&platform=web"
                request = urllib.request.Request(url, headers=headers)
                response = urllib.request.urlopen(request)
                content = json.loads(response.read().decode('utf-8'))
                
                if content['code'] != 0:
                    raise ValueError(f"获取收藏夹内容失败：{content['message']}")
                
                medias = content['data']['medias']
                if not medias:
                    break
                    
                for media in medias:
                    self.video_ids.append(media['bvid'])
                    self.video_titles.append(media['title'])
                
                if len(medias) < 20:
                    break
                    
                page += 1
            
            if not self.video_ids:
                raise ValueError("收藏夹为空")
                
            print(f"共找到 {len(self.video_ids)} 个视频")
            return True
            
        except Exception as e:
            messagebox.showerror("错误", str(e))
            return False

    def check_downloaded_videos(self, output_dir):
        """检查视频是否已经下载过"""
        downloaded = []
        try:
            # 获取输出目录中的所有文件
            files = os.listdir(output_dir)
            # 遍历所有视频ID和标题
            for i, (video_id, title) in enumerate(zip(self.video_ids, self.video_titles)):
                # 移除标题中的特殊字符，因为文件名不能包含这些字符
                safe_title = re.sub(r'[\\/:*?"<>|]', '', title)
                # 检查是否存在以此标题开头的文件
                for file in files:
                    if file.startswith(safe_title):
                        downloaded.append(video_id)
                        print(f"视频已存在：{title}")
                        break
            return downloaded
        except Exception as e:
            print(f"检查已下载视频时出错：{str(e)}")
            return []
    
    # 下载视频
    def download_videos(self, output_dir = '', max_workers = 1):
        """下载视频（已废弃，使用新的下载队列机制）"""
        pass

    def _clean_incomplete_files(self, output_dir, title):
        """清理不完整的下载文件"""
        try:
            # 处理文件名，移除非法字符
            safe_title = re.sub(r'[\\/:*?"<>|]', '', title)
            for filename in os.listdir(output_dir):
                # 使用处理后的标题进行匹配
                if safe_title in filename and os.path.isfile(os.path.join(output_dir, filename)):
                    filepath = os.path.join(output_dir, filename)
                    os.remove(filepath)
                    self.logger.info(f"已删除不完整文件：{filename}")
        except Exception as e:
            self.logger.error(f"清理文件失败：{str(e)}")

    def _verify_download(self, output_dir, title):
        """验证下载文件的完整性"""
        try:
            # 处理文件名，移除非法字符
            safe_title = re.sub(r'[\\/:*?"<>|]', '', title)
            # 检查是否存在视频文件
            files = os.listdir(output_dir)
            video_files = [f for f in files if safe_title in f and f.endswith(('.flv', '.mp4'))]
            if not video_files:
                return False
            
            # 检查文件大小是否大于1KB
            video_path = os.path.join(output_dir, video_files[0])
            if os.path.getsize(video_path) < 1024:
                return False
            
            return True
        except:
            return False

    def _get_dir_size(self, path):
        """获取目录大小"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        return total_size

    def _monitor_download_progress(self, index, video_id, output_dir, initial_size, start_time):
        """监控下载进度（已废弃，使用新的进度监控机制）"""
        pass

    def _format_size(self, size):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

    def pause_download(self, video_id=None):
        """暂停下载（已废弃，使用新的暂停机制）"""
        pass

    def resume_download(self, video_id=None):
        """继续下载（已废弃，使用新的继续机制）"""
        pass

    def cancel_download(self, video_id=None):
        """取消下载（已废弃，使用新的取消机制）"""
        pass

    def download_video(self, video_id, title, index, output_dir, you_get_path, cookies_file):
        """下载单个视频"""
        try:
            # 处理文件名，移除非法字符
            safe_title = re.sub(r'[\\/:*?"<>|]', '', title)
            self.logger.info(f"开始下载第{index}个视频：{safe_title}")
            video_url = f"https://www.bilibili.com/video/{video_id}"
            self.logger.info(f"视频地址：{video_url}")
            
            # 删除已存在的不完整文件
            self._clean_incomplete_files(output_dir, safe_title)
            
            download_success = False
            # 先获取可用的格式信息
            info_cmd = f'"{you_get_path}" --info -c "{cookies_file}" "{video_url}"'
            self.logger.info(f"执行命令：{info_cmd}")
            info_process = subprocess.run(info_cmd, shell=True, capture_output=True, text=True, encoding='utf-8')
            
            # 解析输出获取可用格式
            formats = []
            if info_process.returncode == 0:
                output = info_process.stdout
                self.logger.info(f"可用格式信息：\n{output}")
                
                current_format = None
                has_size = False
                
                for line in output.split('\n'):
                    if '- format:' in line:
                        # 如果之前的格式有大小信息，则添加到列表中
                        if current_format and has_size:
                            formats.append(current_format)
                            self.logger.info(f"添加可用格式：{current_format}")
                        
                        current_format = line.split('format:')[1].strip()
                        has_size = False
                        self.logger.info(f"开始检查格式：{current_format}")
                    elif 'size:' in line and current_format:
                        has_size = True
                        self.logger.info(f"格式 {current_format} 找到大小信息")
                
                # 处理最后一个格式
                if current_format and has_size:
                    formats.append(current_format)
                    self.logger.info(f"添加最后一个可用格式：{current_format}")
                
                # 按照分辨率和编码排序
                def get_quality_score(fmt):
                    # 分辨率优先级（最高权重）
                    resolution_score = 0
                    if any(x in fmt for x in ['1080', 'flv-AV1', 'flv-HEVC', 'flv-AVC']): 
                        resolution_score = 3000  # 识别无数字的1080P格式
                    elif '720' in fmt: resolution_score = 2000
                    elif '480' in fmt: resolution_score = 1000
                    else: resolution_score = 0
                    
                    # 编码优先级（次要权重）
                    codec_score = 0
                    if 'AVC' in fmt: codec_score = 3
                    elif 'HEVC' in fmt: codec_score = 2
                    elif 'AV1' in fmt: codec_score = 1
                    
                    score = resolution_score + codec_score
                    self.logger.info(f"格式 {fmt} 的得分：{score} (分辨率：{resolution_score}, 编码：{codec_score})")
                    return score
                
                formats.sort(key=get_quality_score, reverse=True)
                self.logger.info(f"按优先级排序后的格式列表：{formats}")
            
            if not formats:
                formats = ['dash-flv720-AVC', 'dash-flv480-AVC', 'dash-flv360-AVC']
            else:
                formats = formats[:3]  # 只取前三个最高质量的格式
            
            self.logger.info(f"将尝试以下格式：{formats}")
            
            for fmt in formats:
                for attempt in range(3):
                    try:
                        self.logger.info(f"尝试下载格式：{fmt}，第{attempt+1}次尝试")
                        
                        cmd = f'"{you_get_path}" --debug --format={fmt} --no-caption -c "{cookies_file}" -o "{output_dir}" "{video_url}"'
                        self.logger.info(f"执行命令：{cmd}")
                        
                        # 使用Popen而不是run，以便可以控制进程
                        process = subprocess.Popen(
                            cmd, 
                            shell=True, 
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=False  # 使用二进制模式
                        )
                        
                        # 记录当前下载的进程
                        self.current_downloads[threading.get_ident()] = video_id
                        
                        # 监控下载进度
                        while True:
                            # 检查是否被取消
                            if self.cancelled:
                                process.terminate()
                                self.logger.info(f"下载被取消：{safe_title}")
                                break
                            
                            # 检查是否被暂停
                            if self.paused:
                                time.sleep(1)  # 暂停时等待
                                continue
                            
                            # 检查进程是否结束
                            if process.poll() is not None:
                                break
                            
                            # 读取输出
                            try:
                                line = process.stdout.readline()
                                if line:
                                    line = line.decode('utf-8', errors='ignore')
                                    # 解析进度信息
                                    if '%' in line:
                                        progress_match = re.search(r'(\d+\.?\d*)%', line)
                                        if progress_match:
                                            progress = progress_match.group(1)
                                            speed_match = re.search(r'(\d+\.?\d*\s*[KMG]?B/s)', line)
                                            speed = speed_match.group(1) if speed_match else "0B/s"
                                            if hasattr(self, 'gui_callback'):
                                                self.gui_callback('update_status', index, "下载中", f"{progress}%", speed)
                            except:
                                pass
                            
                            time.sleep(0.1)  # 避免CPU占用过高
                        
                        # 检查下载结果
                        if process.returncode == 0 and self._verify_download(output_dir, safe_title):
                            download_success = True
                            self.logger.info(f"视频 {safe_title} 下载成功")
                            break
                        else:
                            # 尝试解码错误信息，忽略无法解码的部分
                            try:
                                error_msg = process.stderr.decode('utf-8', errors='ignore') if process.stderr else process.stdout.decode('utf-8', errors='ignore')
                            except:
                                error_msg = "无法解码的错误信息"
                            self.logger.error(f"下载失败，错误信息：\n{error_msg}")
                            self._clean_incomplete_files(output_dir, safe_title)
                        
                    except Exception as e:
                        self.logger.error(f"下载出错：{str(e)}")
                        self._clean_incomplete_files(output_dir, safe_title)
                    
                    if download_success:
                        break
                
            if not download_success:
                self.logger.error(f"视频 {safe_title} 所有格式下载尝试均失败")
                if hasattr(self, 'gui_callback'):
                    self.gui_callback('update_status', index, "下载失败", "0%", "0B/s")
            else:
                if hasattr(self, 'gui_callback'):
                    self.gui_callback('update_status', index, "已完成", "100%", "0B/s")
            
        except Exception as e:
            self.logger.error(f"下载过程出错：{str(e)}", exc_info=True)
            if hasattr(self, 'gui_callback'):
                self.gui_callback('update_status', index, "出错", str(e), "0B/s")
        finally:
            # 清理当前下载记录
            if threading.get_ident() in self.current_downloads:
                del self.current_downloads[threading.get_ident()]

    def get_fav_list(self, fav_id):
        """获取收藏夹视频列表"""
        try:
            url = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={fav_id}&pn=1&ps=20&keyword=&order=mtime&type=0&tid=0&platform=web"
            request = urllib.request.Request(url, headers=self.headers)
            response = urllib.request.urlopen(request)
            content = response.read().decode('utf-8')
            
            data = json.loads(content)
            if data['code'] != 0:
                self.logger.error(f"获取收藏夹列表失败：{data['message']}")
                return []
                
            videos = []
            for item in data['data']['medias']:
                videos.append((item['bvid'], item['title']))
            return videos
            
        except Exception as e:
            self.logger.error(f"获取或解析收藏夹列表失败：{str(e)}")
            return []

    def load_formats_cache(self):
        """加载格式缓存"""
        try:
            if os.path.exists(self.formats_cache_file):
                with open(self.formats_cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            self.logger.error(f"加载格式缓存失败：{str(e)}")
            return {}

    def save_formats_cache(self):
        """保存格式缓存"""
        try:
            with open(self.formats_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.formats_cache, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.logger.error(f"保存格式缓存失败：{str(e)}")

    def get_video_formats(self, video_id):
        """获取视频的可用格式"""
        # 先检查缓存
        if video_id in self.formats_cache:
            cache_data = self.formats_cache[video_id]
            cache_time = cache_data.get('time', 0)
            # 缓存有效期为24小时
            if time.time() - cache_time < 24 * 60 * 60:
                self.logger.info(f"使用缓存的格式信息：{video_id}")
                return cache_data['formats']
        
        video_url = f"https://www.bilibili.com/video/{video_id}"
        info_cmd = f'"{self.you_get_path}" --info -c "{self.cookies_file}" "{video_url}"'
        
        try:
            self.logger.info(f"获取视频格式信息：{video_url}")
            process = subprocess.run(
                info_cmd, 
                shell=True, 
                capture_output=True, 
                text=True, 
                encoding='utf-8',
                errors='replace'
            )
            
            if process.returncode == 0:
                self.logger.debug(f"you-get输出：\n{process.stdout}")
                formats = []
                current_format = None
                
                for line in process.stdout.split('\n'):
                    if '- format:' in line:
                        current_format = line.split('format:')[1].strip()
                    elif 'quality:' in line and current_format:
                        quality = line.split('quality:')[1].strip()
                        formats.append(f"{quality} ({current_format})")
                
                if formats:
                    self.logger.info(f"找到以下格式：{formats}")
                    # 更新缓存
                    self.formats_cache[video_id] = {
                        'formats': formats,
                        'time': time.time()
                    }
                    self.save_formats_cache()
                    return formats
                else:
                    self.logger.warning("未找到任何可用格式")
                    return ["获取格式失败"]
            
            self.logger.error(f"获取格式失败，you-get返回：{process.stderr}")
            return ["获取格式失败"]
        except Exception as e:
            self.logger.error(f"获取格式出错：{str(e)}")
            return ["获取格式失败"]

    def tvsign(self, params, appkey='4409e2ce8ffd12b8', appsec='59b43e04ad6965f34319062b478f83dd'):
        '''为请求参数进行 api 签名'''
        params.update({'appkey': appkey})
        params = dict(sorted(params.items())) # 重排序参数 key
        query = urllib.parse.urlencode(params) # 序列化参数
        sign = hashlib.md5((query+appsec).encode()).hexdigest() # 计算 api 签名
        params.update({'sign':sign})
        return params

    def qrcode_login(self):
        """使用二维码方式登录B站"""
        try:
            # 获取二维码
            loginInfo = requests.post('https://passport.bilibili.com/x/passport-tv-login/qrcode/auth_code',
                params=self.tvsign({
                    'local_id':'0',
                    'ts':int(time.time())
                }),
                headers={
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }).json()

            if loginInfo['code'] != 0:
                raise Exception(f"获取二维码失败：{loginInfo['message']}")

            # 生成二维码
            print("请扫描二维码登录:")
            qrcode_terminal.draw(loginInfo['data']['url'])

            # 如果有GUI回调，显示二维码
            if hasattr(self, 'gui_callback') and self.gui_callback:
                self.gui_callback('show_qrcode', loginInfo['data']['url'])

            # 轮询扫码结果
            while True:
                pollInfo = requests.post('https://passport.bilibili.com/x/passport-tv-login/qrcode/poll',
                    params=self.tvsign({
                        'auth_code':loginInfo['data']['auth_code'],
                        'local_id':'0',
                        'ts':int(time.time())
                    }),
                    headers={
                        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    }).json()
                
                if pollInfo['code'] == 0:
                    loginData = pollInfo['data']
                    break
                    
                elif pollInfo['code'] == -3:
                    raise Exception('API校验密匙错误')
                
                elif pollInfo['code'] == -400:
                    raise Exception('请求错误')
                    
                elif pollInfo['code'] == 86038:
                    raise Exception('二维码已失效')
                    
                elif pollInfo['code'] == 86039:
                    time.sleep(5)
                
                else:
                    raise Exception(f'未知错误: {pollInfo["code"]}')

            # 保存登录信息
            saveInfo = {
                'update_time':int(time.time()*1000+0.5),
                'token_info':loginData['token_info'],
                'cookie_info':loginData['cookie_info']
            }

            # 将信息保存到info.json
            info_path = os.path.join('config', 'info.json')
            with open(info_path, 'w+') as f:
                f.write(json.dumps(saveInfo,ensure_ascii=False,separators=(',',':')))

            # 从cookie_info中提取cookie信息
            cookies = {}
            for cookie in loginData['cookie_info']['cookies']:
                cookies[cookie['name']] = cookie['value']

            sessdata = cookies.get('SESSDATA', '')
            bili_jct = cookies.get('bili_jct', '')
            buvid3 = cookies.get('buvid3', '')

            # 更新请求头中的Cookie
            self.headers['Cookie'] = f'SESSDATA={sessdata}; bili_jct={bili_jct}; buvid3={buvid3}'
            
            # 创建cookies.txt文件
            with open(self.cookies_file, "w", encoding="utf-8") as f:
                json.dump({
                    "SESSDATA": sessdata,
                    "bili_jct": bili_jct,
                    "buvid3": buvid3
                }, f)

            print(f"登录成功, 有效期至{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + int(loginData['token_info']['expires_in'])))}")
            return True
        except Exception as e:
            print(f"二维码登录失败：{str(e)}")
            return False

    def refresh_login(self):
        """刷新登录凭证"""
        try:
            info_path = os.path.join('config', 'info.json')
            if not os.path.exists(info_path):
                return False

            saveInfo = json.loads(open(info_path).read())

            rsp_data = requests.post("https://passport.bilibili.com/api/v2/oauth2/refresh_token",
                params=self.tvsign({
                    'access_key':saveInfo['token_info']['access_token'], 
                    'refresh_token':saveInfo['token_info']['refresh_token'],
                    'ts':int(time.time())
                }),
                headers={
                    "content-type": "application/x-www-form-urlencoded", 
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }).json()

            if rsp_data['code'] == 0:
                print(f"刷新成功, 有效期至{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(rsp_data['ts'] + int(rsp_data['data']['token_info']['expires_in'])))}")

                saveInfo = {
                    'update_time':rsp_data['ts'],
                    'token_info':rsp_data['data']['token_info'],
                    'cookie_info':rsp_data['data']['cookie_info']
                }
                with open(info_path, 'w+') as f:
                    f.write(json.dumps(saveInfo,ensure_ascii=False,separators=(',',':')))

                # 更新Cookie
                cookies = {}
                for cookie in rsp_data['data']['cookie_info']['cookies']:
                    cookies[cookie['name']] = cookie['value']

                sessdata = cookies.get('SESSDATA', '')
                bili_jct = cookies.get('bili_jct', '')
                buvid3 = cookies.get('buvid3', '')

                self.headers['Cookie'] = f'SESSDATA={sessdata}; bili_jct={bili_jct}; buvid3={buvid3}'
                
                # 更新cookies.txt文件
                with open(self.cookies_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "SESSDATA": sessdata,
                        "bili_jct": bili_jct,
                        "buvid3": buvid3
                    }, f)

                return True
            else:
                print(f'刷新失败: {rsp_data.get("message", "未知错误")}')
                return False
        except Exception as e:
            print(f"刷新登录失败：{str(e)}")
            return False


class Config:
    def __init__(self):
        # 确保config目录存在
        if not os.path.exists('config'):
            os.makedirs('config')
        self.config_file = os.path.join("config", "config.json")
        self.default_config = {
            "last_user_id": "",
            "last_favorites_id": "",
            "last_output_dir": "",
            "max_workers": "3",
            "show_download_list": False,  # 添加下载列表显示偏好
            "window_size": "800x600",
            "window_position": "",
            "theme": "default"
        }
        self.config = self.load_config()
    
    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return self.default_config.copy()
        except:
            return self.default_config.copy()
    
    def save_config(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=4)


class BiliFavGUI:
    def __init__(self):
        # 创建主窗口
        self.root = tk.Tk()
        self.root.title("哔哩哔哩收藏夹下载工具")
        self.root.geometry("900x800")
        self.root.minsize(900, 600)
        
        # 创建样式
        self.style = ttk.Style()
        self.style.configure("TFrame", background="#f5f5f5")
        self.style.configure("TButton", background="#f5f5f5")
        self.style.configure("TLabel", background="#f5f5f5")
        
        # 配置管理
        self.config = Config()
        self.config.load_config()
        
        # 创建bili_fav实例
        self.bili_fav = Bili_fav("", "")  # 初始化时不传递ID，后续设置
        self.bili_fav.gui_callback = self.handle_callback
        
        # 设置日志记录
        self.setup_logger()
        
        # 初始化属性
        self.user_id = tk.StringVar()
        self.favorites_id = tk.StringVar()
        self.favorites_url = tk.StringVar()
        self.sessdata = tk.StringVar()
        self.bili_jct = tk.StringVar()
        self.buvid3 = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.download_danmaku = tk.BooleanVar(value=False)
        self.max_workers = tk.StringVar(value="3")  # 默认3个并行下载
        
        # 初始化排序相关属性
        self.sort_column = None  # 当前排序列
        self.sort_reverse = False  # 是否降序排序
        
        # 初始化线程池
        self.format_pool = ThreadPoolExecutor(max_workers=3)
        
        # 确保config目录存在
        if not os.path.exists('config'):
            os.makedirs('config')
            
        # 文件路径
        self.you_get_path = 'you-get'
        self.cookies_file = os.path.join('config', 'cookies.txt')
        self.config_file = os.path.join('config', 'config.json')
        self.formats_cache_file = os.path.join('config', 'formats_cache.json')  # 添加格式缓存文件
        
        # 下载器相关属性
        self.downloader = None
        self.paused = False
        self.cancelled = False
        self.active_processes = []
        self.pause_event = threading.Event()
        self.download_queue = Queue()
        self.is_downloading = False
        
        # 加载格式缓存
        self.formats_cache = self.load_formats_cache()
        
        # 创建GUI组件
        self.create_widgets()
        
        # 加载保存的值
        self.load_saved_values()
        
        # 配置窗口
        self.root.geometry("800x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 添加登录状态检查定时器
        self.login_check_timer = None
        self.start_login_check_timer()
        
        # 添加登录状态过期时间
        self.login_expire_time = None

    def setup_logger(self):
        """设置日志处理器"""
        # 创建日志窗口
        self.log_window = tk.Toplevel(self.root)
        self.log_window.title("运行日志")
        self.log_window.geometry("800x400")
        
        # 创建文本框
        self.log_text = tk.Text(self.log_window, wrap=tk.WORD, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(self.log_window, orient="vertical", command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        # 创建自定义日志处理器
        class TextHandler(logging.Handler):
            def __init__(self, text_widget):
                logging.Handler.__init__(self)
                self.text_widget = text_widget
            
            def emit(self, record):
                msg = self.format(record)
                def append():
                    self.text_widget.insert(tk.END, msg + '\n')
                    self.text_widget.see(tk.END)
                self.text_widget.after(0, append)
        
        # 配置日志
        self.logger = logging.getLogger('BiliFav')
        self.logger.setLevel(logging.DEBUG)
        
        # 清除所有已存在的处理器
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # 添加文本处理器
        text_handler = TextHandler(self.log_text)
        text_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(text_handler)
        
        # 添加文件处理器
        logs_dir = os.path.join('config', 'logs')
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
        file_handler = logging.FileHandler(
            os.path.join(logs_dir, f'bilibili_fav_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
            encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(file_handler)

    def load_formats_cache(self):
        """加载格式缓存"""
        try:
            if os.path.exists(self.formats_cache_file):
                with open(self.formats_cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            self.logger.error(f"加载格式缓存失败：{str(e)}")
            return {}

    def save_formats_cache(self):
        """保存格式缓存"""
        try:
            with open(self.formats_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.formats_cache, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.logger.error(f"保存格式缓存失败：{str(e)}")

    def get_video_formats(self, video_id):
        """获取视频的可用格式"""
        # 先检查缓存
        if video_id in self.formats_cache:
            cache_data = self.formats_cache[video_id]
            cache_time = cache_data.get('time', 0)
            # 缓存有效期为24小时
            if time.time() - cache_time < 24 * 60 * 60:
                self.logger.info(f"使用缓存的格式信息：{video_id}")
                return cache_data['formats']
        
        video_url = f"https://www.bilibili.com/video/{video_id}"
        info_cmd = f'"{self.you_get_path}" --info -c "{self.cookies_file}" "{video_url}"'
        
        try:
            self.logger.info(f"获取视频格式信息：{video_url}")
            process = subprocess.run(
                info_cmd, 
                shell=True, 
                capture_output=True, 
                text=True, 
                encoding='utf-8',
                errors='replace'
            )
            
            if process.returncode == 0:
                self.logger.debug(f"you-get输出：\n{process.stdout}")
                formats = []
                current_format = None
                
                for line in process.stdout.split('\n'):
                    if '- format:' in line:
                        current_format = line.split('format:')[1].strip()
                    elif 'quality:' in line and current_format:
                        quality = line.split('quality:')[1].strip()
                        formats.append(f"{quality} ({current_format})")
                
                if formats:
                    self.logger.info(f"找到以下格式：{formats}")
                    # 更新缓存
                    self.formats_cache[video_id] = {
                        'formats': formats,
                        'time': time.time()
                    }
                    self.save_formats_cache()
                    return formats
                else:
                    self.logger.warning("未找到任何可用格式")
                    return ["获取格式失败"]
            
            self.logger.error(f"获取格式失败，you-get返回：{process.stderr}")
            return ["获取格式失败"]
        except Exception as e:
            self.logger.error(f"获取格式出错：{str(e)}")
            return ["获取格式失败"]

    def create_widgets(self):
        """创建GUI组件"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.grid(row=0, column=0, sticky='nsew')
        
        # 登录信息区域
        login_frame = ttk.LabelFrame(main_frame, text="登录信息")
        login_frame.grid(row=0, column=0, sticky='ew', padx=5, pady=5)
        
        # 添加登录状态显示
        self.login_status = ttk.Label(login_frame, text="未登录", foreground="red")
        self.login_status.grid(row=0, column=0, columnspan=2, sticky='w', padx=5, pady=2)
        
        # 添加登录按钮
        self.login_btn = ttk.Button(login_frame, text="登录", command=self.login)
        self.login_btn.grid(row=1, column=0, columnspan=2, pady=5)
        
        # 添加退出登录按钮
        self.logout_btn = ttk.Button(login_frame, text="退出登录", command=self.logout, state="disabled")
        self.logout_btn.grid(row=2, column=0, columnspan=2, pady=5)
        
        # 收藏夹信息区域
        fav_frame = ttk.LabelFrame(main_frame, text="收藏夹信息")
        fav_frame.grid(row=1, column=0, sticky='ew', padx=5, pady=5)
        
        ttk.Label(fav_frame, text="收藏夹链接:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        ttk.Entry(fav_frame, textvariable=self.favorites_url).grid(row=0, column=1, sticky='ew', padx=5)
        ttk.Label(fav_frame, text="示例: https://space.bilibili.com/12345678/favlist?fid=87654321").grid(row=1, column=0, columnspan=2, sticky='w', padx=5, pady=2)
        
        # 下载设置区域
        settings_frame = ttk.LabelFrame(main_frame, text="下载设置")
        settings_frame.grid(row=2, column=0, sticky='ew', padx=5, pady=5)
        
        # 输出目录选择
        ttk.Label(settings_frame, text="输出目录:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        ttk.Entry(settings_frame, textvariable=self.output_dir_var).grid(row=0, column=1, columnspan=2, sticky='ew', padx=5)
        ttk.Button(settings_frame, text="浏览", command=self.select_output_dir).grid(row=0, column=3, padx=5)
        
        # 下载选项行
        options_frame = ttk.Frame(settings_frame)
        options_frame.grid(row=1, column=0, columnspan=4, sticky='ew', padx=5, pady=2)
        
        # 弹幕下载选项
        danmaku_check = ttk.Checkbutton(
            options_frame, 
            text="下载弹幕", 
            variable=self.download_danmaku,
            command=lambda: self.logger.info(f"弹幕下载选项已{'启用' if self.download_danmaku.get() else '禁用'}")
        )
        danmaku_check.pack(side='left')
        
        # 并行下载数量选择
        parallel_frame = ttk.Frame(options_frame)
        parallel_frame.pack(side='right')
        
        ttk.Label(parallel_frame, text="并行下载数:").pack(side='left')
        parallel_spinbox = ttk.Spinbox(
            parallel_frame,
            from_=1,
            to=10,
            width=3,
            textvariable=self.max_workers
        )
        parallel_spinbox.pack(side='left', padx=(5, 0))
        
        # 下载列表
        list_frame = ttk.LabelFrame(main_frame, text="下载列表")
        list_frame.grid(row=3, column=0, sticky='nsew', padx=5, pady=5)
        
        self.download_list = ttk.Treeview(
            list_frame,
            columns=('序号', '标题', '状态', '可用格式', '进度', '速度', 'BV号', 'video_id'),
            show='headings'
        )
        
        # 设置列标题
        self.download_list.heading('序号', text='序号', command=lambda: self.sort_treeview('序号'))
        self.download_list.heading('标题', text='标题', command=lambda: self.sort_treeview('标题'))
        self.download_list.heading('状态', text='状态', command=lambda: self.sort_treeview('状态'))
        self.download_list.heading('可用格式', text='可用格式')
        self.download_list.heading('进度', text='进度', command=lambda: self.sort_treeview('进度'))
        self.download_list.heading('速度', text='速度', command=lambda: self.sort_treeview('速度'))
        self.download_list.heading('BV号', text='BV号')
        
        # 设置列宽
        self.download_list.column('序号', width=50)
        self.download_list.column('标题', width=250)
        self.download_list.column('状态', width=80)
        self.download_list.column('可用格式', width=150)
        self.download_list.column('进度', width=80)
        self.download_list.column('速度', width=80)
        self.download_list.column('BV号', width=150)
        self.download_list.column('video_id', width=0, stretch=False)
        
        # 创建右键菜单
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="取消", command=lambda: self.cancel_download(self.download_list.selection()))
        
        # 绑定右键菜单
        self.download_list.bind("<Button-3>", self.show_context_menu)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.download_list.yview)
        self.download_list.configure(yscrollcommand=scrollbar.set)
        
        self.download_list.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        
        # 下载按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, sticky='ew', padx=5, pady=5)
        
        # 列出内容按钮
        self.download_btn = ttk.Button(button_frame, text="列出内容", command=self.list_favorites)
        self.download_btn.grid(row=0, column=0, padx=2)
        
        self.add_to_queue_btn = ttk.Button(
            button_frame, 
            text="添加到队列", 
            command=self.add_to_download_queue,
            state='disabled'
        )
        self.add_to_queue_btn.grid(row=0, column=1, padx=2)
        
        self.start_queue_btn = ttk.Button(
            button_frame, 
            text="开始下载队列", 
            command=self.start_download_queue,
            state='disabled'
        )
        self.start_queue_btn.grid(row=0, column=2, padx=2)
        
        self.cancel_all_btn = ttk.Button(
            button_frame, 
            text="全部取消", 
            command=self.cancel_all_downloads,
            state='disabled'
        )
        self.cancel_all_btn.grid(row=0, column=3, padx=2)
        
        # 添加一键添加所有视频按钮
        self.add_all_btn = ttk.Button(
            button_frame, 
            text="一键添加全部", 
            command=self.add_all_to_queue,
            state='disabled'
        )
        self.add_all_btn.grid(row=0, column=4, padx=2)  # 添加到最后一列
        
        # 平均分配按钮空间
        for i in range(5):  # 现在有5个按钮
            button_frame.columnconfigure(i, weight=1)
        
        # 配置grid权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)  # 列表区域可扩展
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        login_frame.columnconfigure(1, weight=1)
        fav_frame.columnconfigure(1, weight=1)
        settings_frame.columnconfigure(1, weight=1)

    def login(self):
        """用户登录"""
        try:
            self.logger.info("开始登录...")
            
            # 创建一个新线程执行登录操作
            threading.Thread(target=self.login_thread, daemon=True).start()
        except Exception as e:
            self.logger.error(f"登录时出错: {str(e)}")
            messagebox.showerror("登录错误", str(e))
            
    def login_thread(self):
        """执行登录的线程"""
        try:
            # 尝试刷新登录
            info_path = os.path.join('config', 'info.json')
            if os.path.exists(info_path):
                self.logger.info("尝试刷新登录状态...")
                if self.bili_fav.refresh_login():
                    self.logger.info("登录刷新成功!")
                    self.after_login_success()
                    return
                else:
                    self.logger.info("登录刷新失败，将使用扫码登录")
            
            # 如果刷新失败或没有info.json，则使用二维码登录
            self.logger.info("开始扫码登录...")
            result = self.bili_fav.qrcode_login()
            
            if result:
                self.after_login_success()
            else:
                self.logger.error("登录失败")
                messagebox.showerror("登录失败", "请检查网络连接或重试")
        except Exception as e:
            self.logger.error(f"登录线程出错: {str(e)}")
            messagebox.showerror("登录错误", str(e))
    
    def after_login_success(self):
        """登录成功后的操作"""
        self.logger.info("登录成功!")
        
        # 从info.json读取登录信息
        try:
            info_path = os.path.join('config', 'info.json')
            with open(info_path, 'r', encoding='utf-8') as f:
                login_info = json.load(f)
                cookies = {}
                for cookie in login_info['cookie_info']['cookies']:
                    cookies[cookie['name']] = cookie['value']
                
                # 更新Cookie变量
                self.sessdata.set(cookies.get('SESSDATA', ''))
                self.bili_jct.set(cookies.get('bili_jct', ''))
                self.buvid3.set(cookies.get('buvid3', ''))
                
                # 设置登录过期时间（提前5分钟提醒）
                expire_time = login_info.get('token_info', {}).get('expires_in', 0)
                if expire_time:
                    self.login_expire_time = time.time() + expire_time - 300  # 提前5分钟提醒
                
                # 保存到cookies文件
                bili_cookies_path = os.path.join('config', 'bili_cookies.json')
                with open(bili_cookies_path, 'w', encoding='utf-8') as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=4)
                
                # 创建Netscape格式的cookies文件
                self.create_netscape_cookies(cookies)
                
                self.logger.debug(f"更新后的Cookie信息: {cookies}")
        except Exception as e:
            self.logger.error(f"读取登录信息失败: {str(e)}")
        
        # 更新界面状态
        self.root.after(0, lambda: self.login_btn.config(text="已登录", state="disabled"))
        self.root.after(0, lambda: self.logout_btn.config(state="normal"))  # 启用退出登录按钮
        self.root.after(0, lambda: self.download_btn.config(state="normal"))
        
        # 将登录状态保存到配置
        self.config.login_status = True
        self.config.save_config()
        
        # 关闭二维码窗口
        if hasattr(self, 'qr_window') and self.qr_window:
            self.root.after(0, self.qr_window.destroy)
            
        # 验证登录状态
        self.verify_login()
        
        # 启动登录状态检查定时器
        self.start_login_check_timer()

    def show_qrcode(self, qr_url):
        """显示二维码"""
        # 创建二维码窗口
        self.qr_window = tk.Toplevel(self.root)  # 保存窗口引用
        self.qr_window.title("扫码登录B站")
        self.qr_window.geometry("500x600")  # 进一步增加窗口大小
        self.qr_window.resizable(False, False)
        
        # 生成二维码图片
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=15,  # 增加二维码大小
            border=4,
        )
        qr.add_data(qr_url)
        qr.make(fit=True)
        
        # 创建更大的二维码图片
        img = qr.make_image(fill_color="black", back_color="white")
        
        # 转换为PhotoImage
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        
        # 使用PIL打开并调整大小
        image = Image.open(io.BytesIO(img_byte_arr))
        # 调整图片大小
        image = image.resize((400, 400), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        
        # 显示二维码和说明
        frame = ttk.Frame(self.qr_window, padding=30)  # 增加内边距
        frame.pack(fill="both", expand=True)
        
        # 添加说明文字
        label_info = ttk.Label(frame, text="请使用哔哩哔哩App扫描二维码登录", font=("", 14))
        label_info.pack(pady=15)
        
        # 创建画布来显示二维码
        canvas = tk.Canvas(frame, width=400, height=400)
        canvas.pack(pady=15)
        canvas.create_image(200, 200, image=photo)  # 居中显示
        canvas.image = photo  # 保持引用
        
        # 添加提示文字
        label_note = ttk.Label(frame, text="扫码后请在手机上确认登录", font=("", 12))
        label_note.pack(pady=15)
        
        # 将窗口置于顶层
        self.qr_window.lift()
        self.qr_window.focus_force()
        
        # 确保窗口显示在屏幕中央
        self.qr_window.update_idletasks()
        width = self.qr_window.winfo_width()
        height = self.qr_window.winfo_height()
        x = (self.qr_window.winfo_screenwidth() // 2) - (width // 2)
        y = (self.qr_window.winfo_screenheight() // 2) - (height // 2)
        self.qr_window.geometry(f'{width}x{height}+{x}+{y}')

    def handle_callback(self, action, *args):
        """处理bili_fav的回调"""
        if action == 'show_qrcode':
            self.root.after(0, lambda: self.show_qrcode(args[0]))
        elif action == 'add_item':
            # 原有的add_item处理
            index, title, video_id = args
            self.root.after(0, lambda: self.add_list_item(index, title, video_id))
        elif action == 'update_progress':
            # 原有的更新进度处理
            progress = args[0]
            self.root.after(0, lambda: self.progress_bar.config(value=progress))
        elif action == 'download_completed':
            # 原有的下载完成处理
            self.root.after(0, lambda: setattr(self, 'downloading', False))
            self.root.after(0, lambda: self.download_button.config(state='normal'))
            self.root.after(0, lambda: self.cancel_button.config(state='disabled'))
            self.root.after(0, lambda: self.pause_button.config(state='disabled'))
            self.root.after(0, lambda: messagebox.showinfo("下载完成", "所有视频已下载完成!"))
        elif action == 'download_cancelled':
            # 原有的下载取消处理
            self.root.after(0, lambda: setattr(self, 'downloading', False))
            self.root.after(0, lambda: self.download_button.config(state='normal'))
            self.root.after(0, lambda: self.cancel_button.config(state='disabled'))
            self.root.after(0, lambda: self.pause_button.config(state='disabled'))

    def select_output_dir(self):
        """选择输出目录"""
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.output_dir_var.set(dir_path)

    def extract_ids_from_url(self, url):
        """从收藏夹URL中提取用户ID和收藏夹ID"""
        try:
            # 尝试通过正则表达式提取数字ID
            ids = re.findall(r'(\d+)', url)
            
            if len(ids) >= 2:
                # 第一个连续长数字是用户ID，第二个连续长数字是收藏夹ID
                self.user_id.set(ids[0])
                self.favorites_id.set(ids[1])
                return ids[0], ids[1]
            else:
                raise ValueError("无法从URL中提取用户ID和收藏夹ID，请检查URL格式")
        except Exception as e:
            self.logger.error(f"提取ID失败：{str(e)}")
            raise ValueError("提取URL中的ID失败：" + str(e))

    def list_favorites(self):
        """列出收藏夹内容"""
        if not self.verify_login():
            return
            
        self.download_btn.state(['disabled'])
        threading.Thread(target=self.list_favorites_thread).start()

    def list_favorites_thread(self):
        """列出收藏夹内容的线程"""
        try:
            # 获取收藏夹URL并提取ID
            favorites_url = self.favorites_url.get().strip()
            
            if not favorites_url:
                raise ValueError("请填写收藏夹链接")
            
            # 从URL中提取用户ID和收藏夹ID
            user_id, favorites_id = self.extract_ids_from_url(favorites_url)
            
            self.logger.info(f"开始获取用户 {user_id} 的收藏夹 {favorites_id}")
            
            # 读取cookie信息
            try:
                bili_cookies_path = os.path.join('config', 'bili_cookies.json')
                with open(bili_cookies_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        raise ValueError("Cookie文件为空")
                    cookies = json.loads(content)
            except Exception as e:
                self.logger.error(f"读取Cookie文件失败：{str(e)}")
                raise ValueError("读取Cookie文件失败，请重新登录")
            
            # 构建请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Cookie': f"SESSDATA={cookies['SESSDATA']}; bili_jct={cookies['bili_jct']}; buvid3={cookies['buvid3']}"
            }
            
            # 获取收藏夹内容
            page = 1
            self.video_ids = []
            self.video_titles = []
            
            while True:
                url = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={favorites_id}&pn={page}&ps=20&keyword=&order=mtime&type=0&tid=0&platform=web"
                request = urllib.request.Request(url, headers=headers)
                response = urllib.request.urlopen(request)
                content = json.loads(response.read().decode('utf-8'))
                
                if content['code'] != 0:
                    raise ValueError(f"获取收藏夹内容失败：{content['message']}")
                
                medias = content['data']['medias']
                if not medias:
                    break
                    
                for media in medias:
                    self.video_ids.append(media['bvid'])
                    self.video_titles.append(media['title'])
                
                if len(medias) < 20:
                    break
                    
                page += 1
            
            if not self.video_ids:
                raise ValueError("收藏夹为空")
                
            self.logger.info(f"共找到 {len(self.video_ids)} 个视频")
            
            # 清空现有列表
            for item in self.download_list.get_children():
                self.download_list.delete(item)
            
            # 先添加所有视频到列表
            for i, (video_id, title) in enumerate(zip(self.video_ids, self.video_titles), 1):
                self.download_list.insert('', 'end', values=(
                    i, title, "等待获取格式...", "", "", "", video_id
                ))
            
            # 使用线程池并行获取格式信息
            with ThreadPoolExecutor(max_workers=3) as executor:
                # 每次处理3个视频
                for i in range(0, len(self.video_ids), 3):
                    chunk_videos = list(enumerate(self.video_ids[i:i+3], i))
                    futures = []
                    
                    # 提交当前批次的任务
                    for index, video_id in chunk_videos:
                        future = executor.submit(self.get_video_formats_task, index, video_id)
                        futures.append(future)
                    
                    # 等待当前批次完成
                    for future in as_completed(futures):
                        try:
                            # 获取任务结果
                            index, formats = future.result()
                            formats_str = '\n'.join(formats)
                            
                            # 更新列表显示
                            item_id = self.download_list.get_children()[index]
                            if formats[0] != "获取格式失败":
                                self.download_list.set(item_id, '状态', "待选择")
                            else:
                                self.download_list.set(item_id, '状态', "格式获取失败")
                            self.download_list.set(item_id, '可用格式', formats_str)
                            
                            self.logger.info(f"完成获取格式：视频 {self.video_ids[index]}")
                        except Exception as e:
                            self.logger.error(f"获取视频格式失败：{str(e)}")
                            item_id = self.download_list.get_children()[index]
                            self.download_list.set(item_id, '状态', "格式获取失败")
                    
                    # 更新进度
                    completed = i + len(chunk_videos)
                    total = len(self.video_ids)
                    self.logger.info(f"格式信息获取进度: {completed}/{total}")
            
            self.logger.info("所有视频格式获取完成")
            
            # 启用相关按钮
            self.add_to_queue_btn.state(['!disabled'])
            self.add_all_btn.state(['!disabled'])
            
        except Exception as e:
            self.logger.error(f"获取收藏夹内容失败：{str(e)}")
            messagebox.showerror("错误", str(e))
        finally:
            self.download_btn.state(['!disabled'])

    def get_video_formats_task(self, index, video_id):
        """获取视频格式的任务（用于线程池）"""
        try:
            formats = self.get_video_formats(video_id)
            return index, formats
        except Exception as e:
            self.logger.error(f"获取视频 {video_id} 的格式失败：{str(e)}")
            return index, ["获取格式失败"]

    def download_selected_format(self):
        """下载选中的格式（已废弃，使用新的下载队列机制）"""
        pass

    def quick_download(self):
        """一键下载最高画质（已废弃，使用新的下载队列机制）"""
        pass

    def get_progress(self, progress_str):
        """获取进度（已废弃，使用新的进度计算机制）"""
        pass

    def pause_all_downloads(self):
        """暂停所有下载"""
        try:
            self.paused = True
            self.pause_event.clear()  # 清除事件，使下载线程暂停
            self.logger.info("暂停所有下载")
            
            # 暂时禁用暂停按钮，启用继续按钮
            self.pause_all_btn.state(['disabled'])
            self.resume_all_btn.state(['!disabled'])
            
            # 更新所有正在下载的项目状态
            for item in self.download_list.get_children():
                if self.download_list.set(item, '状态') == "下载中":
                    self.download_list.set(item, '状态', "已暂停")
                    self.download_list.set(item, '速度', "已暂停")
            
            # 强制更新界面
            self.root.update()
            
        except Exception as e:
            self.logger.error(f"暂停下载时出错：{str(e)}")
            messagebox.showerror("错误", f"暂停下载时出错：{str(e)}")

    def resume_all_downloads(self):
        """继续所有下载"""
        try:
            self.paused = False
            self.pause_event.set()  # 设置事件，使下载线程继续
            self.logger.info("继续所有下载")
            
            # 暂时禁用继续按钮，启用暂停按钮
            self.resume_all_btn.state(['disabled'])
            self.pause_all_btn.state(['!disabled'])
            
            # 更新所有暂停的项目状态
            for item in self.download_list.get_children():
                if self.download_list.set(item, '状态') == "已暂停":
                    self.download_list.set(item, '状态', "下载中")
                    self.download_list.set(item, '速度', "计算中")
            
            # 强制更新界面
            self.root.update()
            
        except Exception as e:
            self.logger.error(f"继续下载时出错：{str(e)}")
            messagebox.showerror("错误", f"继续下载时出错：{str(e)}")

    def cancel_all_downloads(self):
        """取消所有下载"""
        if not messagebox.askyesno("确认", "确定要取消所有下载吗？"):
            return
            
        self.cancelled = True
        self.logger.info("取消所有下载")
        
        # 终止所有活动的下载进程
        for process in self.active_processes[:]:  # 使用副本进行迭代
            if process.poll() is None:  # 如果进程还在运行
                try:
                    process.terminate()  # 尝试正常终止
                    process.wait(timeout=5)  # 等待进程结束
                except subprocess.TimeoutExpired:
                    process.kill()  # 如果等待超时，强制结束进程
                except Exception as e:
                    self.logger.error(f"终止进程时出错：{str(e)}")
        
        # 清空活动进程列表
        self.active_processes.clear()
        
        # 更新所有正在下载的项目状态
        for item in self.download_list.get_children():
            status = self.download_list.set(item, '状态')
            if status == "下载中":
                self.download_list.set(item, '状态', "已取消")
                self.download_list.set(item, '进度', "-")
                self.download_list.set(item, '速度', "-")

    def download_video_thread(self, video_id, title, format_code, output_dir, item_id):
        """下载视频的线程"""
        process = None
        try:
            video_url = f"https://www.bilibili.com/video/{video_id}"
            
            # 构建下载命令
            cmd = [
                f'"{self.you_get_path}"',
                f'--format={format_code}',
                f'-o "{output_dir}"',
                f'-c "{self.cookies_file}"'
            ]
            
            # 检查弹幕下载选项
            danmaku_enabled = self.download_danmaku.get()
            self.logger.info(f"弹幕下载状态: {"启用" if danmaku_enabled else "禁用"}")
            
            if not danmaku_enabled:
                cmd.append('--no-caption')
                self.logger.info(f"跳过下载视频 {title} 的弹幕")
            else:
                self.logger.info(f"将下载视频 {title} 的弹幕")
            
            cmd.append(f'"{video_url}"')
            
            # 合并命令
            cmd = ' '.join(cmd)
            self.logger.debug(f"下载命令: {cmd}")
            
            # 使用 subprocess.Popen 时指定编码
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                encoding='utf-8',
                errors='replace'
            )
            
            # 添加到活动进程列表
            self.active_processes.append(process)
            
            last_update = time.time()
            
            # 更新进度
            while process.poll() is None:
                # 检查是否被取消
                if self.cancelled:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    self.logger.info(f"取消下载视频：{title}")
                    self.update_download_status(item_id, "已取消", "-", "-")
                    return
                
                try:
                    line = process.stdout.readline()
                    if not line:
                        continue
                    
                    # 记录输出到日志
                    if line.strip():
                        self.logger.debug(f"you-get输出: {line.strip()}")
                    
                    # 解析进度信息
                    if '%' in line:
                        try:
                            progress_match = re.search(r'(\d+\.?\d*)%', line)
                            if progress_match:
                                progress = str(int(float(progress_match.group(1))))
                                
                            speed_match = re.search(r'(\d+\.?\d*\s*[KMG]?B/s)', line)
                            speed = speed_match.group(1) if speed_match else "计算中"
                            
                            current_time = time.time()
                            if current_time - last_update >= 0.1:
                                self.update_download_status(item_id, "下载中", f"{progress}%", speed)
                                last_update = current_time
                                self.root.update()
                        except Exception as e:
                            self.logger.warning(f"解析进度信息失败：{str(e)}")
                            continue
                except Exception as e:
                    self.logger.warning(f"读取输出时出错：{str(e)}")
                    continue
            
            # 检查下载结果
            if process.returncode == 0:
                self.logger.info(f"视频 {title} 下载完成")
                self.update_download_status(item_id, "已完成", "100%", "-")
            else:
                error = process.stderr.read() if process else "未知错误"
                self.logger.error(f"下载失败：{error}")
                self.update_download_status(item_id, "失败", "-", "-")
                messagebox.showerror("错误", f"下载失败：{error}")
                
        except Exception as e:
            self.logger.error(f"下载过程出错：{str(e)}")
            messagebox.showerror("错误", f"下载过程出错：{str(e)}")
            self.update_download_status(item_id, "失败", "-", "-")
        finally:
            # 从活动进程列表中移除
            if process in self.active_processes:
                self.active_processes.remove(process)

    def sort_treeview(self, col):
        """对Treeview的指定列进行排序"""
        # 获取所有项目
        items = [(self.download_list.set(item, col), item) for item in self.download_list.get_children('')]
        
        # 如果点击的是同一列，反转排序顺序
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_reverse = False
            self.sort_column = col
        
        # 根据列类型进行排序
        if col == '序号':
            # 数字排序
            items.sort(key=lambda x: int(x[0]) if x[0].isdigit() else float('inf'), 
                      reverse=self.sort_reverse)
        elif col == '状态':
            # 状态排序（自定义顺序）
            status_order = {
                '等待中': 0,
                '正在下载': 1,
                '已暂停': 2,
                '已完成': 3,
                '已取消': 4,
                '下载失败': 5
            }
            items.sort(key=lambda x: status_order.get(x[0], 999), 
                      reverse=self.sort_reverse)
        elif col == '进度':
            # 进度排序（提取百分比数字）
            def get_progress(progress_str):
                try:
                    if '%' in progress_str:
                        return float(progress_str.split('(')[-1].split('%')[0])
                    return -1
                except:
                    return -1
            
            items.sort(key=lambda x: get_progress(x[0]), 
                      reverse=self.sort_reverse)
        else:
            # 字符串排序
            items.sort(key=lambda x: x[0].lower(), 
                      reverse=self.sort_reverse)
        
        # 重新插入排序后的项目
        for index, (val, item) in enumerate(items):
            self.download_list.move(item, '', index)
        
        # 更新列标题显示排序方向
        for col_name in ('序号', '标题', '状态', '进度', '速度'):
            if col_name == col:
                direction = '↓' if self.sort_reverse else '↑'
                self.download_list.heading(col_name, text=f'{col_name} {direction}')
            else:
                self.download_list.heading(col_name, text=col_name)

    def logout(self):
        """退出登录"""
        try:
            # 确认对话框
            if not messagebox.askyesno("确认", "确定要退出登录吗？"):
                return
                
            self.logger.info("开始退出登录...")
            
            # 清除cookie文件
            if os.path.exists(self.cookies_file):
                os.remove(self.cookies_file)
                self.logger.info("已删除cookies文件")
            
            # 清除info.json文件
            info_path = os.path.join('config', 'info.json')
            if os.path.exists(info_path):
                os.remove(info_path)
                self.logger.info("已删除info.json文件")
            
            # 清除bili_cookies.json文件
            bili_cookies_path = os.path.join('config', 'bili_cookies.json')
            if os.path.exists(bili_cookies_path):
                os.remove(bili_cookies_path)
                self.logger.info("已删除bili_cookies.json文件")
            
            # 清除登录状态变量
            self.sessdata.set('')
            self.bili_jct.set('')
            self.buvid3.set('')
            
            # 更新界面状态
            self.login_status.config(text="未登录", foreground="red")
            self.login_btn.config(text="登录", state="normal")
            self.logout_btn.config(state="disabled")  # 禁用退出登录按钮
            self.download_btn.config(state="disabled")
            self.add_to_queue_btn.config(state="disabled")
            self.start_queue_btn.config(state="disabled")
            self.add_all_btn.config(state="disabled")
            
            # 清空下载列表
            for item in self.download_list.get_children():
                self.download_list.delete(item)
            
            # 清除下载队列
            while not self.download_queue.empty():
                self.download_queue.get()
                self.download_queue.task_done()
            
            # 取消所有正在进行的下载
            self.cancel_all_downloads()
            
            # 清除登录过期时间
            self.login_expire_time = None
            
            # 保存配置
            self.save_values()
            
            self.logger.info("退出登录完成")
            messagebox.showinfo("提示", "已成功退出登录")
            
        except Exception as e:
            self.logger.error(f"退出登录时出错：{str(e)}")
            messagebox.showerror("错误", f"退出登录时出错：{str(e)}")

    def add_to_download_queue(self):
        """添加选中的视频到下载队列"""
        selected = self.download_list.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择要下载的视频")
            return
            
        # 获取输出目录
        output_dir = self.output_dir_var.get()
        if not output_dir:
            messagebox.showwarning("提示", "请先选择输出目录")
            return
            
        added_count = 0
        for item_id in selected:
            item = self.download_list.item(item_id)
            status = item['values'][2]
            formats_str = item['values'][3]
            video_id = item['values'][6]
            title = item['values'][1]
            
            if status == "等待获取格式...":
                self.logger.warning(f"跳过未获取格式的视频：{title}")
                continue
                
            if status == "已在队列" or status == "下载中" or status == "已完成":
                continue
            
            formats = formats_str.split('\n')
            if not formats or formats[0] == "获取格式失败":
                self.logger.warning(f"跳过格式获取失败的视频：{title}")
                continue
            
            # 弹出格式选择对话框
            dialog = tk.Toplevel(self.root)
            dialog.title(f"选择下载格式 - {title}")
            dialog.geometry("300x400")
            dialog.transient(self.root)  # 设置为主窗口的临时窗口
            dialog.grab_set()  # 模态对话框
            
            listbox = tk.Listbox(dialog)
            listbox.pack(fill=tk.BOTH, expand=True)
            
            for fmt in formats:
                listbox.insert(tk.END, fmt)
            
            def confirm():
                if not listbox.curselection():
                    messagebox.showwarning("提示", "请选择一个格式")
                    return
                    
                selected_format = formats[listbox.curselection()[0]]
                dialog.destroy()
                
                # 从格式字符串中提取格式代码
                format_match = re.search(r'\((.*?)\)', selected_format)
                if not format_match:
                    self.logger.error(f"无法从 {selected_format} 提取格式代码")
                    return
                    
                format_code = format_match.group(1)
                
                # 添加到下载队列
                self.download_queue.put((video_id, title, format_code, output_dir, item_id))
                self.download_list.set(item_id, '状态', "已在队列")
                nonlocal added_count
                added_count += 1
                
            ttk.Button(dialog, text="确定", command=confirm).pack(pady=5)
            
            # 等待对话框关闭
            self.root.wait_window(dialog)
        
        if added_count > 0:
            self.logger.info(f"已添加 {added_count} 个视频到下载队列")
            # 启用开始下载按钮
            self.start_queue_btn.state(['!disabled'])

    def start_download_queue(self):
        """开始处理下载队列"""
        if self.is_downloading:
            return
            
        self.is_downloading = True
        threading.Thread(target=self.process_download_queue, daemon=True).start()
        
        # 启用取消按钮
        self.cancel_all_btn.state(['!disabled'])
        
        # 重置下载状态
        self.cancelled = False

    def process_download_queue(self):
        """处理下载队列的线程"""
        try:
            # 创建线程池
            max_workers = int(self.max_workers.get())
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 存储所有任务的future对象
                all_futures = set()
                
                while not self.cancelled:
                    # 移除已完成的任务
                    done_futures = {f for f in all_futures if f.done()}
                    all_futures.difference_update(done_futures)
                    
                    # 检查是否还有任务需要处理
                    if self.download_queue.empty() and not all_futures:
                        break
                    
                    # 如果有空闲线程且队列不为空，添加新任务
                    while len(all_futures) < max_workers and not self.download_queue.empty():
                        try:
                            video_id, title, format_code, output_dir, item_id = self.download_queue.get_nowait()
                            
                            # 更新状态
                            self.download_list.set(item_id, '状态', "下载中")
                            self.download_list.set(item_id, '进度', "0%")
                            self.download_list.set(item_id, '速度', "计算中")
                            
                            # 提交新的下载任务
                            future = executor.submit(
                                self.download_video_thread,
                                video_id, title, format_code, output_dir, item_id
                            )
                            all_futures.add(future)
                            
                            self.download_queue.task_done()
                        except Exception as e:
                            self.logger.error(f"添加下载任务失败：{str(e)}")
                            break
                    
                    # 使用as_completed监控已完成的任务
                    if all_futures:
                        done, _ = wait(all_futures, timeout=0.1, return_when=FIRST_COMPLETED)
                        for future in done:
                            try:
                                future.result()  # 获取结果以检查是否有异常
                            except Exception as e:
                                self.logger.error(f"下载任务执行失败：{str(e)}")
                            all_futures.remove(future)
                    else:
                        time.sleep(0.1)  # 避免空闲时CPU占用过高
                        
            # 等待所有剩余任务完成
            if all_futures:
                for future in as_completed(all_futures):
                    try:
                        future.result()
                    except Exception as e:
                        self.logger.error(f"等待剩余任务时出错：{str(e)}")
                        
        except Exception as e:
            self.logger.error(f"处理下载队列时出错：{str(e)}")
        finally:
            self.is_downloading = False

    def load_saved_values(self):
        """加载保存的配置值"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                    # 加载基本配置
                    self.user_id.set(config.get('user_id', ''))
                    self.favorites_id.set(config.get('favorites_id', ''))
                    self.favorites_url.set(config.get('favorites_url', ''))
                    self.output_dir_var.set(config.get('output_dir', ''))
                    self.download_danmaku.set(config.get('download_danmaku', False))
                    self.max_workers.set(config.get('max_workers', '3'))  # 加载并行下载数量
                    
                    # 加载上次登录信息
                    last_login = config.get('last_login', {})
                    if last_login:
                        self.sessdata.set(last_login.get('SESSDATA', ''))
                        self.bili_jct.set(last_login.get('bili_jct', ''))
                        self.buvid3.set(last_login.get('buvid3', ''))
                        
                        # 如果有完整的登录信息，尝试验证登录状态
                        if all([last_login.get('SESSDATA'), last_login.get('bili_jct'), last_login.get('buvid3')]):
                            self.verify_login()
                    
        except Exception as e:
            self.logger.error(f"加载配置文件失败：{str(e)}")

    def save_values(self):
        """保存当前配置值"""
        try:
            config = {
                'user_id': self.user_id.get().strip(),
                'favorites_id': self.favorites_id.get().strip(),
                'favorites_url': self.favorites_url.get().strip(),
                'output_dir': self.output_dir_var.get().strip(),
                'download_danmaku': self.download_danmaku.get(),
                'max_workers': self.max_workers.get(),  # 保存并行下载数量
                'last_login': {
                    'SESSDATA': self.sessdata.get().strip(),
                    'bili_jct': self.bili_jct.get().strip(),
                    'buvid3': self.buvid3.get().strip()
                }
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
                
        except Exception as e:
            self.logger.error(f"保存配置文件失败：{str(e)}")

    def verify_login(self):
        """验证登录状态"""
        try:
            self.logger.debug("开始验证登录状态...")
            
            cookies = {
                'SESSDATA': self.sessdata.get().strip(),
                'bili_jct': self.bili_jct.get().strip(),
                'buvid3': self.buvid3.get().strip()
            }
            
            self.logger.debug(f"当前Cookie信息: {cookies}")
            
            # 验证登录状态
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Cookie': f"SESSDATA={cookies['SESSDATA']}; bili_jct={cookies['bili_jct']}; buvid3={cookies['buvid3']}"
            }
            
            self.logger.debug("发送验证请求...")
            nav_url = 'https://api.bilibili.com/x/web-interface/nav'
            request = urllib.request.Request(nav_url, headers=headers)
            response = urllib.request.urlopen(request)
            content = json.loads(response.read().decode('utf-8'))
            
            self.logger.debug(f"验证响应: {content}")
            
            if content['code'] == 0:
                # 登录有效，保存cookie文件
                bili_cookies_path = os.path.join('config', 'bili_cookies.json')
                with open(bili_cookies_path, 'w', encoding='utf-8') as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=4)
                self.create_netscape_cookies(cookies)
                
                # 更新UI状态
                self.login_status.config(text=f"已登录：{content['data']['uname']}", foreground="green")
                self.download_btn.state(['!disabled'])
                self.logger.info(f"登录状态有效：{content['data']['uname']}")
                return True
            else:
                self.logger.warning(f"登录状态已失效，错误码：{content['code']}，消息：{content.get('message', '未知错误')}")
                self.login_status.config(text="登录已失效", foreground="red")
                return False
                
        except Exception as e:
            self.logger.error(f"验证登录状态失败：{str(e)}", exc_info=True)
            self.login_status.config(text="登录状态检查失败", foreground="red")
            return False

    def on_closing(self):
        """窗口关闭时的处理"""
        try:
            # 取消登录状态检查定时器
            if self.login_check_timer:
                self.root.after_cancel(self.login_check_timer)
            
            # 保存配置
            self.save_values()
            # 保存格式缓存
            self.save_formats_cache()
            # 关闭线程池
            self.format_pool.shutdown(wait=False)
            
            # 终止所有活动的下载进程
            for process in self.active_processes[:]:  # 使用副本进行迭代
                if process.poll() is None:  # 如果进程还在运行
                    try:
                        process.terminate()  # 尝试正常终止
                        process.wait(timeout=5)  # 等待进程结束
                    except subprocess.TimeoutExpired:
                        process.kill()  # 如果等待超时，强制结束进程
                    except Exception as e:
                        self.logger.error(f"终止进程时出错：{str(e)}")
            
            # 清空活动进程列表
            self.active_processes.clear()
            
        except Exception as e:
            self.logger.error(f"关闭窗口时出错：{str(e)}")
        finally:
            # 销毁窗口
            self.root.destroy()

    def add_all_to_queue(self):
        """一键添加所有视频到下载队列（使用最高画质）"""
        try:
            # 获取输出目录
            output_dir = self.output_dir_var.get()
            if not output_dir:
                messagebox.showwarning("提示", "请先选择输出目录")
                return
                
            # 确认对话框
            if not messagebox.askyesno("确认", "是否将所有视频以最高画质添加到下载队列？"):
                return
                
            added_count = 0
            skipped_count = 0
            
            # 遍历所有视频
            for item_id in self.download_list.get_children():
                item = self.download_list.item(item_id)
                status = item['values'][2]
                formats_str = item['values'][3]
                video_id = item['values'][6]
                title = item['values'][1]
                
                # 跳过已在队列或已完成的视频
                if status in ["已在队列", "下载中", "已完成"]:
                    skipped_count += 1
                    continue
                
                # 跳过未获取格式的视频
                if status == "等待获取格式...":
                    self.logger.warning(f"跳过未获取格式的视频：{title}")
                    skipped_count += 1
                    continue
                
                formats = formats_str.split('\n')
                if not formats or formats[0] == "获取格式失败":
                    self.logger.warning(f"跳过格式获取失败的视频：{title}")
                    skipped_count += 1
                    continue
                
                try:
                    # 选择第一个格式（最高画质）
                    first_format = formats[0]
                    format_match = re.search(r'\((.*?)\)', first_format)
                    if not format_match:
                        self.logger.error(f"无法从 {first_format} 提取格式代码")
                        skipped_count += 1
                        continue
                        
                    format_code = format_match.group(1)
                    self.logger.info(f"为视频 {title} 选择格式：{first_format} (代码: {format_code})")
                    
                    # 添加到下载队列
                    self.download_queue.put((video_id, title, format_code, output_dir, item_id))
                    self.download_list.set(item_id, '状态', "已在队列")
                    added_count += 1
                    
                except Exception as e:
                    self.logger.error(f"处理视频 {title} 时出错：{str(e)}")
                    skipped_count += 1
                    continue
            
            # 显示结果
            message = f"成功添加 {added_count} 个视频到下载队列"
            if skipped_count > 0:
                message += f"\n跳过 {skipped_count} 个视频"
            messagebox.showinfo("添加完成", message)
            
            if added_count > 0:
                # 启用开始下载按钮
                self.start_queue_btn.state(['!disabled'])
                
        except Exception as e:
            self.logger.error(f"一键添加视频时出错：{str(e)}")
            messagebox.showerror("错误", f"一键添加视频时出错：{str(e)}")

    def create_netscape_cookies(self, cookies):
        """创建Netscape格式的cookies文件"""
        try:
            with open(self.cookies_file, 'w', encoding='utf-8') as f:
                for name, value in cookies.items():
                    f.write(f".bilibili.com\tTRUE\t/\tFALSE\t1999999999\t{name}\t{value}\n")
            self.logger.info("成功创建Netscape格式的cookies文件")
        except Exception as e:
            self.logger.error(f"创建cookies文件失败：{str(e)}")

    def show_context_menu(self, event):
        """显示右键菜单"""
        try:
            # 获取点击位置对应的item和列
            item = self.download_list.identify_row(event.y)
            column = self.download_list.identify_column(event.x)
            
            if item:
                # 选中被点击的item
                self.download_list.selection_set(item)
                
                # 清除现有菜单项
                self.context_menu.delete(0, tk.END)
                
                # 在BV号列显示复制选项，其他列显示取消选项
                if column == '#7':  # BV号列的索引是7
                    self.context_menu.add_command(
                        label="复制BV号",
                        command=lambda: self.copy_bv_number(item)
                    )
                else:
                    self.context_menu.add_command(
                        label="取消",
                        command=lambda: self.cancel_download([item])
                    )
                self.context_menu.post(event.x_root, event.y_root)
        except Exception as e:
            self.logger.error(f"显示右键菜单时出错：{str(e)}")

    def copy_bv_number(self, item_id):
        """复制BV号到剪贴板"""
        try:
            bv_number = self.download_list.set(item_id, 'BV号')
            if bv_number:
                self.root.clipboard_clear()
                self.root.clipboard_append(bv_number)
                self.logger.info(f"已复制BV号：{bv_number}")
        except Exception as e:
            self.logger.error(f"复制BV号时出错：{str(e)}")

    def pause_download(self, selected_items):
        """暂停选中的下载"""
        # 暂时禁用单个视频暂停功能
        if selected_items:
            self.logger.info("单个视频暂停功能已禁用")
            return
            
        # 暂停所有下载
        self.paused = True
        self.logger.info("暂停所有下载")
        if hasattr(self, 'gui_callback'):
            for thread_id in self.current_downloads:
                self.gui_callback('update_status', thread_id, "已暂停", "-", "-")

    def resume_download(self, selected_items):
        """继续选中的下载"""
        # 暂时禁用单个视频继续功能
        if selected_items:
            self.logger.info("单个视频继续功能已禁用")
            return
            
        # 继续所有下载
        self.paused = False
        self.logger.info("继续所有下载")
        if hasattr(self, 'gui_callback'):
            for thread_id in self.current_downloads:
                self.gui_callback('update_status', thread_id, "下载中", "0%", "0B/s")

    def cancel_download(self, selected_items):
        """取消选中的下载"""
        if not selected_items:
            return
            
        if not messagebox.askyesno("确认", "确定要取消选中的下载吗？"):
            return
            
        for item_id in selected_items:
            try:
                status = self.download_list.set(item_id, '状态')
                if status in ["下载中", "已暂停", "等待中"]:
                    # 获取视频ID
                    video_id = self.download_list.set(item_id, 'video_id')
                    # 设置取消状态
                    self.download_list.set(item_id, '状态', "已取消")
                    self.download_list.set(item_id, '进度', "-")
                    self.download_list.set(item_id, '速度', "-")
                    # 记录取消状态
                    if not hasattr(self, 'cancelled_downloads'):
                        self.cancelled_downloads = set()
                    self.cancelled_downloads.add(video_id)
                    # 从暂停列表中移除
                    if hasattr(self, 'paused_downloads'):
                        self.paused_downloads.discard(video_id)
                    self.logger.info(f"取消下载：{self.download_list.set(item_id, '标题')}")
            except Exception as e:
                self.logger.error(f"取消下载时出错：{str(e)}")

    def update_download_status(self, item_id, status, progress=None, speed=None):
        """更新下载状态"""
        try:
            self.download_list.set(item_id, '状态', status)
            if progress is not None:
                self.download_list.set(item_id, '进度', progress)
            if speed is not None:
                self.download_list.set(item_id, '速度', speed)
        except Exception as e:
            self.logger.error(f"更新下载状态时出错：{str(e)}")

    def start_login_check_timer(self):
        """启动登录状态检查定时器"""
        if self.login_check_timer:
            self.root.after_cancel(self.login_check_timer)
        
        # 每5分钟检查一次登录状态
        self.login_check_timer = self.root.after(300000, self.check_login_status)
        
    def check_login_status(self):
        """检查登录状态"""
        try:
            if not self.verify_login():
                # 如果登录状态无效，尝试刷新
                if self.bili_fav.refresh_login():
                    self.logger.info("登录状态已刷新")
                    self.verify_login()
                else:
                    self.logger.warning("登录状态已失效，需要重新登录")
                    self.login_status.config(text="登录已失效", foreground="red")
                    messagebox.showwarning("登录状态", "您的登录状态已失效，请重新登录")
            
            # 检查登录过期时间
            if self.login_expire_time and time.time() > self.login_expire_time:
                self.logger.warning("登录即将过期，请重新登录")
                messagebox.showwarning("登录状态", "您的登录即将过期，请重新登录")
            
            # 重新启动定时器
            self.start_login_check_timer()
            
        except Exception as e:
            self.logger.error(f"检查登录状态时出错：{str(e)}")
            self.start_login_check_timer()

def main():
    app = BiliFavGUI()
    app.root.mainloop()

if __name__ == '__main__':
    main()  