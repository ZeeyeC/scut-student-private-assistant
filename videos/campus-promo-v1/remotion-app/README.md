# 课间宣传片 · Remotion 工程

本轮入口为 `HomeworkPreview`（15秒真实截图整理样段）与 `CampusPromoV1`（75秒无声粗剪），均为1920×1080、30fps；`StylePreview` 保留最初的风格与虚构材料预览。当前已有真实模型响应和确认结果，尚未加入旁白、字幕、音乐或导出最终宣传片。

运行 `npm run dev -- --port 3010`，打开 `/HomeworkPreview` 或 `/CampusPromoV1`。`npm run lint` 检查 TypeScript 和 ESLint。运行依赖仅用于视频制作，与 App 产品依赖分离。

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
