import {
  useEffect,
  useRef,
  useState,
  type ComponentPropsWithoutRef,
  type FC,
} from 'react';
import {
  MarkdownTextPrimitive,
  type CodeHeaderProps,
  type MarkdownTextPrimitiveProps,
} from '@assistant-ui/react-markdown';
import {
  escapeCurrencyDollars,
  normalizeMathDelimiters,
} from '@assistant-ui/react-markdown/preprocess';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import './assistant-markdown.css';

type WithMarkdownNode<T> = T & {
  node?: unknown;
};

const CONTROL_CHAR_PATTERN = /[\u0000-\u001F\u007F]/;

/**
 * Preprocess markdown text using @assistant-ui/react-markdown's built-in utilities
 * so fenced code blocks and inline code spans remain untouched while bracket math
 * delimiters (\[...\], \(...\)) and currency dollar signs are safely normalized.
 */
export const preprocessMarkdown = (text: string): string => {
  if (!text) {
    return '';
  }
  return escapeCurrencyDollars(normalizeMathDelimiters(text));
};

/**
 * Restrict transformed URLs strictly to absolute http/https URLs and local #hash anchors.
 * Rejects control characters, protocol-relative URLs (//), relative paths, and
 * dangerous schemes (javascript:, data:, file:, vbscript:, etc.).
 */
export const safeUrlTransform = (url: string): string => {
  if (typeof url !== 'string') {
    return '';
  }

  if (CONTROL_CHAR_PATTERN.test(url)) {
    return '';
  }

  const trimmed = url.trim();
  if (!trimmed) {
    return '';
  }

  if (trimmed.startsWith('#')) {
    return trimmed;
  }

  if (trimmed.startsWith('//') || !/^https?:\/\//i.test(trimmed)) {
    return '';
  }

  try {
    const parsed = new URL(trimmed);
    if (
      (parsed.protocol === 'http:' || parsed.protocol === 'https:') &&
      Boolean(parsed.hostname)
    ) {
      return parsed.toString();
    }
  } catch {
    return '';
  }

  return '';
};

const REMARK_PLUGINS: NonNullable<MarkdownTextPrimitiveProps['remarkPlugins']> = [
  remarkGfm,
  [remarkMath, { singleDollarTextMath: true }],
];

const REHYPE_KATEX_OPTIONS = {
  throwOnError: false,
  strict: 'ignore',
  trust: false,
  output: 'htmlAndMathml',
  maxExpand: 1000,
  maxSize: 25,
} as const;

const REHYPE_PLUGINS: NonNullable<MarkdownTextPrimitiveProps['rehypePlugins']> = [
  [rehypeKatex, REHYPE_KATEX_OPTIONS],
];

type CopyStatus = 'idle' | 'copied' | 'error';

const CodeHeader: FC<CodeHeaderProps> = ({ language, code }) => {
  const [copyStatus, setCopyStatus] = useState<CopyStatus>('idle');
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  const scheduleReset = () => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(() => {
      setCopyStatus('idle');
      timerRef.current = null;
    }, 2000);
  };

  const handleCopy = async () => {
    if (typeof code !== 'string' || code.length === 0) {
      setCopyStatus('error');
      scheduleReset();
      return;
    }

    try {
      if (
        typeof navigator === 'undefined' ||
        !navigator.clipboard ||
        typeof navigator.clipboard.writeText !== 'function'
      ) {
        throw new Error('Clipboard API unavailable');
      }
      await navigator.clipboard.writeText(code);
      setCopyStatus('copied');
    } catch {
      setCopyStatus('error');
    }

    scheduleReset();
  };

  const normalizedLanguage =
    typeof language === 'string' && language.trim().length > 0
      ? language.trim().toLowerCase()
      : 'text';

  const statusLabel =
    copyStatus === 'copied'
      ? '已复制'
      : copyStatus === 'error'
        ? '复制失败'
        : '复制代码';

  return (
    <div className="assistant-markdown__code-header">
      <span className="assistant-markdown__code-lang">{normalizedLanguage}</span>
      <div className="assistant-markdown__code-actions">
        <span
          className="assistant-markdown__copy-status"
          role="status"
          aria-live="polite"
        >
          {copyStatus === 'copied'
            ? '已复制'
            : copyStatus === 'error'
              ? '复制失败'
              : ''}
        </span>
        <button
          type="button"
          className={`assistant-markdown__copy-btn${
            copyStatus === 'copied'
              ? ' assistant-markdown__copy-btn--copied'
              : copyStatus === 'error'
                ? ' assistant-markdown__copy-btn--error'
                : ''
          }`}
          aria-label="复制代码"
          title="复制代码"
          onClick={() => {
            void handleCopy();
          }}
        >
          {statusLabel}
        </button>
      </div>
    </div>
  );
};

const MarkdownAnchor: FC<WithMarkdownNode<ComponentPropsWithoutRef<'a'>>> = ({
  node: _node,
  href,
  children,
  className,
  ...rest
}) => {
  const safeHref = typeof href === 'string' ? safeUrlTransform(href) : '';
  if (!safeHref) {
    return <span className="assistant-markdown__unsafe-link">{children}</span>;
  }

  const isHashLink = safeHref.startsWith('#');
  const mergedClassName = className
    ? `assistant-markdown__link ${className}`
    : 'assistant-markdown__link';

  return (
    <a
      {...rest}
      href={safeHref}
      className={mergedClassName}
      target={isHashLink ? undefined : '_blank'}
      rel={isHashLink ? undefined : 'noopener noreferrer'}
    >
      {children}
    </a>
  );
};

const MarkdownImage: FC<WithMarkdownNode<ComponentPropsWithoutRef<'img'>>> = ({
  node: _node,
  alt,
}) => {
  const altText = typeof alt === 'string' ? alt.trim() : '';
  return (
    <span className="assistant-markdown__image-fallback" role="note">
      {altText ? `[图片: ${altText}]` : '[图片]'}
    </span>
  );
};

const MarkdownTable: FC<WithMarkdownNode<ComponentPropsWithoutRef<'table'>>> = ({
  node: _node,
  children,
  className,
  ...rest
}) => {
  return (
    <div className="assistant-markdown__table-wrap">
      <table {...rest} className={className}>
        {children}
      </table>
    </div>
  );
};

const MarkdownInput: FC<WithMarkdownNode<ComponentPropsWithoutRef<'input'>>> = ({
  node: _node,
  type,
  checked,
}) => {
  if (type === 'checkbox') {
    return (
      <input
        type="checkbox"
        className="assistant-markdown__checkbox"
        checked={Boolean(checked)}
        disabled
        readOnly
        tabIndex={-1}
        aria-disabled="true"
      />
    );
  }
  return null;
};

const MARKDOWN_COMPONENTS: NonNullable<MarkdownTextPrimitiveProps['components']> = {
  CodeHeader,
  a: MarkdownAnchor,
  img: MarkdownImage,
  table: MarkdownTable,
  input: MarkdownInput,
};

export function AssistantMarkdown() {
  return (
    <MarkdownTextPrimitive
      className="assistant-markdown"
      smooth={false}
      defer={false}
      skipHtml={true}
      preprocess={preprocessMarkdown}
      remarkPlugins={REMARK_PLUGINS}
      rehypePlugins={REHYPE_PLUGINS}
      urlTransform={safeUrlTransform}
      components={MARKDOWN_COMPONENTS}
    />
  );
};

export default AssistantMarkdown;
