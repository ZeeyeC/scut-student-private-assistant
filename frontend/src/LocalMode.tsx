import { useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { api } from "./api";
import { Button } from "./components/ui/button";

type ProfileStatus = {
  selected: boolean;
  needs_selection: boolean;
  profiles: { id: string; email: string; resource_count: number }[];
};
export function LocalEntry({ children }: { children: ReactNode }) {
  const q = useQueryClient();
  const [error, setError] = useState("");
  const [choosing, setChoosing] = useState(false);
  const status = useQuery({
    queryKey: ["local-profile"],
    queryFn: () => api<ProfileStatus>("/local/status"),
  });
  const session = useQuery({
    queryKey: ["local-session"],
    enabled: !!status.data && !status.data.needs_selection,
    queryFn: async () => {
      await api("/local/session", { method: "POST", body: "{}" });
      await q.invalidateQueries({ queryKey: ["me"] });
      return true;
    },
    staleTime: Infinity,
    retry: false,
  });
  async function choose(body: object) {
    setChoosing(true);
    setError("");
    try {
      await api("/local/session", {
        method: "POST",
        body: JSON.stringify(body),
      });
      q.setQueryData(["local-session"], true);
      await q.invalidateQueries({ queryKey: ["local-profile"] });
    } catch (e) {
      setError(String(e));
    } finally {
      setChoosing(false);
    }
  }
  if (status.error || session.error)
    return (
      <main className="auth">
        <h1>本地助手暂时无法连接</h1>
        <p role="alert">{String(status.error || session.error)}</p>
        <Button onClick={() => location.reload()}>重新连接</Button>
      </main>
    );
  // A concurrent status read may observe the user commit before LocalProfile.
  // A successful session is authoritative and must not be hidden by that stale read.
  if (status.data?.needs_selection && !session.data)
    return (
      <main className="auth">
        <div className="brand">课间</div>
        <h1>检测到已有资料</h1>
        <p>
          选择要继续使用的本机资料。之后双击启动即可进入，无需邮箱和密码。其他资料会保留，不会合并或删除。
        </p>
        {status.data.profiles.map((p) => (
          <section className="card" key={p.id}>
            <p>
              {p.email} · {p.resource_count} 项记录
            </p>
            <Button
              disabled={choosing}
              onClick={() => choose({ profile_id: p.id })}
            >
              继续使用这份资料
            </Button>
          </section>
        ))}
        <Button
          variant="outline"
          disabled={choosing}
          onClick={() => choose({ create_new: true })}
        >
          新建独立资料，保留原数据
        </Button>
        {error && <p role="alert">{error}</p>}
      </main>
    );
  return session.data ? (
    children
  ) : (
    <main className="auth">
      <p role="status">正在打开本机个人助手…</p>
    </main>
  );
}

type Models = {
  revision: string;
  model_provider: "openai";
  text_model: string;
  vision_model: string;
  model_base_url: string;
  key_configured?: boolean;
  model_api_key: string;
  model_use_system_proxy: boolean;
};
export function LocalSettings() {
  const q = useQueryClient();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const model = useQuery({
    queryKey: ["model-settings"],
    queryFn: () => api<Models>("/local/model-settings"),
  });
  const installation = useQuery({
    queryKey: ["extension-installation"],
    queryFn: () => api<{ can_stop: boolean }>("/local/extension-installation"),
  });
  const { register, handleSubmit, resetField, formState } = useForm<Models>({
    values: model.data
      ? {
          ...model.data,
          text_model: model.data.text_model || "openai/gpt-6-luna",
          vision_model: model.data.vision_model || "openai/gpt-6-luna",
          model_api_key: "",
        }
      : undefined,
  });
  return (
    <section className="card">
      <h2>统一模型连接</h2>
      <p>
        助手对话、任务拆解、作业识别和课表识别共用下方 API 地址与一个密钥。图片功能使用视觉模型；支持图文的同一模型可同时填写在两处。
      </p>
      {model.isPending ? (
        <p>正在读取模型配置…</p>
      ) : model.error ? (
        <p role="alert">{String(model.error)}</p>
      ) : (
        <form
          onSubmit={handleSubmit(async (v) => {
            try {
              setError("");
              const { key_configured: _, ...body } = v;
              await api("/local/model-settings", {
                method: "PUT",
                body: JSON.stringify(body),
              });
              resetField("model_api_key", { defaultValue: "" });
              await q.invalidateQueries({ queryKey: ["model-settings"] });
              await q.invalidateQueries({ queryKey: ["health"] });
              setMessage("模型配置已保存；下一次请求使用新配置。");
            } catch (e) {
              setError(String(e));
            }
          })}
        >
          <input type="hidden" {...register("model_provider")} />
          <label>
            API 地址
            <input required {...register("model_base_url")} />
          </label>
          <div className="grid2">
            <label>
              文本模型
              <input required {...register("text_model")} />
            </label>
            <label>
              视觉模型
              <input required {...register("vision_model")} />
            </label>
          </div>
          <label>
            API 密钥
            <input
              type="password"
              autoComplete="new-password"
              placeholder={
                model.data?.key_configured
                  ? "已配置，留空保留原密钥"
                  : "填写服务商 API 密钥"
              }
              {...register("model_api_key")}
            />
          </label>
          <p>
            密钥仅保存在本机配置文件，不会回显。DeepSeek 可使用 https://api.deepseek.com，文本与视觉均填写 deepseek-flash；其他服务请使用供应商提供的完整模型 ID。
          </p>
          <label className="check"><input type="checkbox" {...register("model_use_system_proxy")} />使用系统环境代理（本机代理不可用时可关闭，仅影响模型请求）</label>
          <Button disabled={formState.isSubmitting}>保存模型配置</Button>
        </form>
      )}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
      {installation.data?.can_stop && (
        <div className="step">
          <p>关闭窗口后后台仍在本机运行。停止后，可双击桌面入口重新打开。</p>
          <Button
            variant="outline"
            onClick={async () => {
              if (!window.confirm("停止本机助手？请先保存正在校对的内容。"))
                return;
              try {
                await api("/local/shutdown", { method: "POST", body: "{}" });
                setMessage("正在停止助手。下次请双击桌面入口重新打开。");
              } catch (e) {
                setError(String(e));
              }
            }}
          >
            停止助手
          </Button>
        </div>
      )}
    </section>
  );
}
