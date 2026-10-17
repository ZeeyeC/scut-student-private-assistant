# 视频动作素材

用户指定来源：[奶龙闪身步教学](https://www.bilibili.com/video/BV1uSe16KEfi/)（BV1uSe16KEfi，视频页面署名见原链接）。

`source.mp4` 是本地处理时使用的用户指定公开视频，不随仓库提交；重新提取时需自行准备该源文件。本项目直接提取原视频角色动作，没有用生成图冒充视频动作。

| 动作 | 原视频时间 | 帧数 | 播放速度 |
| --- | --- | --- | --- |
| 闪身步 | 2.10–5.25 秒 | 63 | 20 fps |
| 大抡臂 | 11.05–15.35 秒 | 86 | 20 fps |
| 狗熊哆嗦毛 | 25.60–28.90 秒 | 66 | 20 fps |

“狗熊哆嗦毛”在应用内原速连续播放两遍，总时长为 6.6 秒，不重复存储帧文件。

最后一段选取完整身体可见的镜头，避开之后的近景切换。待机形象也来自同一视频，保持动作前后外形一致；原先生成的角色图片保留为图标与回退素材。

已按蓝色舞台背景做颜色分离、角色连通区域筛选、封闭五官保留、边缘柔化、统一透明画布和站立基线。动作没有声音。原视频背景、字幕和水印位于角色以外，不在最终透明角色帧中。源视频与中间帧仅保留在本地。低清视频的快速运动处仍可能有少量边缘杂色。

## 重新提取

从项目根目录运行（需要 macOS 视频解码服务；输出中间帧到被忽略的 build 目录）：

```bash
xcrun swiftc -module-cache-path build/swift-cache -framework AVFoundation -framework AppKit tools/extract_video.swift -o build/extract-video
build/extract-video art/video/source.mp4 build/video-frames 0.05 0 32.65 720
../backend/.venv/bin/python tools/prepare_actions.py
../backend/.venv/bin/python build.py --reuse-service
```

应用只打包 `Resources/Animations` 的透明帧和清单，不打包原视频和中间帧，也不需要联网加载视频。
