# 课间宣传片制作工程

V2 主版 62 秒，1920 × 1080 / 30fps，已接入中文旁白、原创配乐和转场音效。真实 App 操作，业务内容全部虚构。V1 的75秒版本保留作对照。

**最新交付：**用户通过有声预览并明确授权导出后，已生成`edit/export-v2/课间-宣传片-V2-1080p.mp4`（H.264/AAC，62秒，约7.3MB）。整片解码、黑帧扫描、16个画面抽检及导出音轨比对通过；同目录附SHA256和验证结果。访达可见副本：`/Users/czy/ProjectManagement/agentbuild/exports/课间宣传片-V2/`。仅本地交付，未公开上传。

当前已提供两个可编辑预览：

- `http://localhost:3010/StylePreview` 或 `/CampusPromoV2`：62 秒 V2 有声审片版，18 个镜头与17处转场。
- `http://localhost:3010/HomeworkPreview`：15 秒 V2 截图整理样段。
- V1 在 Studio 的 `Earlier` 文件夹保留。

运行：进入 `remotion-app/`，执行 `npm ci`、`npm run dev -- --port 3010`。旁白、音乐与音效已完成并接入，字幕未加入，用户已通过当前画面和声音并授权导出。录屏切片完成了实际结果核对、CFR 转换与黑帧检查；部分点击动作未完整收录，未将其伪造成连续操作。详情见 `docs/video/campus-promo-v1/V2-节奏与视觉修改.md`与`音频制作方案.md`。

- `materials/`：原创虚构作业截图、课程讲义、演示数据清单。
- `source/`：本轮真实录屏原件，只读保留，不自动提交 Git。
- `work/`：过程记录；`profile/` 是隔离资料，不进入 Git 或发布包。
- `remotion-app/`：独立视频工程。进入后运行 `npm run dev` 预览。
- `edit/`：预览与导出，不与原件混放。
- 方案和录制清单见 `docs/video/campus-promo-v1/`。

视频中的课程、作业与资料均为虚构演示样例。模型响应必须实际运行后录制；尚未录到的画面保持待录，不用测试固定回复代替。

## 模型调用预算

用户已允许当前模型最多 8 次演示请求，仅发送本轮虚构材料。每次发起前后更新 `work/model-requests.json`；不把 API Key 或供应商请求日志放入素材目录。

8 次演示请求已用完（2 次失败、6 次成功）；没有继续发起业务模型调用。个人资料 App 已恢复。音频使用免费Edge TTS与本地原创合成，没有付费服务调用，也不自动公开上传或发布。

## 音频复现

独立环境安装 `work/audio-requirements.txt`，运行 `work/generate-voice.py`（向在线TTS发送旁白文字），再运行 `work/build-audio.py`（仅本地处理）。音轨位于 `remotion-app/public/audio/`，来源见该目录 `SOURCES.md`。逐句时间槽和配乐可编辑；Studio中旁白、音乐、音效为独立轨。`work/validate-audio.py`检查语句边界、声道/长度、响度、峰值及实际Remotion混音。
