import { appOrigin } from "../lib/build-config";
import { sendMessage } from "../lib/protocol";
import {importPageAllows} from "../lib/app-message";
export default defineContentScript({
  matches: [appOrigin + "/*"],
  runAt: "document_start",
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
      if(!importPageAllows(location.pathname,action,payload))return;
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
