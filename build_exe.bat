@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   原型生成器 - 打包为 EXE
echo ============================================
echo.

:: 进入脚本所在目录
cd /d "%~dp0"

:: 检查 PyInstaller
echo [1/5] 检查 PyInstaller...
pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo       未安装 PyInstaller，正在安装...
    pip install pyinstaller
    if %ERRORLEVEL% neq 0 (
        echo [错误] PyInstaller 安装失败！
        pause
        exit /b 1
    )
)
echo       PyInstaller 已就绪

:: 清理旧构建
echo [2/5] 清理旧构建...
if exist "build" rmdir /s /q "build"
if exist "dist\原型生成器" rmdir /s /q "dist\原型生成器"

:: 执行 PyInstaller 打包
echo [3/5] 正在打包（约1-2分钟）...
pyinstaller ^
    --name "原型生成器" ^
    --noconfirm ^
    --clean ^
    --console ^
    --hidden-import=requests ^
    --hidden-import=urllib3 ^
    --hidden-import=charset_normalizer ^
    --hidden-import=certifi ^
    --hidden-import=idna ^
    server.py

if %ERRORLEVEL% neq 0 (
    echo [错误] 打包失败！
    pause
    exit /b 1
)

:: 复制资源文件到 dist
set DIST_DIR=dist\原型生成器
echo [4/5] 复制资源文件...

:: 前端文件
xcopy "src" "%DIST_DIR%\src\" /E /I /Q >nul
echo       已复制 src/

:: 模板
xcopy "templates" "%DIST_DIR%\templates\" /E /I /Q >nul
echo       已复制 templates/

:: 配置文件（使用示例版，不泄露用户密钥）
if exist "config.example.json" (
    copy "config.example.json" "%DIST_DIR%\config.json" >nul
) else (
    copy "config.json" "%DIST_DIR%\config.json" >nul
)
copy "models.example.json" "%DIST_DIR%\models.json" >nul
echo       已复制配置文件

:: 入口页面
copy "index.html" "%DIST_DIR%\" >nul

:: 辅助脚本
copy "export_project.py" "%DIST_DIR%\" >nul 2>nul
copy "split_to_modao.py" "%DIST_DIR%\" >nul 2>nul

:: 文档
if exist "docs" (
    xcopy "docs" "%DIST_DIR%\docs\" /E /I /Q >nul
    echo       已复制 docs/
)

:: 创建空目录
mkdir "%DIST_DIR%\projects" 2>nul
mkdir "%DIST_DIR%\backups" 2>nul
mkdir "%DIST_DIR%\uploads" 2>nul
mkdir "%DIST_DIR%\exports" 2>nul
mkdir "%DIST_DIR%\data" 2>nul
echo       已创建数据目录

:: 创建 README
echo [5/5] 生成使用说明...
(
echo # 原型生成器 - 独立运行版
echo.
echo ## 快速开始
echo.
echo 1. **配置 AI 模型**
echo    编辑 `models.json`，填入您的模型信息和 API Key
echo    也可以启动后在页面顶栏「模型管理」中可视化配置
echo.
echo 2. **启动**
echo    双击 `原型生成器.exe` 即可！
echo    浏览器会自动打开 http://localhost:8080
echo.
echo 3. **无需安装 Python**
echo    此版本已内置 Python 运行时，开箱即用
echo.
echo ## 注意事项
echo.
echo - 首次配置请编辑 models.json 添加您的 API 密钥
echo - 生成的项目保存在 projects/ 目录中
echo - 关闭命令行窗口即可停止服务
) > "%DIST_DIR%\README.md"

echo.
echo ============================================
echo   打包完成！
echo ============================================
echo.
echo 输出目录: %~dp0%DIST_DIR%
echo.
echo 将 dist\原型生成器 整个文件夹发给别人即可。
echo 对方双击 原型生成器.exe 就能直接使用！
echo.

:: 清理 build 临时目录
rmdir /s /q "build" 2>nul
del "原型生成器.spec" 2>nul

:: 打开输出目录
explorer "%~dp0%DIST_DIR%"

pause
