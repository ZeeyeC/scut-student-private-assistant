import { appOrigin } from "../lib/build-config";
import { sendMessage } from "../lib/protocol";
export default defineContentScript({
  matches: [appOrigin + "/*"],
  main(ctx) {
    ctx.addEventListener(window, "message", async (event: MessageEvent) => {
      if (
        event.source !== window ||
        event.origin !== appOrigin ||
        event.data?.channel !== "campus-assistant-v1" ||
        typeof event.data.nonce !== "string"
      )
        return;
      const { action, nonce, requestId, payload } = event.data;
      try {
        let result: unknown;
        if (action === "detect") result = { installed: true };
        else if (action === "start")
          result = await sendMessage("start", { ...payload, nonce });
        else if (action === "restore")
          result = await sendMessage("restore", { ...payload, nonce });
        else if (action === "stop") result = await sendMessage("stop", payload);
        else return;
        window.postMessage(
          { channel: "campus-assistant-reply-v1", nonce, requestId, result },
          appOrigin,
        );
      } catch (e) {
        window.postMessage(
          {
            channel: "campus-assistant-reply-v1",
            nonce,
            requestId,
            error: String(e),
          },
          appOrigin,
        );
      }
    });
  },
});
