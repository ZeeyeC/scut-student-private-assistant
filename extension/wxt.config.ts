import { defineConfig } from "wxt";
import { readFileSync, writeFileSync } from "node:fs";
const appOrigin = new URL(process.env.PUBLIC_ORIGIN ?? "http://127.0.0.1:5173")
  .origin;
const adapter = process.env.SCUT_ADAPTER_PATH
  ? JSON.parse(readFileSync(process.env.SCUT_ADAPTER_PATH, "utf8"))
  : null;
if (adapter) {
  const url = new URL(adapter.entry_url);
  const query = Array.from(url.searchParams.entries()).sort();
  const observedRoute =
    url.hostname === "xsjw2018.jw.scut.edu.cn" &&
    ((url.pathname === "/" && !url.search) ||
      (url.pathname === "/jwglxt/kbcx/xskbcx_cxXskbcxIndex.html" &&
        JSON.stringify(query) ===
          JSON.stringify([
            ["gnmkdm", "N2151"],
            ["layout", "default"],
          ])));
  if (
    !adapter.verified ||
    !(
      url.protocol === "https:" ||
      (url.protocol === "http:" && observedRoute)
    ) ||
    !url.hostname.endsWith(".scut.edu.cn") ||
    (url.search && !observedRoute) ||
    url.username ||
    url.password ||
    url.port ||
    url.origin !== adapter.school_origin
  )
    throw new Error("学校配置必须经过实测并限定华工精确域名");
}
writeFileSync(
  new URL("./lib/build-config.ts", import.meta.url),
  `export const appOrigin = ${JSON.stringify(appOrigin)};\nexport const adapter: null | {[key:string]:unknown;kind?:string;visibility_selector?:string;version:string;entry_url:string;school_origin:string;container_selector:string;semester_selector:string;loading_selector:string;route_pattern?:string} = ${JSON.stringify(adapter)};\n`,
);
export default defineConfig({
  outDir: process.env.WXT_OUT_DIR ?? ".output",
  manifest: {
    name: "课间 · 华工课表桥接",
    description: "由助手发起，经本人登录后只读提取课表",
    permissions: ["storage", "alarms"],
    host_permissions: [
      appOrigin + "/*",
      ...(adapter ? [adapter.school_origin + "/*"] : []),
    ],
  },
});
