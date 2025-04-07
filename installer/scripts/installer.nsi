; 编码设置
Unicode true

; 安装程序初始定义常量
!define PRODUCT_NAME "B站收藏夹下载器"
!define PRODUCT_VERSION "1.0"
!define PRODUCT_PUBLISHER "Your Name"
!define PRODUCT_WEB_SITE "https://github.com/yourusername/bilibili-fav-downloader"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\B站收藏夹下载器.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

SetCompressor lzma

; 加载AccessControl插件
!include LogicLib.nsh
!addplugindir "Plugins\x86-unicode"

; MUI 现代界面定义
!include "MUI2.nsh"

; MUI 预定义常量
!define MUI_ABORTWARNING
!define MUI_ICON "R.ico"
!define MUI_UNICON "R.ico"

; 欢迎页面
!insertmacro MUI_PAGE_WELCOME
; 许可协议页面
;!insertmacro MUI_PAGE_LICENSE "LICENSE"
; 安装目录选择页面
!insertmacro MUI_PAGE_DIRECTORY
; 安装过程页面
!insertmacro MUI_PAGE_INSTFILES
; 安装完成页面
!define MUI_FINISHPAGE_RUN "$INSTDIR\B站收藏夹下载器.exe"
!insertmacro MUI_PAGE_FINISH

; 卸载过程页面
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; 安装界面包含的语言设置
!insertmacro MUI_LANGUAGE "SimpChinese"

; 安装程序版本号
VIProductVersion "${PRODUCT_VERSION}.0.0"
VIAddVersionKey /LANG=${LANG_SIMPCHINESE} "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey /LANG=${LANG_SIMPCHINESE} "Comments" "B站收藏夹视频下载工具"
VIAddVersionKey /LANG=${LANG_SIMPCHINESE} "CompanyName" "${PRODUCT_PUBLISHER}"
VIAddVersionKey /LANG=${LANG_SIMPCHINESE} "FileVersion" "${PRODUCT_VERSION}"
VIAddVersionKey /LANG=${LANG_SIMPCHINESE} "ProductVersion" "${PRODUCT_VERSION}"

; 程序名称
Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
; 安装程序输出文件名
OutFile "installer\B站收藏夹下载器安装程序.exe"
; 默认安装目录
InstallDir "$PROGRAMFILES\${PRODUCT_NAME}"
; 获取安装目录的父级目录
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
ShowInstDetails show
ShowUnInstDetails show

Section "MainSection" SEC01
    SetOutPath "$INSTDIR"
    SetOverwrite ifnewer
    
    ; 复制主程序文件
    File "dist\B站收藏夹下载器.exe"
    File "README.md"
    File "R.ico"
    
    ; 创建开始菜单快捷方式
    CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\B站收藏夹下载器.exe"
    CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\B站收藏夹下载器.exe"
    
    ; 创建logs目录
    CreateDirectory "$INSTDIR\logs"
    ; 设置logs目录的权限
    ExecWait 'cmd.exe /C icacls "$INSTDIR\logs" /grant Users:(OI)(CI)F'
    
    ; 注册卸载信息
    WriteUninstaller "$INSTDIR\uninst.exe"
    WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\B站收藏夹下载器.exe"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninst.exe"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\B站收藏夹下载器.exe"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
SectionEnd

Section Uninstall
    ; 删除开始菜单快捷方式
    Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
    RMDir "$SMPROGRAMS\${PRODUCT_NAME}"
    
    ; 删除桌面快捷方式
    Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
    
    ; 删除安装目录下的所有文件
    Delete "$INSTDIR\B站收藏夹下载器.exe"
    Delete "$INSTDIR\README.md"
    Delete "$INSTDIR\R.ico"
    Delete "$INSTDIR\uninst.exe"
    RMDir /r "$INSTDIR\logs"
    RMDir "$INSTDIR"
    
    ; 删除注册表信息
    DeleteRegKey HKLM "${PRODUCT_UNINST_KEY}"
    DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"
SectionEnd 