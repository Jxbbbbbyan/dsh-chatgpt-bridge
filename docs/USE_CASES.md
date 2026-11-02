# ChatGPT sidebar automation — capabilities and evidence

[English overview](../README.md) · [中文说明](../README.zh.md)

## Technical route / 技术路线

DeepSeek Harness (DSH) skills → Python CLI → Windows UI Automation targeting → SendInput mouse/keyboard actions → accessibility-tree reply extraction. Attachment workflows use the visible file dialog; long screenshots can be split into overlapping images.

## Where this helps / 能解决什么

| Need / 需求 | Useful feature / 作用 | Evidence / 证据 |
|---|---|---|
| Agent-to-browser prompt delivery / 代理向浏览器交付提示词 | Existing logged-in Edge ChatGPT sidebar; CLI find/read/ask commands | [Engine and CLI](../src/dsh_chatgpt_bridge/core.py) |
| Reply extraction without OCR / 不用 OCR 读取回复 | Extract text from the accessibility tree | [Setup and usage](../README.md#quick-start) |
| Focus and prompt verification / 焦点与内容校验 | Guard typing and submission; fail when the check does not match | [Lessons](LESSONS.md) |
| Long screenshot to ChatGPT / 长图附件交付 | Overlapping slices and length-bounded attachment batches | [Long screenshots](LONG-SCREENSHOTS.md) |
| Inspect a real delivery / 看真实交付结果 | Committed brief, slices, transcript and final output | [Worked example](EXAMPLE.md) |

Search terms describe these capabilities: **ChatGPT UI automation, Microsoft Edge sidebar, Windows accessibility, UI Automation, SendInput, DSH agent skills, file upload, screenshot slicing, prompt delivery, reply extraction**. 中文：ChatGPT 侧栏自动化、真实鼠标键盘、无障碍树、长图切片、附件上传、回复读取。

## Fit and boundaries / 适用范围

Requires Windows, Python 3.11+, an interactive desktop and the compatible Edge ChatGPT sidebar already open. It does not promise unattended or headless operation. UI/localisation changes may break lookup or truncate extracted text. Input checks reduce mistakes but cannot prevent all focus theft. Account permissions, quotas and service terms still apply. Diagnostic screenshots may contain private content.

这是对特定交互界面的桥接工具；上述优势来自实现与已有案例，没有跨版本成功率或速度对比基准。
