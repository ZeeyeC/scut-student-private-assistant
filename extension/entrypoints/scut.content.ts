import { appOrigin, adapter } from "../lib/build-config";
import { sendMessage } from "../lib/protocol";
import { captureContainer } from "../lib/extract";
import { captureScutList } from "../lib/scut-list";
export default defineContentScript({
  matches: [(adapter?.school_origin ?? appOrigin) + "/*"],
  main(ctx) {
    if (!adapter) return;
    const config = adapter;
    let queriedSession = "",
      queryAt = 0,
      queryMutated = false;
    const onQuery = async (e: MouseEvent) => {
      if (
        !e.isTrusted ||
        !(e.target instanceof Element) ||
        !e.target.closest("#search_go")
      )
        return;
      queryAt = Date.now();
      queryMutated = false;
      queriedSession = "";
      const binding = await sendMessage("binding");
      if (binding) queriedSession = binding.sessionId;
    };
    const onTermChange = (e: Event) => {
      if (e.target instanceof Element && e.target.matches("#xnm, #xqm"))
        queriedSession = "";
    };
    if (config.kind === "scut-zf-list") {
      document.addEventListener("click", onQuery, true);
      document.addEventListener("change", onTermChange, true);
    }
    let last = "",
      stableSince = 0,
      running = false;
    const inspect = async () => {
      if (running) return;
      running = true;
      try {
        const binding = await sendMessage("binding");
        if (!binding || binding.captured) return;
        if (
          config.route_pattern &&
          !new RegExp(config.route_pattern).test(location.pathname)
        )
          return;
        const node = document.querySelector(config.container_selector),
          semester = document
            .querySelector(config.semester_selector)
            ?.textContent?.trim();
        const visible = (element: Element | null) =>
          !!element &&
          element.checkVisibility({
            checkOpacity: true,
            checkVisibilityCSS: true,
          });
        const visibleCourse = config.visibility_selector
          ? Array.from(
              document.querySelectorAll(config.visibility_selector),
            ).some(visible)
          : visible(node);
        if (
          !visibleCourse ||
          !semester ||
          (config.loading_selector &&
            visible(document.querySelector(config.loading_selector)))
        )
          return;
        await sendMessage("school", { kind: "waiting_timetable" });
        if (config.kind === "scut-zf-list") {
          if (
            queriedSession !== binding.sessionId ||
            !queryMutated ||
            Date.now() - queryAt < 1500
          )
            return;
          const year = document
            .querySelector<HTMLSelectElement>("#xnm")
            ?.selectedOptions[0]?.textContent?.trim();
          const term = document
            .querySelector<HTMLSelectElement>("#xqm")
            ?.selectedOptions[0]?.textContent?.trim();
          if (
            !year ||
            !term ||
            semester.replace(/\s/g, "") !== `${year}学年第${term}学期`
          )
            return;
        }
        const fragment =
          config.kind === "scut-zf-list"
            ? captureScutList(document)
            : captureContainer(document, config.container_selector);
        if (fragment !== last) {
          last = fragment;
          stableSince = Date.now();
          return;
        }
        if (Date.now() - stableSince < 1000) return;
        await sendMessage("school", { kind: "extracting" });
        await sendMessage("school", {
          kind: "capture",
          fragments: [fragment],
          semester_label: semester,
        });
      } catch {
        /* page may still be loading; no unrelated content is read */
      } finally {
        running = false;
      }
    };
    const observer = new MutationObserver((mutations) => {
      if (
        queryAt &&
        mutations.some(
          (m) =>
            m.target instanceof Element &&
            !!m.target.closest(
              "#table1, #table2, #kblist_table, #kbgrid_table_0",
            ),
        )
      ) {
        queryMutated = true;
        stableSince = Date.now();
      }
      void inspect();
    });
    observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
      characterData: true,
    });
    const timer = setInterval(inspect, 500);
    ctx.onInvalidated(() => {
      observer.disconnect();
      clearInterval(timer);
      document.removeEventListener("click", onQuery, true);
      document.removeEventListener("change", onTermChange, true);
    });
  },
});
