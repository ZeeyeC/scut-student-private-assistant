import { useState, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { Button } from "./components/ui/button";
type Installation = { available: boolean; directory: string };
export function ImportGuide({
  open,
  onOpenChange,
  phase,
  onDetect,
  onContinue,
  busy,
  error,
  children,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  phase: "checking" | "missing" | "ready";
  onDetect: () => void;
  onContinue: () => void;
  busy: boolean;
  error: string;
  children: ReactNode;
}) {
  const [notice, setNotice] = useState("");
  const mode = useQuery({
    queryKey: ["app-mode"],
    queryFn: () => api<{ mode: string }>("/app-mode"),
  });
  const installation = useQuery({
    queryKey: ["extension-installation"],
    enabled: open && mode.data?.mode === "local",
    queryFn: () => api<Installation>("/local/extension-installation"),
  });
  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setNotice("已复制，请粘贴到对应位置。");
    } catch {
      setNotice("复制失败，请选中下方文字手动复制。");
    }
  }
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="import-dialog">
          <header>
            <div>
              <p className="eyebrow">一步一步完成 · 首次约 2 分钟</p>
              <Dialog.Title asChild>
                <h2>导入华工课表</h2>
              </Dialog.Title>
            </div>
            <Dialog.Close asChild>
              <Button variant="outline" aria-label="关闭导入引导">
                关闭
              </Button>
            </Dialog.Close>
          </header>
          <Dialog.Description>
            在这台电脑的 Chrome 或 Edge
            中操作。学校登录、验证码和学期选择由你完成；助手只读取课表容器。
          </Dialog.Description>
          <ol className="guide-progress">
            <li>连接扩展</li>
            <li>本人进入课表</li>
            <li>校对并保存</li>
          </ol>
          <div className="guide-body">
            {phase === "checking" && <p>正在检测课表扩展，请稍候…</p>}
            {phase === "missing" && (
              <section>
                <h3>安装课表扩展</h3>
                <p>
                  首次需要安装一次，之后可直接导入。Safari
                  可以管理助手数据，导入课表请切换到 Chrome 或 Edge。
                </p>
                <div className="guide-address">
                  <div>
                    <strong>Chrome</strong>
                    <code>chrome://extensions</code>
                    <Button
                      variant="outline"
                      onClick={() => copy("chrome://extensions")}
                    >
                      复制 Chrome 地址
                    </Button>
                  </div>
                  <div>
                    <strong>Edge</strong>
                    <code>edge://extensions</code>
                    <Button
                      variant="outline"
                      onClick={() => copy("edge://extensions")}
                    >
                      复制 Edge 地址
                    </Button>
                  </div>
                </div>
                <ol className="guide-instructions">
                  <li>复制上方对应地址，在浏览器地址栏粘贴并打开。</li>
                  <li>
                    开启页面上的<strong>开发者模式</strong>，点击
                    <strong>加载已解压的扩展程序</strong>（Edge
                    中为“加载解压缩的扩展”）。
                  </li>
                  <li>
                    选择下面的扩展文件夹。请选择整个文件夹，不选择其中某个文件。
                  </li>
                  <li>回到助手，刷新网页，再点击“重新检测扩展”。</li>
                </ol>
                <div className="directory">
                  <strong>扩展文件夹</strong>
                  <code>
                    {installation.data?.directory ??
                      "extension/.output/chrome-mv3"}
                  </code>
                  {mode.data?.mode === "local" &&
                  installation.data?.available ? (
                    <div className="guide-actions">
                      <Button
                        variant="outline"
                        onClick={async () => {
                          try {
                            await api("/local/open-extension-folder", {
                              method: "POST",
                              body: "{}",
                            });
                            setNotice(
                              "已请求系统显示扩展文件夹，请在浏览器中选择此目录。",
                            );
                          } catch (e) {
                            setNotice(String(e));
                          }
                        }}
                      >
                        打开扩展文件夹
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => copy(installation.data!.directory)}
                      >
                        复制文件夹路径
                      </Button>
                    </div>
                  ) : (
                    <p>
                      若目录不存在，请使用附带扩展的桌面包，或按项目说明先构建扩展。
                    </p>
                  )}
                </div>
                <Button disabled={busy} onClick={onDetect}>
                  重新检测扩展
                </Button>
              </section>
            )}
            {phase === "ready" && (
              <section>
                <h3>课表扩展已连接</h3>
                <ol className="guide-instructions">
                  <li>点击下方按钮，扩展将打开并聚焦华工教务主入口。</li>
                  <li>
                    本人登录，完成验证码。进入
                    <strong>信息查询 → 学生课表查询 / 个人课表</strong>
                    。若菜单名称不同，请找到显示本人课程的课表页。
                  </li>
                  <li>
                    选择学年、学期，点击<strong>查询</strong>
                    。扩展会等待表格加载完成。学校菜单新开的课表标签页也会自动关联，请保留教务入口页直到出现预览。
                  </li>
                  <li>
                    回到助手校对课程、周次、节次和地点，再确认保存。请在设置中核对开学日期和节次时间。
                  </li>
                </ol>
                <Button disabled={busy} onClick={onContinue}>
                  {busy ? "正在请求扩展开页…" : "打开教务并继续"}
                </Button>
                <p className="hint">
                  重复点击会继续当前有效导入。关闭这个引导不会取消导入。
                </p>
              </section>
            )}
            {notice && <p>{notice}</p>}
            {error && <p role="alert">{error}</p>}
            {children}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
