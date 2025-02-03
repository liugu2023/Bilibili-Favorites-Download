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
from concurrent.futures import ThreadPoolExecutor, as_completed


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

        # 文件路径
        self.you_get_path = 'you-get'
        self.cookies_file = 'cookies.txt'
        self.config_file = 'config.json'
        self.formats_cache_file = 'formats_cache.json'  # 添加格式缓存文件
        
        # 加载格式缓存
        self.formats_cache = self.load_formats_cache()

    def setup_logger(self):
        """设置日志记录器"""
        # 创建logs目录（如果不存在）
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        # 创建日志文件名（使用当前时间）
        log_filename = f'logs/download_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        
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

    # report spider results 显示爬虫结果
    def report(self):
        print("已搜索到%s部视频：" % len(self.video_ids))
        i = 1
        for title in self.video_titles:
            print("%s."%i + title)
            i += 1
    
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
        i = 1
        python_path = r"C:\Users\liugu\AppData\Local\Programs\Python\Python313\python.exe"
        you_get_path = os.path.join(os.path.dirname(python_path), "Scripts", "you-get.exe")
        
        # 创建cookies.txt文件
        cookies_file = "cookies.txt"
        with open(cookies_file, "w", encoding="utf-8") as f:
            f.write(f".bilibili.com\tTRUE\t/\tFALSE\t1999999999\tSESSDATA\t{self.headers['Cookie'].split('SESSDATA=')[1].split(';')[0]}\n")
            f.write(f".bilibili.com\tTRUE\t/\tFALSE\t1999999999\tbili_jct\t{self.headers['Cookie'].split('bili_jct=')[1].split(';')[0]}\n")
            f.write(f".bilibili.com\tTRUE\t/\tFALSE\t1999999999\tbuvid3\t{self.headers['Cookie'].split('buvid3=')[1].split(';')[0]}\n")
        
        # 记录下载失败的视频
        failed_downloads = []
        
        # 检查已下载的视频
        if output_dir:
            downloaded = self.check_downloaded_videos(output_dir)
            videos_to_download = [(vid, title) for vid, title in zip(self.video_ids, self.video_titles) 
                                if vid not in downloaded]
        else:
            videos_to_download = list(zip(self.video_ids, self.video_titles))
        
        if not videos_to_download:
            print("所有视频都已下载完成！")
            return
        
        print(f"共找到 {len(videos_to_download)} 个未下载的视频")
        
        # 如果有GUI回调，先更新下载列表
        if hasattr(self, 'gui_callback'):
            for i, (video_id, title) in enumerate(videos_to_download, 1):
                self.gui_callback('add_item', i, title, video_id)
        
        # 单线程下载
        for i, (video_id, title) in enumerate(videos_to_download, 1):
            if self.cancelled:
                break
                
            while self.paused:
                time.sleep(1)
                if self.cancelled:
                    break
                    
            self.download_video(video_id, title, i, output_dir, you_get_path, cookies_file)
            
            # 更新进度
            if hasattr(self, 'gui_callback'):
                progress = (i / len(videos_to_download)) * 100
                self.gui_callback('update_progress', progress)
        
        # 下载完成后的处理
        if hasattr(self, 'gui_callback'):
            if self.cancelled:
                self.gui_callback('download_cancelled')
            else:
                self.gui_callback('download_completed')
        
        print("所有视频下载完成！")

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
        """监控下载进度"""
        self.stop_monitor = False
        last_size = initial_size
        last_time = start_time
        total_size = 0  # 用于存储总大小
        update_interval = 0.2  # 更新频率为0.2秒一次
        
        # 获取文件总大小（仅在第一次获取）
        try:
            # 使用B站API获取视频信息
            api_url = f'https://api.bilibili.com/x/web-interface/view?bvid={video_id}'
            request = urllib.request.Request(api_url, headers=self.headers)
            response = urllib.request.urlopen(request)
            data = json.loads(response.read().decode('utf-8'))
            
            if data['code'] == 0:
                # 获取所有视频分P的大小总和
                pages = data['data']['pages']
                total_size = sum(page['size'] for page in pages)
                print(f"获取到视频总大小: {self._format_size(total_size)}")
            else:
                print(f"获取视频信息失败: {data['message']}")
                
        except Exception as e:
            print(f"获取视频大小失败：{str(e)}")
            total_size = 0
        
        last_percentage = 0  # 记录上一次的进度百分比
        
        while not self.stop_monitor:
            try:
                current_size = self._get_dir_size(output_dir)
                current_time = time.time()
                
                # 计算速度 (bytes/s)
                time_diff = current_time - last_time
                size_diff = current_size - last_size
                speed = size_diff / time_diff if time_diff > 0 else 0
                
                # 计算下载进度
                downloaded_size = current_size - initial_size
                if total_size > 0:
                    percentage = int((downloaded_size * 100) / total_size)
                    
                    # 确保进度不会后退或跳跃太大
                    if percentage < last_percentage:
                        percentage = last_percentage
                    elif percentage - last_percentage > 5:  # 限制单次进度增长
                        percentage = last_percentage + 5
                    
                    # 确保进度在合理范围内
                    if percentage > 100:
                        percentage = 99
                    elif percentage < 0:
                        percentage = 0
                        
                    # 检查下载是否完成
                    if percentage >= 99 and not size_diff and downloaded_size >= total_size * 0.99:
                        progress = "100%"
                        speed_str = "0B/s"
                        if hasattr(self, 'gui_callback'):
                            self.gui_callback('update_status', index, "已完成", progress, speed_str)
                        break
                    
                    progress = f"{percentage}%"
                    last_percentage = percentage  # 更新上一次的进度
                else:
                    # 如果无法获取总大小，使用增量显示进度
                    progress = "0%"
                
                # 格式化速度显示
                speed_str = self._format_size(speed) + "/s"
                
                # 更新GUI显示
                if hasattr(self, 'gui_callback'):
                    self.gui_callback('update_status', index, "正在下载", progress, speed_str)
                
                # 更新参考值
                last_size = current_size
                last_time = current_time
                
                time.sleep(update_interval)
                
            except Exception as e:
                print(f"监控进度出错：{str(e)}")
                time.sleep(update_interval)

    def _format_size(self, size):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

    def _format_time(self, seconds):
        """格式化时间"""
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            return f"{int(seconds/60)}分{int(seconds%60)}秒"
        else:
            hours = int(seconds/3600)
            minutes = int((seconds%3600)/60)
            return f"{hours}时{minutes}分"

    def pause_download(self):
        self.paused = True

    def resume_download(self):
        self.paused = False

    def cancel_download(self, video_id=None):
        if video_id:
            # 取消单个视频
            for thread_id, vid in list(self.current_downloads.items()):
                if vid == video_id:
                    del self.current_downloads[thread_id]
        else:
            # 取消所有下载
            self.cancelled = True
            self.current_downloads.clear()

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
                        
                        # 设置encoding='utf-8'来解决编码问题
                        process = subprocess.run(
                            cmd, 
                            shell=True, 
                            capture_output=True, 
                            text=False  # 使用二进制模式
                        )
                        
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


class Config:
    def __init__(self):
        self.config_file = "config.json"
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
        self.window = tk.Tk()
        self.window.title("B站收藏夹下载器")
        
        # 初始化属性
        self.user_id = tk.StringVar()
        self.favorites_id = tk.StringVar()
        self.sessdata = tk.StringVar()
        self.bili_jct = tk.StringVar()
        self.buvid3 = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.download_danmaku = tk.BooleanVar(value=False)
        
        # 初始化线程池
        self.format_pool = ThreadPoolExecutor(max_workers=3)
        
        # 文件路径
        self.you_get_path = 'you-get'
        self.cookies_file = 'cookies.txt'
        self.config_file = 'config.json'
        self.formats_cache_file = 'formats_cache.json'  # 添加格式缓存文件
        
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
        
        # 创建日志处理器
        self.setup_logger()
        
        # 创建GUI组件
        self.create_widgets()
        
        # 加载保存的值
        self.load_saved_values()
        
        # 配置窗口
        self.window.geometry("800x600")
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)

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

    def setup_logger(self):
        """设置日志处理器"""
        # 创建日志窗口
        self.log_window = tk.Toplevel(self.window)
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
        
        # 添加文本处理器
        text_handler = TextHandler(self.log_text)
        text_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(text_handler)
        
        # 添加文件处理器
        if not os.path.exists('logs'):
            os.makedirs('logs')
        file_handler = logging.FileHandler(
            f'logs/bilibili_fav_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
            encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(file_handler)

    def create_widgets(self):
        """创建GUI组件"""
        # 主框架
        main_frame = ttk.Frame(self.window, padding="5")
        main_frame.grid(row=0, column=0, sticky='nsew')
        
        # 登录信息区域
        login_frame = ttk.LabelFrame(main_frame, text="登录信息")
        login_frame.grid(row=0, column=0, sticky='ew', padx=5, pady=5)
        
        # 添加登录状态显示
        self.login_status = ttk.Label(login_frame, text="未登录", foreground="red")
        self.login_status.grid(row=0, column=0, columnspan=2, sticky='w', padx=5, pady=2)
        
        ttk.Label(login_frame, text="SESSDATA:").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        ttk.Entry(login_frame, textvariable=self.sessdata).grid(row=1, column=1, sticky='ew', padx=5)
        
        ttk.Label(login_frame, text="bili_jct:").grid(row=2, column=0, sticky='w', padx=5, pady=2)
        ttk.Entry(login_frame, textvariable=self.bili_jct).grid(row=2, column=1, sticky='ew', padx=5)
        
        ttk.Label(login_frame, text="buvid3:").grid(row=3, column=0, sticky='w', padx=5, pady=2)
        ttk.Entry(login_frame, textvariable=self.buvid3).grid(row=3, column=1, sticky='ew', padx=5)
        
        # 添加登录按钮
        self.login_btn = ttk.Button(login_frame, text="登录", command=self.login)
        self.login_btn.grid(row=4, column=0, columnspan=2, pady=5)
        
        # 收藏夹信息区域
        fav_frame = ttk.LabelFrame(main_frame, text="收藏夹信息")
        fav_frame.grid(row=1, column=0, sticky='ew', padx=5, pady=5)
        
        ttk.Label(fav_frame, text="用户ID:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        ttk.Entry(fav_frame, textvariable=self.user_id).grid(row=0, column=1, sticky='ew', padx=5)
        
        ttk.Label(fav_frame, text="收藏夹ID:").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        ttk.Entry(fav_frame, textvariable=self.favorites_id).grid(row=1, column=1, sticky='ew', padx=5)
        
        # 下载设置区域
        settings_frame = ttk.LabelFrame(main_frame, text="下载设置")
        settings_frame.grid(row=2, column=0, sticky='ew', padx=5, pady=5)
        
        # 输出目录选择
        ttk.Label(settings_frame, text="输出目录:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        ttk.Entry(settings_frame, textvariable=self.output_dir_var).grid(row=0, column=1, sticky='ew', padx=5)
        ttk.Button(settings_frame, text="浏览", command=self.select_output_dir).grid(row=0, column=2, padx=5)
        
        # 下载选项
        danmaku_check = ttk.Checkbutton(
            settings_frame, 
            text="下载弹幕", 
            variable=self.download_danmaku,
            command=lambda: self.logger.info(f"弹幕下载选项已{'启用' if self.download_danmaku.get() else '禁用'}")
        )
        danmaku_check.grid(row=1, column=0, columnspan=3, sticky='w', padx=5, pady=2)
        
        # 下载列表
        list_frame = ttk.LabelFrame(main_frame, text="下载列表")
        list_frame.grid(row=3, column=0, sticky='nsew', padx=5, pady=5)
        
        self.download_list = ttk.Treeview(
            list_frame,
            columns=('序号', '标题', '状态', '可用格式', '进度', '速度', 'video_id'),
            show='headings'
        )
        
        # 设置列标题
        self.download_list.heading('序号', text='序号', command=lambda: self.sort_treeview('序号'))
        self.download_list.heading('标题', text='标题', command=lambda: self.sort_treeview('标题'))
        self.download_list.heading('状态', text='状态', command=lambda: self.sort_treeview('状态'))
        self.download_list.heading('可用格式', text='可用格式')
        self.download_list.heading('进度', text='进度', command=lambda: self.sort_treeview('进度'))
        self.download_list.heading('速度', text='速度', command=lambda: self.sort_treeview('速度'))
        
        # 设置列宽
        self.download_list.column('序号', width=50)
        self.download_list.column('标题', width=300)
        self.download_list.column('状态', width=100)
        self.download_list.column('可用格式', width=200)
        self.download_list.column('进度', width=100)
        self.download_list.column('速度', width=100)
        self.download_list.column('video_id', width=0, stretch=False)
        
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
        
        self.pause_all_btn = ttk.Button(
            button_frame, 
            text="全部暂停", 
            command=self.pause_all_downloads,
            state='disabled'
        )
        self.pause_all_btn.grid(row=0, column=3, padx=2)
        
        self.resume_all_btn = ttk.Button(
            button_frame, 
            text="全部继续", 
            command=self.resume_all_downloads,
            state='disabled'
        )
        self.resume_all_btn.grid(row=0, column=4, padx=2)
        
        self.cancel_all_btn = ttk.Button(
            button_frame, 
            text="全部取消", 
            command=self.cancel_all_downloads,
            state='disabled'
        )
        self.cancel_all_btn.grid(row=0, column=5, padx=2)
        
        # 平均分配按钮空间
        for i in range(6):  # 现在有6个按钮
            button_frame.columnconfigure(i, weight=1)
        
        # 配置grid权重
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)  # 列表区域可扩展
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        login_frame.columnconfigure(1, weight=1)
        fav_frame.columnconfigure(1, weight=1)
        settings_frame.columnconfigure(1, weight=1)

    def login(self):
        """登录处理"""
        try:
            # 获取输入的cookie信息
            sessdata = self.sessdata.get().strip()
            bili_jct = self.bili_jct.get().strip()
            buvid3 = self.buvid3.get().strip()
            
            if not all([sessdata, bili_jct, buvid3]):
                messagebox.showwarning("提示", "请填写完整的登录信息")
                return
            
            # 验证登录状态
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Cookie': f'SESSDATA={sessdata}; bili_jct={bili_jct}; buvid3={buvid3}'
            }
            
            nav_url = 'https://api.bilibili.com/x/web-interface/nav'
            request = urllib.request.Request(nav_url, headers=headers)
            response = urllib.request.urlopen(request)
            content = response.read().decode('utf-8')
            user_info = json.loads(content)
            
            if user_info['code'] == 0:
                # 登录成功，保存cookie
                cookies = {
                    'SESSDATA': sessdata,
                    'bili_jct': bili_jct,
                    'buvid3': buvid3
                }
                
                # 保存JSON格式的cookie（用于API请求）
                with open('bili_cookies.json', 'w', encoding='utf-8') as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=4)
                
                # 保存Netscape格式的cookie（用于you-get）
                self.create_netscape_cookies(cookies)
                
                # 保存登录状态到配置文件
                config = {
                    'user_id': self.user_id.get().strip(),
                    'favorites_id': self.favorites_id.get().strip(),
                    'output_dir': self.output_dir_var.get().strip(),
                    'download_danmaku': self.download_danmaku.get(),  # 保存弹幕下载设置
                    'last_login': {
                        'SESSDATA': sessdata,
                        'bili_jct': bili_jct,
                        'buvid3': buvid3,
                        'username': user_info['data']['uname']
                    }
                }
                
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
                
                self.login_status.config(text=f"已登录：{user_info['data']['uname']}", foreground="green")
                self.download_btn.state(['!disabled'])
                self.logger.info(f"登录成功：{user_info['data']['uname']}")
                messagebox.showinfo("成功", "登录成功！")
            else:
                self.login_status.config(text="登录失败", foreground="red")
                self.logger.error(f"登录失败：{user_info['message']}")
                messagebox.showerror("错误", f"登录失败：{user_info['message']}")
                
        except Exception as e:
            self.login_status.config(text="登录失败", foreground="red")
            self.logger.error(f"登录过程出错：{str(e)}")
            messagebox.showerror("错误", f"登录过程出错：{str(e)}")

    def create_netscape_cookies(self, cookies):
        """创建 Netscape 格式的 cookie 文件"""
        try:
            with open(self.cookies_file, 'w', encoding='utf-8') as f:
                f.write('# Netscape HTTP Cookie File\n')
                f.write('# https://curl.haxx.se/rfc/cookie_spec.html\n')
                f.write('# This is a generated file!  Do not edit.\n\n')
                
                # 添加B站域名的cookie
                for name, value in cookies.items():
                    f.write(f'.bilibili.com\tTRUE\t/\tFALSE\t{int(time.time()) + 2592000}\t{name}\t{value}\n')
            
            self.logger.info("已创建 Netscape 格式的 cookie 文件")
        except Exception as e:
            self.logger.error(f"创建 cookie 文件失败：{str(e)}")

    def select_output_dir(self):
        """选择输出目录"""
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.output_dir_var.set(dir_path)

    def list_favorites(self):
        """列出收藏夹内容"""
        if not self.verify_login():
            return
            
        self.download_btn.state(['disabled'])
        threading.Thread(target=self.list_favorites_thread).start()

    def list_favorites_thread(self):
        """列出收藏夹内容的线程"""
        try:
            # 获取收藏夹内容
            user_id = self.user_id.get().strip()
            favorites_id = self.favorites_id.get().strip()
            
            if not user_id or not favorites_id:
                raise ValueError("请填写用户ID和收藏夹ID")
            
            self.logger.info(f"开始获取用户 {user_id} 的收藏夹 {favorites_id}")
            
            # 读取cookie信息
            try:
                with open('bili_cookies.json', 'r', encoding='utf-8') as f:
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
                
                try:
                    request = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(request) as response:
                        content = response.read().decode('utf-8')
                        data = json.loads(content)
                        
                        if data['code'] != 0:
                            raise ValueError(f"获取收藏夹内容失败：{data['message']}")
                        
                        medias = data['data']['medias']
                        if not medias:
                            break
                            
                        for media in medias:
                            self.video_ids.append(media['bvid'])
                            self.video_titles.append(media['title'])
                        
                        if len(medias) < 20:
                            break
                            
                        page += 1
                        
                except urllib.error.URLError as e:
                    self.logger.error(f"网络请求失败：{str(e)}")
                    raise ValueError("网络请求失败，请检查网络连接")
                except json.JSONDecodeError as e:
                    self.logger.error(f"解析响应数据失败：{str(e)}")
                    raise ValueError("解析响应数据失败，请稍后重试")
            
            if not self.video_ids:
                raise ValueError("收藏夹为空")
            
            # 清空现有列表
            for item in self.download_list.get_children():
                self.download_list.delete(item)
            
            # 先添加所有视频到列表
            self.logger.info(f"共找到 {len(self.video_ids)} 个视频，开始获取格式信息...")
            for i, (video_id, title) in enumerate(zip(self.video_ids, self.video_titles), 1):
                self.download_list.insert('', 'end', values=(
                    i, title, "等待获取格式...", "", "", "", video_id
                ))
                self.download_list.update()
            
            # 启用添加到队列按钮
            self.add_to_queue_btn.state(['!disabled'])
            
            # 使用线程池并行获取格式信息
            completed = 0
            futures = []
            
            # 提交所有任务
            for i, video_id in enumerate(self.video_ids):
                future = self.format_pool.submit(self.get_video_formats_task, i, video_id)
                futures.append(future)
            
            # 等待任务完成并更新进度
            for future in as_completed(futures):
                completed += 1
                self.logger.info(f"格式信息获取进度: {completed}/{len(self.video_ids)}")
                
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
                except Exception as e:
                    self.logger.error(f"获取视频格式失败：{str(e)}")
            
            self.logger.info("所有视频格式获取完成")
            
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
        """下载选中的格式"""
        selected = self.download_list.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择要下载的视频")
            return
            
        # 获取选中项的信息
        item = self.download_list.item(selected[0])
        status = item['values'][2]
        formats_str = item['values'][3]
        
        # 检查是否已获取到格式信息
        if status == "等待获取格式...":
            messagebox.showwarning("提示", "正在获取视频格式信息，请稍候...")
            return
        elif status == "格式获取失败":
            if not messagebox.askyesno("警告", "该视频格式获取失败，是否重试？"):
                return
            # 重新获取格式
            video_id = item['values'][6]
            index = int(item['values'][0]) - 1
            future = self.format_pool.submit(self.get_video_formats_task, index, video_id)
            future.add_done_callback(lambda f: self.update_format_result(f, index))

    def update_format_result(self, future, index):
        """更新格式获取结果的回调函数"""
        try:
            index, formats = future.result()
            formats_str = '\n'.join(formats)
            
            item_id = self.download_list.get_children()[index]
            if formats[0] != "获取格式失败":
                self.download_list.set(item_id, '状态', "待选择")
            else:
                self.download_list.set(item_id, '状态', "格式获取失败")
            self.download_list.set(item_id, '可用格式', formats_str)
            
        except Exception as e:
            self.logger.error(f"更新格式信息失败：{str(e)}")

    def quick_download(self):
        """一键下载最高画质"""
        selected = self.download_list.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择要下载的视频")
            return
            
        # 获取输出目录
        output_dir = self.output_dir_var.get()
        if not output_dir:
            messagebox.showwarning("提示", "请先选择输出目录")
            return
            
        download_count = 0
        for item_id in selected:
            item = self.download_list.item(item_id)
            status = item['values'][2]
            formats_str = item['values'][3]
            video_id = item['values'][6]
            title = item['values'][1]
            
            if status == "等待获取格式...":
                self.logger.warning(f"跳过未获取格式的视频：{title}")
                continue
            
            formats = formats_str.split('\n')
            if not formats or formats[0] == "获取格式失败":
                self.logger.warning(f"跳过格式获取失败的视频：{title}")
                continue
            
            try:
                # 选择第一个格式（通常是最高画质）
                first_format = formats[0]
                self.logger.debug(f"解析格式字符串：{first_format}")
                
                # 从格式字符串中提取格式代码，格式如 "1080P (dash-flv720)"
                format_match = re.search(r'\((.*?)\)', first_format)
                if not format_match:
                    self.logger.error(f"无法从 {first_format} 提取格式代码")
                    continue
                    
                format_code = format_match.group(1)
                self.logger.info(f"为视频 {title} 选择格式：{first_format} (代码: {format_code})")
                
                # 更新状态
                self.download_list.set(item_id, '状态', "下载中")
                self.download_list.set(item_id, '进度', "0%")
                self.download_list.set(item_id, '速度', "计算中")
                
                # 启动下载线程
                download_thread = threading.Thread(
                    target=self.download_video_thread,
                    args=(video_id, title, format_code, output_dir, item_id)
                )
                download_thread.daemon = True  # 设置为守护线程
                download_thread.start()
                
                download_count += 1
                
            except Exception as e:
                self.logger.error(f"处理视频 {title} 时出错：{str(e)}")
                self.download_list.set(item_id, '状态', "启动失败")
                continue
        
        if download_count > 0:
            # 启用控制按钮
            self.pause_all_btn.state(['!disabled'])
            self.cancel_all_btn.state(['!disabled'])
            
            # 重置下载状态
            self.paused = False
            self.cancelled = False
            self.pause_event.set()
            
            self.logger.info(f"成功启动 {download_count} 个下载任务")
        else:
            messagebox.showwarning("提示", "没有可下载的视频")

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
            self.window.update()
            
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
            self.window.update()
            
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
            self.logger.info(f"弹幕下载状态: {'启用' if danmaku_enabled else '禁用'}")
            
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
            while process.poll() is None and not self.cancelled:
                if self.paused:
                    time.sleep(0.1)  # 暂停时减少CPU使用
                    continue
                
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
                                self.download_list.set(item_id, '进度', f"{progress}%")
                                self.download_list.set(item_id, '速度', speed)
                                last_update = current_time
                                self.window.update()
                        except Exception as e:
                            self.logger.warning(f"解析进度信息失败：{str(e)}")
                            continue
                except Exception as e:
                    self.logger.warning(f"读取输出时出错：{str(e)}")
                    continue
            
            # 如果是取消导致的退出
            if self.cancelled:
                if process and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                
                self.logger.info(f"取消下载视频：{title}")
                self.download_list.set(item_id, '状态', "已取消")
                self.download_list.set(item_id, '进度', "-")
                self.download_list.set(item_id, '速度', "-")
                return
            
            # 检查下载结果
            if process and process.returncode == 0:
                self.logger.info(f"视频 {title} 下载完成")
                self.download_list.set(item_id, '状态', "已完成")
                self.download_list.set(item_id, '进度', "100%")
                self.download_list.set(item_id, '速度', "-")
            else:
                error = process.stderr.read() if process else "未知错误"
                self.logger.error(f"下载失败：{error}")
                self.download_list.set(item_id, '状态', "失败")
                self.download_list.set(item_id, '进度', "-")
                self.download_list.set(item_id, '速度', "-")
                messagebox.showerror("错误", f"下载失败：{error}")
                
        except Exception as e:
            self.logger.error(f"下载过程出错：{str(e)}")
            messagebox.showerror("错误", f"下载过程出错：{str(e)}")
            self.download_list.set(item_id, '状态', "失败")
            self.download_list.set(item_id, '进度', "-")
            self.download_list.set(item_id, '速度', "-")
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
        if messagebox.askyesno("确认", "确定要退出登录吗？"):
            # 清除cookie文件
            if os.path.exists(self.cookies_file):
                os.remove(self.cookies_file)
            
            # 清除cookie数据
            self.cookies = None
            
            # 更新状态显示
            self.login_status.config(text="需要登录", foreground="red")
            
            # 禁用下载相关按钮
            self.download_btn.state(['disabled'])
            self.download_selected_btn.state(['disabled'])
            
            # 清空下载列表
            for item in self.download_list.get_children():
                self.download_list.delete(item)
            
            # 弹出登录窗口
            self.login()

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
            dialog = tk.Toplevel(self.window)
            dialog.title(f"选择下载格式 - {title}")
            dialog.geometry("300x400")
            dialog.transient(self.window)  # 设置为主窗口的临时窗口
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
            self.window.wait_window(dialog)
        
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
        
        # 启用控制按钮
        self.pause_all_btn.state(['!disabled'])
        self.cancel_all_btn.state(['!disabled'])
        
        # 重置下载状态
        self.paused = False
        self.cancelled = False
        self.pause_event.set()

    def process_download_queue(self):
        """处理下载队列的线程"""
        try:
            while not self.download_queue.empty() and not self.cancelled:
                video_id, title, format_code, output_dir, item_id = self.download_queue.get()
                
                # 更新状态
                self.download_list.set(item_id, '状态', "下载中")
                self.download_list.set(item_id, '进度', "0%")
                self.download_list.set(item_id, '速度', "计算中")
                
                # 开始下载
                self.download_video_thread(video_id, title, format_code, output_dir, item_id)
                
                # 等待当前下载完成
                while any(p.poll() is None for p in self.active_processes):
                    time.sleep(0.1)
                    if self.cancelled:
                        break
                
                self.download_queue.task_done()
                
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
                    self.output_dir_var.set(config.get('output_dir', ''))
                    self.download_danmaku.set(config.get('download_danmaku', False))
                    
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
                'output_dir': self.output_dir_var.get().strip(),
                'download_danmaku': self.download_danmaku.get(),
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
            cookies = {
                'SESSDATA': self.sessdata.get().strip(),
                'bili_jct': self.bili_jct.get().strip(),
                'buvid3': self.buvid3.get().strip()
            }
            
            # 验证登录状态
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Cookie': f"SESSDATA={cookies['SESSDATA']}; bili_jct={cookies['bili_jct']}; buvid3={cookies['buvid3']}"
            }
            
            nav_url = 'https://api.bilibili.com/x/web-interface/nav'
            request = urllib.request.Request(nav_url, headers=headers)
            response = urllib.request.urlopen(request)
            content = json.loads(response.read().decode('utf-8'))
            
            if content['code'] == 0:
                # 登录有效，保存cookie文件
                with open('bili_cookies.json', 'w', encoding='utf-8') as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=4)
                self.create_netscape_cookies(cookies)
                
                # 更新UI状态
                self.login_status.config(text=f"已登录：{content['data']['uname']}", foreground="green")
                self.download_btn.state(['!disabled'])
                self.logger.info(f"登录状态有效：{content['data']['uname']}")
                return True
            else:
                self.logger.warning("登录状态已失效")
                self.login_status.config(text="登录已失效", foreground="red")
                return False
                
        except Exception as e:
            self.logger.error(f"验证登录状态失败：{str(e)}")
            self.login_status.config(text="登录状态检查失败", foreground="red")
            return False

    def on_closing(self):
        """窗口关闭时的处理"""
        try:
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
            self.window.destroy()

def main():
    app = BiliFavGUI()
    app.window.mainloop()

if __name__ == '__main__':
    main()  