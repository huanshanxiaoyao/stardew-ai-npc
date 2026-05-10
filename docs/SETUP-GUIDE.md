# 给星露谷玩家的安装指南

> 让你的 NPC 真正"活"起来 —— 不再是固定剧本的同一句话，而是会聊天气、关心你的婚事、记得你昨天答应的任务的 AI。
>
> *Setup guide for Stardew Valley fans, written in Chinese for the author's friends. The commands are universal; if you read English, the structure should still be followable.*

---

## 这是什么？

一个星露谷物语的 mod，把 NPC 的对话接到了 AI（DeepSeek）。每次你跟 NPC 说话，AI 会根据你当前游戏的实际情况（春天还是冬天？下雨吗？你结婚了吗？正在做什么任务？）生成一句符合人设的回复。

你看到的样子和原版几乎一样 —— 还是同样的对话框、同样的字体，但内容换成了 AI 写的。如果你不想用 AI 了，把后台关掉，游戏立刻退回原版对话，**不会破坏存档**。

## 你需要准备什么

| | 说明 |
|---|---|
| 一台 Mac | M1/M2/M3 都可以；目前只支持 macOS（Windows/Linux 暂不支持） |
| 星露谷物语（Steam 版） | 从 Steam 正版安装的 |
| 一个 DeepSeek 账号 | 注册免费，自己充值；聊一晚上几毛钱到一两块钱（详见末尾费用一节） |
| 大约 30 分钟 | 一次性安装；之后每次玩游戏多 5 秒钟启动一个后台程序 |

如果你之前装过其他 SMAPI mod（比如 Lookup Anything、CJB Cheats Menu），那 SMAPI 部分可以跳过，直接从第 2 步开始。

---

## 第 1 步：装 SMAPI（如果还没装）

SMAPI 是星露谷物语的 mod 加载器。**所有**星露谷的 mod 都靠它运行。

去官网按指南装：**https://smapi.io**

下载 Mac 版的安装包，双击运行 `install on Mac.command`，按提示走完即可。装完之后，从 Steam 启动游戏时会先弹一个黑色控制台窗口（那是 SMAPI），然后才是游戏 —— 这是正常的。

## 第 2 步：打开 Terminal

按 **Cmd + 空格**，输入 "terminal"，回车。会出现一个黑色（或白色）的窗口。这就是终端。

接下来的所有命令都在这个窗口里执行。**复制 → 粘贴 → 回车**就行，不用手敲。

## 第 3 步：装两样底层工具

复制粘贴下面这一行，回车，等它跑完（可能要 1–3 分钟）：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

这是 Homebrew —— Mac 上的"应用商店"，给开发者用的。装的过程中可能会让你输入 Mac 的开机密码（输了不会显示，正常的，盲打回车）。

装完之后，再粘贴下面这行，回车：

```bash
brew install python@3.11 dotnet@6 git
```

这会同时装 Python（运行 AI 后台需要）、.NET 6（编译 mod 需要）、git（下载代码需要）。又是几分钟。

## 第 4 步：申请 DeepSeek API key

1. 去 **https://platform.deepseek.com** 注册账号
2. 登录后点左侧的 "API Keys"
3. 点 "Create new API key"，给它起个名字（比如 "stardew"）
4. **复制那串 sk-xxxxxx 的字符串** —— 这就是 API key
5. 顺便去 "Top up"（充值）页面充 1 块钱测试用 —— 微信/支付宝都行

⚠️ **API key 等于密码**：别发给任何人，别上传到网上。后面我们会把它放在一个本地文件里，只你自己看得到。

## 第 5 步：下载这个 mod

继续在 Terminal 里粘贴：

```bash
cd ~/Documents
git clone https://github.com/huanshanxiaoyao/stardew-ai-npc.git
cd stardew-ai-npc
```

这会把代码下载到 `~/Documents/stardew-ai-npc/` 这个文件夹。

> 不想用 git？也可以直接到 https://github.com/huanshanxiaoyao/stardew-ai-npc 点绿色的 "Code" 按钮 → "Download ZIP"，解压到 `~/Documents/`，然后在 Terminal 里 `cd ~/Documents/stardew-ai-npc-main` 进去。

## 第 6 步：把你的 API key 填进去

粘贴：

```bash
cp bridge/.env.example bridge/.env
open -e bridge/.env
```

最后一行会用文本编辑器打开一个文件，里面只有一行：

```
DEEPSEEK_API_KEY=
```

把你刚才复制的 sk-xxxxxx 粘到等号后面（**没有空格、没有引号**），变成：

```
DEEPSEEK_API_KEY=sk-abc123def456...
```

按 **Cmd+S** 保存，关掉编辑器。

## 第 7 步：编译并安装 mod（一次性）

粘贴：

```bash
./scripts/install_mod.sh
```

这一步会编译 C# 代码（第一次会下载一些依赖，慢一点，一两分钟）然后把 mod 复制到 SMAPI 的 Mods 文件夹里。

跑完之后最后一行应该是：

```
Installed to: /Users/<你的用户名>/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/Mods/StardewAiMod
```

看到这行就成功了 ✅

---

## 每次玩游戏的步骤

装好之后，**每次你想用 AI 对话**：

### 启动 AI 后台

打开 Terminal，粘贴：

```bash
cd ~/Documents/stardew-ai-npc
./scripts/run_bridge.sh
```

看到 `listening on ws://127.0.0.1:8765` 就 OK。**让这个 Terminal 一直开着**（不要关、不要 Ctrl+C），最小化它就行。

### 启动游戏

从 Steam 正常启动星露谷物语。

进入存档后，你会在 SMAPI 控制台（启动游戏时弹的黑色窗口）看到：

```
[Stardew AI Mod] StardewAiMod loaded; Harmony + bridge active.
[Stardew AI Mod] Bridge: connected.
```

走到任意 NPC 面前，按动作键（默认是右键 / Mac 上是 ctrl+点击 / 或者方向键）。屏幕中央会先出现一个 `…` 等待框，1–3 秒后变成 AI 写的回复。✨

### 不想用 AI 时

切到那个 Terminal 窗口，按 **Ctrl+C**。AI 后台关闭。游戏里再点 NPC，会回到原版对话，**不会崩溃**。下次想用就再 `run_bridge.sh` 一次。

---

## 常见问题

### NPC 还是出原版对话，没出 AI 回复

最可能：**AI 后台没启动**或**没连上**。看 Terminal 窗口：
- 没有 `listening on ws://...` 这行 → 后台没跑起来；重新执行 `./scripts/run_bridge.sh`
- 有 `listening` 但没有 `client connected: ...` → 游戏没连上 mod；试试重启游戏
- 都有但仍然是原版 → 看 SMAPI 控制台是否有 `Loaded mod StardewAiMod`，没有就是 mod 没装好，重跑 `./scripts/install_mod.sh`

### 等待框出现了但一直转圈，不出回复

可能性：
1. **API key 错了**：检查 `bridge/.env` 文件里的 key 是否完整（开头是 `sk-`）
2. **DeepSeek 余额不足**：去 platform.deepseek.com 充值
3. **网络不通**：DeepSeek 在国内访问通常没问题，但要确保你能正常上网
4. **超时**：等 12 秒会显示 "(NPC didn't speak)"，是兜底

错误消息会出现在 AI 后台 Terminal 里，可以贴出来求助。

### 我想换成中文回复

打开 `bridge/bridge/llm.py`，找到这一段：

```python
system = (
    f"You are {npc_name} from Stardew Valley. "
    f"The player {player_name} just talked to you in {location}. "
    f"Reply in 1-2 short sentences, in character, in English."
)
```

把最后的 `in English` 改成 `in Chinese`，保存。在 Terminal 里 Ctrl+C 关掉后台，再 `./scripts/run_bridge.sh` 重启。**不需要重启游戏**。

### 我想让 NPC 知道更多事情

目前 NPC 知道：今天日期、季节、星期、天气、你的配偶、你最多 5 个未完成任务。
不知道的：好感度、你的钱、背包里的物品、农场建筑、过去的对话记录（重启后台后清空）。

加更多信息需要改代码，参考 `docs/superpowers/specs/2026-05-09-state-injection-design.md`。

### 费用大概多少

DeepSeek 当前价格（2026 年 5 月）：每百万输入 token 约 ¥1，每百万输出 token 约 ¥2。

每次 NPC 对话大概用 200–500 个 token。**一晚上聊 200 句 ≈ 几毛钱**。聊一年也就几十块。

可以登录 platform.deepseek.com 看实时用量。

### 隐私 / 数据

- 你的 API key 只存在本地的 `bridge/.env` 文件，不会上传任何地方
- 每次对话内容会发给 DeepSeek 的服务器（这是 LLM 的工作方式）
- 桥接程序本身**不**记录任何对话到磁盘 —— Terminal 里的日志关掉就没了
- 不收集任何遥测数据

### 想反馈 bug / 提建议

去 https://github.com/huanshanxiaoyao/stardew-ai-npc/issues 提 issue。

---

## 一句话备忘

下次再玩，只需要做两件事：

```bash
cd ~/Documents/stardew-ai-npc && ./scripts/run_bridge.sh
```

然后从 Steam 启动游戏。其他的不用动。

祝玩得开心 🌾
