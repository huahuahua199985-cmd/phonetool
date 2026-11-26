# Windows 打包说明（只需做一次）

1. 在一台 Windows 电脑上安装 **Python 3.12（64 位）**：https://www.python.org/downloads/ ，安装时务必勾选 **Add python.exe to PATH**。
2. 把整个项目文件夹复制到这台电脑。
3. **双击 `build.bat`**，等待几分钟（会自动安装依赖、跑测试、打包）。
4. 完成后得到 `PhoneTool-windows.zip`（里面是 `PhoneTool.exe` 和运行库），发给客户即可。客户解压后双击 `PhoneTool.exe`。

客户首次运行若提示「Windows 已保护你的电脑 / 未知发布者」：点「更多信息」→「仍要运行」。
