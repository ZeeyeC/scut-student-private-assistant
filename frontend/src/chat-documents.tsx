import { useEffect, useRef, useState } from 'react';
import { FileText } from 'lucide-react';
import { api } from './api';
import type { Resource } from './types';
import './chat-images.css';

export const DOC_EXTENSIONS = [
  '.pdf',
  '.docx',
  '.pptx',
  '.xlsx',
  '.txt',
  '.md',
  '.markdown',
];

export const DOC_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'text/plain',
  'text/markdown',
  'text/x-markdown',
];

export const DOC_ACCEPT = [
  '.pdf',
  '.docx',
  '.pptx',
  '.xlsx',
  '.txt',
  '.md',
  ...DOC_TYPES,
].join(',');

export const MAX_DOC_COUNT = 5;
export const MAX_DOC_BYTES = 20 * 1024 * 1024;

export function isDocFile(file: Pick<File, 'name' | 'type'>): boolean {
  const name = (file.name || '').toLowerCase().trim();
  const dot = name.lastIndexOf('.');
  const ext = dot >= 0 ? name.slice(dot) : '';
  if (ext) {
    if (!DOC_EXTENSIONS.includes(ext)) return false;
    if (!file.type || file.type === 'application/octet-stream') return true;
    if (file.type.startsWith('image/')) return false;
    return DOC_TYPES.includes(file.type) || file.type.startsWith('text/');
  }
  return DOC_TYPES.includes(file.type);
}

export function validateDocFiles(files: File[], existingCount = 0): File[] {
  if (files.length === 0 || existingCount + files.length > MAX_DOC_COUNT) {
    throw new Error('最多可添加 5 份课程资料。');
  }
  for (const file of files) {
    if (!isDocFile(file)) {
      throw new Error('仅支持 PDF、DOCX、PPTX、XLSX、TXT、MD 课程资料。');
    }
    if (file.size > MAX_DOC_BYTES) {
      throw new Error('单个课程资料不能超过 20 MiB。');
    }
  }
  return files;
}

export type PendingDocument = {
  id: string;
  file: File;
  uploadKey: string;
  sourceId?: string;
  assetId?: string;
};

export type SelectedSource = {
  id: string;
  title: string;
  filename?: string;
  format?: string;
};

function toSelectedSource(input: Resource | SelectedSource): SelectedSource {
  if ('data' in input && input.data && typeof input.data === 'object') {
    return {
      id: input.id,
      title: String(input.data.title || input.data.filename || input.id),
      filename: input.data.filename ? String(input.data.filename) : undefined,
      format: input.data.format ? String(input.data.format) : undefined,
    };
  }
  const s = input as SelectedSource;
  return {
    id: s.id,
    title: s.title || s.filename || s.id,
    filename: s.filename,
    format: s.format,
  };
}

export function docFormatBadge(name: string): string {
  const dot = name.lastIndexOf('.');
  if (dot < 0) return 'DOC';
  return name.slice(dot + 1).toUpperCase().slice(0, 4) || 'DOC';
}

export function useChatDocuments() {
  const [documents, setDocuments] = useState<PendingDocument[]>([]);
  const [selectedSources, setSelectedSources] = useState<SelectedSource[]>([]);
  const [error, setError] = useState('');
  const [keys, setKeys] = useState(() => ({
    runKey: crypto.randomUUID(),
    threadKey: crypto.randomUUID(),
  }));

  const generation = useRef(0);
  const locked = useRef(false);
  const currentDocs = useRef<PendingDocument[]>([]);
  const currentSources = useRef<SelectedSource[]>([]);
  const queue = useRef<Promise<void>>(Promise.resolve());

  const rollKeys = () => {
    setKeys({
      runKey: crypto.randomUUID(),
      threadKey: crypto.randomUUID(),
    });
  };

  const clear = () => {
    generation.current++;
    locked.current = false;
    currentDocs.current = [];
    currentSources.current = [];
    setDocuments([]);
    setSelectedSources([]);
    setError('');
    rollKeys();
  };

  const freeze = () => {
    generation.current++;
    locked.current = true;
  };

  const unfreeze = () => {
    locked.current = false;
  };

  useEffect(
    () => () => {
      generation.current++;
      locked.current = false;
    },
    [],
  );

  const remove = (id: string) => {
    if (locked.current) return;
    const target = currentDocs.current.find((item) => item.id === id);
    if (!target) return;
    const next = currentDocs.current.filter((item) => item.id !== id);
    currentDocs.current = next;
    setDocuments(next);
    setError('');
    rollKeys();
  };

  const attachSource = (raw: Resource | SelectedSource) => {
    if (locked.current) return;
    const source = toSelectedSource(raw);
    if (currentSources.current.some((s) => s.id === source.id)) {
      setError('');
      return;
    }
    if (
      currentDocs.current.length + currentSources.current.length >=
      MAX_DOC_COUNT
    ) {
      setError('最多可添加 5 份课程资料。');
      return;
    }
    const next = [...currentSources.current, source];
    currentSources.current = next;
    setSelectedSources(next);
    setError('');
    rollKeys();
  };

  const detachSource = (id: string) => {
    if (locked.current) return;
    if (!currentSources.current.some((s) => s.id === id)) return;
    const next = currentSources.current.filter((s) => s.id !== id);
    currentSources.current = next;
    setSelectedSources(next);
    setError('');
    rollKeys();
  };

  const toggleSource = (raw: Resource | SelectedSource) => {
    if (locked.current) return;
    const source = toSelectedSource(raw);
    if (currentSources.current.some((s) => s.id === source.id)) {
      detachSource(source.id);
    } else {
      attachSource(source);
    }
  };

  const add = (files: File[]): Promise<void> => {
    if (locked.current) return Promise.resolve();
    const epoch = generation.current;
    const task = queue.current.then(async () => {
      if (epoch !== generation.current || locked.current) return;
      try {
        const existingTotal =
          currentDocs.current.length + currentSources.current.length;
        const validFiles = validateDocFiles(files, existingTotal);
        if (epoch !== generation.current || locked.current) return;
        if (
          currentDocs.current.length +
            currentSources.current.length +
            validFiles.length >
          MAX_DOC_COUNT
        ) {
          throw new Error('最多可添加 5 份课程资料。');
        }
        const batch: PendingDocument[] = validFiles.map((file) => ({
          id: crypto.randomUUID(),
          file,
          uploadKey: crypto.randomUUID(),
        }));
        const next = [...currentDocs.current, ...batch];
        currentDocs.current = next;
        setDocuments(next);
        setError('');
        rollKeys();
      } catch (e) {
        if (epoch === generation.current && !locked.current) {
          setError(String(e instanceof Error ? e.message : e));
        }
      }
    });
    queue.current = task.catch(() => {});
    return task;
  };

  const onSend = async (
    docsSnapshot: PendingDocument[] = currentDocs.current,
    sourcesSnapshot: SelectedSource[] = currentSources.current,
    isCurrent: () => boolean = () => true,
  ): Promise<string[]> => {
    for (const item of docsSnapshot) {
      if (!isCurrent()) return [];
      const existingId = item.sourceId ?? item.assetId;
      if (existingId) {
        item.sourceId = existingId;
        item.assetId = existingId;
        continue;
      }
      const form = new FormData();
      form.set('file', item.file);
      const created = await api<{ id: string; revision: number }>(
        '/knowledge/documents',
        {
          method: 'POST',
          body: form,
          headers: { 'Idempotency-Key': item.uploadKey },
        },
      );
      item.sourceId = created.id;
      item.assetId = created.id;
    }
    const merged: string[] = [];
    for (const s of sourcesSnapshot) {
      if (s.id && !merged.includes(s.id)) merged.push(s.id);
    }
    for (const d of docsSnapshot) {
      const id = d.sourceId ?? d.assetId;
      if (id && !merged.includes(id)) merged.push(id);
    }
    return merged.slice(0, MAX_DOC_COUNT);
  };

  const sourceIds: string[] = [];
  for (const s of selectedSources) {
    if (s.id && !sourceIds.includes(s.id)) sourceIds.push(s.id);
  }
  for (const d of documents) {
    const id = d.sourceId ?? d.assetId;
    if (id && !sourceIds.includes(id)) sourceIds.push(id);
  }

  return {
    documents,
    selectedSources,
    sourceIds: sourceIds.slice(0, MAX_DOC_COUNT),
    totalCount: documents.length + selectedSources.length,
    runKey: keys.runKey,
    threadKey: keys.threadKey,
    error,
    setError,
    add,
    remove,
    attachSource,
    detachSource,
    toggleSource,
    onSend,
    clear,
    freeze,
    unfreeze,
  };
}

export function ChatDocumentControls({
  state,
  disabled,
  onPickFiles,
}: {
  state: ReturnType<typeof useChatDocuments>;
  disabled: boolean;
  onPickFiles?: () => void;
}) {
  return (
    <>
      {state.documents.length > 0 && (
        <div
          className="chat-image-preview chat-doc-preview"
          aria-label="待发送的课程资料"
        >
          {state.documents.map((item) => (
            <div key={item.id} className="chat-image-tile chat-doc-tile">
              <div className="chat-doc-thumb" aria-hidden="true">
                <FileText size={26} />
                <small>{docFormatBadge(item.file.name)}</small>
              </div>
              <span>{item.file.name}</span>
              <button
                type="button"
                className="chat-image-remove"
                disabled={disabled}
                aria-label={`移除${item.file.name}`}
                onClick={() => state.remove(item.id)}
              >
                ×
              </button>
            </div>
          ))}
          {onPickFiles && state.totalCount < MAX_DOC_COUNT && (
            <button
              type="button"
              className="chat-image-add"
              disabled={disabled}
              aria-label="继续添加课程资料"
              onClick={onPickFiles}
            >
              <span aria-hidden="true">＋</span>
              <span>添加资料</span>
            </button>
          )}
        </div>
      )}
      {state.selectedSources.length > 0 && (
        <div className="chat-source-tokens" aria-label="已选课程资料">
          {state.selectedSources.map((source) => (
            <span key={source.id} className="chat-source-token">
              <FileText size={13} aria-hidden="true" />
              <span>{source.title}</span>
              <button
                type="button"
                className="chat-source-token-remove"
                disabled={disabled}
                aria-label={`移除${source.title}`}
                onClick={() => state.detachSource(source.id)}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      {state.error && <p role="alert">{state.error}</p>}
    </>
  );
}
