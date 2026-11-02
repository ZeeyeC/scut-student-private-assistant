# Independent whole-branch review

Reviewer markdown_final_review, read-only,7e8bbf1..f6603c3. One Important: long inlineKaTeX formulas remain inline and overflow their bubble. Actual libraryCSS .katex-base nowrap/min-content confirmed. No other actionable defects in streaming/copy/URL restrictions/KaTeX override.

Excluded from defects: Mermaid, syntax highlighting, remote image previews (explicitly out of scope); Task2 release/native (pending by design).

Regression unbreakable inline and bracket math: RED actual chat.scrollWidth999 > clientWidth298. Added local inline-block scrolling onKaTeX root, preserved display-math wrapper scrolling. GREEN pending.

GREEN:5/5 complete chat-markdown E2Es passed (9.6s); bounds defect fixed without changing user-message or backend behavior. Actual horizontal-wheel regression added before final release. No remaining Critical/Important findings.
