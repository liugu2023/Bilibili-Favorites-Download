import os
import subprocess
import sys
import winreg

def get_nsis_path():
    """获取NSIS安装路径"""
    try:
        # 尝试从注册表获取NSIS安装路径
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                          r"SOFTWARE\NSIS") as key:
            install_path = winreg.QueryValueEx(key, "")[0]
            makensis_path = os.path.join(install_path, "makensis.exe")
            if os.path.exists(makensis_path):
                return makensis_path
    except:
        # 尝试常见的安装路径
        common_paths = [
            r"C:\Program Files (x86)\NSIS\makensis.exe",
            r"C:\Program Files\NSIS\makensis.exe",
            r"D:\Program Files (x86)\NSIS\makensis.exe",
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
    
    raise FileNotFoundError("找不到NSIS编译器(makensis.exe)。请确保已安装NSIS。")

def make_installer():
    try:
        # 安装必要的依赖
        print("正在安装依赖...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        
        # 生成可执行文件
        print("正在生成可执行文件...")
        subprocess.call(['python', 'build.py'])
        
        # 运行NSIS编译器
        print("正在创建安装包...")
        makensis_path = get_nsis_path()
        print(f"找到NSIS编译器: {makensis_path}")
        
        # 确保installer目录存在
        os.makedirs('installer', exist_ok=True)
        
        # 使用命令行参数指定UTF-8编码
        result = subprocess.call([makensis_path, '/INPUTCHARSET', 'UTF8', 'installer.nsi'])
        
        if result == 0:
            print("安装包制作完成！")
        else:
            print("安装包制作失败！")
            
    except FileNotFoundError as e:
        print(f"错误: {str(e)}")
        print("请从 https://nsis.sourceforge.io/Download 下载并安装NSIS")
    except Exception as e:
        print(f"发生错误: {str(e)}")

if __name__ == '__main__':
    make_installer() 