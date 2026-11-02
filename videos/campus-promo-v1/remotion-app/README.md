# 课间宣传片 · Remotion 工程

当前入口为 `StylePreview` / `CampusPromoV2`（62秒V2）与 `HomeworkPreview`（15秒V2样段），均为1920×1080、30fps。采用18镜头、深浅场景交替、动态大字、错位卡片、左右分屏与全幅界面，已加入中文旁白、原创电子配乐与转场音效。V1位于`Earlier`文件夹。用户只在浏览器审阅，不需要导出；字幕尚未加入。

声音由 `src/PromoAudio.tsx` 的三个独立音轨控制。首尾淡化与人声期间的音乐降低已写入素材，轨道默认unity音量。若试听没有声音，请检查Studio静音按钮和系统音量；浏览器需要点击播放后开始音频。

运行 `npm run dev -- --port 3010`，打开 `/StylePreview` 或 `/HomeworkPreview`。`npm run lint` 检查 TypeScript 和 ESLint。运行依赖仅用于视频制作，与 App 产品依赖分离。

原始录屏、隔离 profile 和凭据不放入 `public/`。只将检查通过的虚构业务录屏切片放入 `public/footage/`，原始时间码与裁切记录在上级 `work/cuts.json` 和 `edit/edit-spec.json`。当前未导出最终 MP4；切片 MP4 只是本地编辑素材。

<p align="center">
  <a href="https://github.com/remotion-dev/logo">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://github.com/remotion-dev/logo/raw/main/animated-logo-banner-dark.apng">
      <img alt="Animated Remotion Logo" src="https://github.com/remotion-dev/logo/raw/main/animated-logo-banner-light.gif">
    </picture>
  </a>
</p>

Welcome to your Remotion project!

## Commands

**Install Dependencies**

```console
npm i --loglevel=error
```

**Start Preview**

```console
npm run dev
```

**Render video**

```console
npx remotion render
```

**Upgrade Remotion**

```console
npx remotion upgrade
```

## Docs

Get started with Remotion by reading the [fundamentals page](https://www.remotion.dev/docs/the-fundamentals).

## Help

We provide help on our [Discord server](https://discord.gg/6VzzNDwUwV).

## Issues

Found an issue with Remotion? [File an issue here](https://github.com/remotion-dev/remotion/issues/new).

## License

Note that for some entities a company license is needed. [Read the terms here](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md).
