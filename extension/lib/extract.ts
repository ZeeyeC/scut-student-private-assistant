import createDOMPurify from "dompurify";
export function captureContainer(doc: Document, selector: string): string {
  if (["body", "html", "*"].includes(selector.trim()))
    throw new Error("不能读取完整页面");
  const node = doc.querySelector(selector);
  return sanitizeTable(doc, node);
}
export function sanitizeTable(doc: Document, node: Element | null): string {
  if (!node || node.tagName !== "TABLE" || node.querySelector("input,form"))
    throw new Error("课表尚未加载或容器未核验");
  const purifier = createDOMPurify(doc.defaultView!);
  const result = purifier.sanitize(node.outerHTML, {
    ALLOWED_TAGS: [
      "table",
      "thead",
      "tbody",
      "tfoot",
      "tr",
      "th",
      "td",
      "span",
      "br",
    ],
    ALLOWED_ATTR: ["rowspan", "colspan"],
    ALLOW_DATA_ATTR: false,
  });
  if (
    new TextEncoder().encode(result).length > 1048576 ||
    node.querySelectorAll("tr").length > 2000
  )
    throw new Error("课表超过提取限制");
  return result;
}
