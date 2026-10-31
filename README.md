# 长征启动器

一个自己写的 Minecraft 启动器：Python 后端 + 本地网页界面 + Electron 外壳，长得像一个桌面软件，不是浏览器标签页。

## 它有什么

- **版本**：从 2009 年的远古版本到最新正式版全都能装，支持 Forge / Fabric / NeoForge / OptiFine，按版本隔离启动。
- **下载**：原版按「最新正式版 / 正式版 / 快照 / 远古」分组；模组、光影、资源包、整合包直接给热门榜，不用搜也能挑。
- **中文名**：模组名自动查 MC百科，查不到按词表拼，最后走机翻，列表里显示中文、下面跟英文原名。
- **小助手**：会说人话的搜索（「有没有让帧数高一点的模组」），不满意说「再推荐几个」接着翻；能读崩溃日志自动修（重复 mod 挪走、缺前置补上、内存不足提示）；还能按需求生成模组/插件骨架。
- **拖放**：文件拖进小助手页面就能传上去，然后一句话让它导入。
- **联机**：三步开服，可切「正版校验」；勾上是只有正版能进，不勾就是离线模式。
- **整合包**：导出当前版本的整合包（可选带不带游戏设置和启动器设置），导入别人的 zip / mrpack。
- **体检**：Java、内存、磁盘、目录权限、网络一次查完；mod 管理支持多选、批量启停、排序、搜索。
- **存档与截图**：存档跟版本隔离，截图汇总所有位置，按月分组。

## 怎么跑（源码）

```bash
python backend.py        # 只起后端，浏览器开 http://127.0.0.1:8765
python main.py           # 起后端并开一个窗口
```

依赖：`pip install certifi pillow`（打包才需要 pyinstaller）。

## 怎么用 Electron 外壳

```bash
cd electron
pnpm install            # 或 npm install
# 先把 backend.py 打包成 长征引擎.exe 放到上一级目录
npx electron .
```

## 打包

```bash
pyinstaller --onefile --windowed --name 长征引擎 --add-data "web;web" --runtime-tmpdir run backend.py
```

## 自动更新

在 `version.json` 里改版本号：

```json
{"version": "1.0.0", "download": "https://example.com/app.zip", "notes": "改了什么"}
```

启动器设置页填这个文件的地址，点「检查更新」就会比对。

## 说明

个人项目，只给自己和朋友用。游戏本体和模组版权归各自作者，这个仓库里不包含任何游戏文件。
