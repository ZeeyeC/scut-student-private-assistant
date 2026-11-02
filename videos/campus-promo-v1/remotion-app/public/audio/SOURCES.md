# 音频来源

## 中文旁白

- 文案：本轮原创宣传文案，记录在视频工程 `work/voiceover-script.json`。
- 引擎：`rany2/edge-tts` 7.3.1，Microsoft Edge 在线 TTS。
- 声音：`zh-CN-XiaoxiaoNeural`，语速 +8%，音高不变。
- 处理：仅修剪句首/句尾静音、轻量淡入淡出、响度处理；18句均完整落入时间槽，未对主版语句作额外变速。
- 传输内容仅为宣传文案；未使用 App API Key、个人课程、截图或讲义，没有调用付费语音 API。
- 客户端来源：[rany2/edge-tts](https://github.com/rany2/edge-tts)。客户端开源许可与在线声音/输出使用范围分开，当前文件用于浏览器审片，不代表取得独立无条件商用声音授权。

## 背景音乐与音效

由本轮 `work/build-audio.py` 使用 Python、NumPy、FFmpeg 原创合成，没有使用第三方歌曲或声音采样。

- 120 BPM；F# minor / D / A / E 和声，合成铺底、分解音、低音与轻节拍。
- 转场滑动与落点音来自合成噪声、包络与正弦音。
- 人声期间伴奏自动降低，成片首尾淡入淡出。
- 不模仿指定歌曲、演唱者或真实人物声音。

## 文件与编辑

- `voice-01.wav`至`voice-18.wav`：逐句处理后的旁白，便于修改时序。
- `main-voice/music/sfx.mp3`：62秒主版的独立三音轨。
- `sample-voice/music/sfx.mp3`：15秒样段的独立三音轨。
- `main-mix.mp3`、`sample-mix.mp3`：内部参考混音，Studio仍使用分离音轨。
- 时间槽、SHA256、处理长度见工程 `work/audio-manifest.json`；技术验证见 `work/audio-validation.json`。

当前仅生成音频素材并接入预览，没有导出视频，也没有公开上传。
