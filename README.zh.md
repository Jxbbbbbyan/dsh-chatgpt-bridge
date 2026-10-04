# dsh-chatgpt-bridge

**让 DSH 里的任意模型，都能跟你在浏览器里已经开着的 ChatGPT 对话 —— 靠真实的鼠标移动和真实的键盘输入。**

[English](README.md) · [完整实例](docs/EXAMPLE.md) · [经验教训](docs/LESSONS.md)

---

## 这是什么

不是 API 客户端，而是一座桥。它像人一样操作 **Edge 里停靠的 ChatGPT 边栏**：用 UI Automation
瞄准，用 `SendInput` 点击，用 `SendInput` 打字，再从无障碍树里把回复读回来。不需要 API key，
不注入 JavaScript，不用 DevTools 协议，不装浏览器扩展。

所以它能用在 API 到不了的地方：你自己的登录态、你自己的订阅、你界面上已有的模型选择和模式，
包括 ChatGPT 自己的文件和图片附件。

```
  DSH 模型  ──►  skills + 命令行  ──►  SendInput（真实鼠标/键盘）  ──►  Edge 边栏（ChatGPT）
                       ▲                                                     │
                       └──────────  UI Automation 无障碍树（读回复）  ◄────────┘
```

## 为什么这样设计

| 层 | 选择 | 理由 |
|---|---|---|
| **瞄准** | 对 Edge 窗口做 UI Automation | 边栏会暴露 `DocumentControl` 和 `EditControl`，目标是精确矩形，不需要模板匹配，也不需要计算机视觉 |
| **动作** | Windows `SendInput`（`MOUSEEVENTF_ABSOLUTE \| VIRTUALDESK` + `KEYEVENTF_UNICODE`） | 事件以硬件同样的路径到达应用；中文等任意字符原样送达，不用剪贴板中转 |
| **时序** | 人类化输入模型 | 最小 jerk 轨迹（含过冲与修正）+ 对数正态击键间隔，而不是瞬移加倾倒 |
| **读取** | 无障碍树，不做 OCR | 文本确定，不需要解析截图、不需要剪贴板、不需要 OCR 语言包 |
| **校验** | 每个"提交性动作"前先断言 | 打字前确认焦点，回车前确认内容 |

以上每一条都是**实测结论**，不是设想：替代方案都在实践中失败过。见 [docs/LESSONS.md](docs/LESSONS.md)。

## 快速开始

环境：Windows、**Edge 且 ChatGPT 边栏已打开**、Python 3.11+，解释器里要有 `uiautomation` 和 `Pillow`。

```powershell
git clone https://github.com/Jxbbbbbyan/dsh-chatgpt-bridge
cd dsh-chatgpt-bridge
pip install -e .

dsh-chatgpt-bridge find            # 定位边栏、文档与输入框
dsh-chatgpt-bridge read            # 当前对话转录（已去掉界面噪声）
dsh-chatgpt-bridge ask "Reply with just the word: OK"
```

`ask` 会：移动光标 → 点击输入框 → **确认焦点真的在输入框** → 打字 → **确认内容与预期一致** →
回车 → 等待新的助手消息稳定 → 打印回复。

"拒绝打字"和"拒绝发送"是特性而非缺陷。两道闸都是因为真实事故才加上的：一次点空会把提示词喷进
当时有焦点的任意窗口；一次内容错乱会把坏消息发出去。

## 附件与长图

```powershell
dsh-chatgpt-bridge attach-files slices\slice-0*.png     # 真实 UI：+ → Files and folders → 打开对话框
dsh-chatgpt-bridge ask --prompt-file brief.txt          # 提示词从 UTF-8 文件读取
```

超过约 2000 px 的长图会被聊天界面**压缩到字都看不清**。`slicer` 把它切成带重叠、仍然清晰可读的切片：

```powershell
python -m dsh_chatgpt_bridge.slicer long-screenshot.jpg slices
```

一次 640×8260 的截图切出 6 张 640×1700 的切片，再按字符长度分批挂载 —— 因为文件对话框的
"文件名"框会在约 256 字符处**静默截断**。完整流程与四条关键规则在
[docs/LONG-SCREENSHOTS.md](docs/LONG-SCREENSHOTS.md)。

## 安全模型

真实输入意味着运行期间人无法使用自己的机器。因此：

- **Escape 是急停键**，每个事件发出前都会检查
- 每次运行都有**时间、事件数、光标距离三重上限**
- 运行结束或中止后**光标会还原**
- 工具**宁可中止也不猜**：没有焦点就不打字，内容不符就不回车

它驱动的是**你自己**的会话和账号，不是绕过某个服务控制手段的工具，也不应被用于非本人的账号。

## 完整实例

仓库里提交了一次真实的完整运行：一张 **640×8260 px** 的文章长截图，切成 6 张图，配一份书面要求
送进边栏，得到一篇 **3869 字的中文驳论文** —— 全部由 ChatGPT 写成。

- [docs/EXAMPLE.md](docs/EXAMPLE.md) —— 逐步台账，以及每条硬性要求的核验
- [examples/undergrad-rebuttal/](examples/undergrad-rebuttal/) —— 要求原文、追问、成稿、6 张切片，
  以及 ChatGPT 的**逐字转录**

## 这不是什么

- 不是 API 客户端，也不是 API 客户端的封装
- 不是通用浏览器自动化框架 —— 它只针对这一个界面
- 不是隐蔽工具：没有指纹伪装、没有验证码处理、没有代理轮换
- 不是有 API 时的替代品 —— 它存在是为了那些能力只在浏览器里、别处都没有的场景

## 仓库结构

| 路径 | 内容 |
|---|---|
| `src/dsh_chatgpt_bridge/core.py` | 引擎与命令行（瞄准、动作、时序、读取、校验） |
| `src/dsh_chatgpt_bridge/browser.py` | 通用 Chromium 驱动（用于 GitHub 控制台操作） |
| `src/dsh_chatgpt_bridge/slicer.py` | 长图 → 可读可上传的切片 |
| `skills/` | 三个 DSH 技能：工具参考、带门禁的交付流程、GUI 输入硬规则 |
| `docs/` | 指南、长图流水线、经验教训、完整实例 |
| `examples/undergrad-rebuttal/` | 已提交的实例，含 ChatGPT 原始输出 |
| `tools/` | 用来发现并刻画该界面的诊断探针 |

## 许可证

MIT，见 [LICENSE](LICENSE)。
