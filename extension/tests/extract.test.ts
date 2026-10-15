import { describe, it, expect } from "vitest";
import { JSDOM } from "jsdom";
import { captureContainer } from "../lib/extract";
describe("only timetable container", () => {
  it("retains merged cells and removes login, links and identity outside container", () => {
    const doc = new JSDOM(
      '<input type="password" value="secret"><p>学号 1234</p><table id="t"><tr><td rowspan="2"><a href="https://secret">数学</a><img src="x" onerror="evil()"></td></tr></table>',
    ).window.document;
    const result = captureContainer(doc, "#t");
    expect(result).toContain("数学");
    expect(result).toContain('rowspan="2"');
    expect(result).not.toMatch(/secret|学号|href|onerror|<input|<img|id=/);
  });
  it("does not extract a login page or arbitrary outer document", () => {
    const doc = new JSDOM('<form><input type="password"></form>').window
      .document;
    expect(() => captureContainer(doc, "#t")).toThrow();
    expect(() => captureContainer(doc, "body")).toThrow();
  });
});
