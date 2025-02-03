import os
import sys
import shutil
import subprocess
from subprocess import call

def build():
    # 清理之前的构建
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    if os.path.exists('build'):
        shutil.rmtree('build')
        
    # 获取Python安装路径
    python_path = os.path.dirname(sys.executable)
    python_exe = os.path.join(python_path, 'python.exe')
    pythonw_exe = os.path.join(python_path, 'pythonw.exe')
    you_get_path = os.path.join(python_path, 'Lib', 'site-packages', 'you_get')
    
    # 使用PyInstaller打包
    cmd = [
        'pyinstaller',
        '--name=B站收藏夹下载器',
        '--windowed',  # 无控制台窗口
        '--icon=R.ico',  # 设置程序图标
        '--add-data=README.md;.',  # 添加说明文档
        '--hidden-import=urllib3',
        '--hidden-import=requests',
        '--hidden-import=tkinter',
        '--hidden-import=json',
        '--hidden-import=logging',
        '--hidden-import=subprocess',
        '--hidden-import=threading',
        '--hidden-import=queue',
        '--collect-all=you_get',  # 收集you-get的所有依赖
        '--collect-all=urllib3',
        '--collect-all=requests',
        '--collect-all=certifi',
        '--collect-all=chardet',
        '--collect-all=idna',
        '--collect-all=charset_normalizer',
        f'--add-binary={python_exe};.',  # 添加Python解释器（使用实际路径）
        f'--add-binary={pythonw_exe};.',  # 添加Python解释器无控制台版本
        f'--add-data={you_get_path};you_get',  # 添加you-get库
        '--onefile',  # 打包成单个文件
        'Bilibili_fav_downloader.py'
    ]
    
    # 确保you-get已安装
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'you-get'])
    except:
        print("安装you-get失败，请检查网络连接")
        sys.exit(1)
    
    # 运行打包命令
    call(cmd)
    
    # 复制必要文件到dist目录
    dist_dir = os.path.join('dist', 'B站收藏夹下载器')
    
    # 创建目录
    os.makedirs(os.path.join(dist_dir, 'logs'), exist_ok=True)
    
    # 复制说明文档
    shutil.copy('README.md', dist_dir)

if __name__ == '__main__':
    build() 