import { useEffect, useRef, useState } from 'react';
import type { ClipboardEvent, DragEvent, ReactNode } from 'react';
import './chat-images.css';
import { Paperclip } from 'lucide-react';

export const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
const MAX_IMAGE_COUNT = 5;
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const MAX_IMAGE_PIXELS = 20_000_000;

export function validateImageFiles(files: File[], existingCount = 0): File[] {
  if (files.length === 0 || existingCount + files.length > MAX_IMAGE_COUNT) {
    throw new Error('最多可添加 5 张作业截图。');
  }
  for (const file of files) {
    if (!IMAGE_TYPES.includes(file.type)) {
      throw new Error('仅支持 PNG、JPEG、WebP 图片。');
    }
    if (file.size > MAX_IMAGE_BYTES) {
      throw new Error('图片不能超过 10 MiB。');
    }
  }
  return files;
}

export type PendingImage = {
  id: string;
  file: File;
  url: string;
  uploadKey: string;
  assetId?: string;
};

function decodeImage(url: string): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const img = new Image();
    img.onload = () =>
      img.naturalWidth * img.naturalHeight <= MAX_IMAGE_PIXELS
        ? resolve()
        : reject(new Error('图片不能超过 2000 万像素。'));
    img.onerror = () => reject(new Error('图片无法读取，请重新选择。'));
    img.src = url;
  });
}

export function useChatImage() {
  const [images, setImages] = useState<PendingImage[]>([]);
  const [error, setError] = useState('');
  const [keys, setKeys] = useState(() => ({
    runKey: crypto.randomUUID(),
    threadKey: crypto.randomUUID(),
  }));

  const generation = useRef(0);
  const current = useRef<PendingImage[]>([]);
  const queue = useRef<Promise<void>>(Promise.resolve());

  const rollKeys = () => {
    setKeys({
      runKey: crypto.randomUUID(),
      threadKey: crypto.randomUUID(),
    });
  };

  const clear = () => {
    generation.current++;
    for (const item of current.current) {
      URL.revokeObjectURL(item.url);
    }
    current.current = [];
    setImages([]);
    setError('');
    rollKeys();
  };

  const remove = (id: string) => {
    const target = current.current.find((item) => item.id === id);
    if (!target) return;
    URL.revokeObjectURL(target.url);
    const next = current.current.filter((item) => item.id !== id);
    current.current = next;
    setImages(next);
    setError('');
    rollKeys();
  };

  const freeze = () => {
    generation.current++;
  };

  useEffect(
    () => () => {
      generation.current++;
      for (const item of current.current) {
        URL.revokeObjectURL(item.url);
      }
    },
    []
  );

  const add = (files: File[]): Promise<void> => {
    const epoch = generation.current;
    const task = queue.current.then(async () => {
      if (epoch !== generation.current) return;
      const urls: string[] = [];
      try {
        const validFiles = validateImageFiles(files, current.current.length);
        for (const file of validFiles) {
          const url = URL.createObjectURL(file);
          urls.push(url);
          await decodeImage(url);
          if (epoch !== generation.current) {
            for (const u of urls) URL.revokeObjectURL(u);
            return;
          }
        }
        if (current.current.length + validFiles.length > MAX_IMAGE_COUNT) {
          throw new Error('最多可添加 5 张作业截图。');
        }
        const batch: PendingImage[] = validFiles.map((file, i) => ({
          id: crypto.randomUUID(),
          file,
          url: urls[i],
          uploadKey: crypto.randomUUID(),
        }));
        const next = [...current.current, ...batch];
        current.current = next;
        setImages(next);
        setError('');
        rollKeys();
      } catch (e) {
        for (const u of urls) URL.revokeObjectURL(u);
        if (epoch === generation.current) {
          setError(String(e instanceof Error ? e.message : e));
        }
      }
    });
    queue.current = task.catch(() => {});
    return task;
  };

  return {
    images,
    runKey: keys.runKey,
    threadKey: keys.threadKey,
    error,
    setError,
    add,
    remove,
    clear,
    freeze,
  };
}

export function ImageDropArea({
  children,
  disabled,
  onFiles,
}: {
  children: ReactNode;
  disabled: boolean;
  onFiles: (files: File[]) => void;
}) {
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    const prevent = (e: globalThis.DragEvent) => {
      if (e.dataTransfer?.types.includes('Files')) e.preventDefault();
    };
    window.addEventListener('dragover', prevent);
    window.addEventListener('drop', prevent);
    return () => {
      window.removeEventListener('dragover', prevent);
      window.removeEventListener('drop', prevent);
    };
  }, []);

  useEffect(() => {
    if (disabled) setDragging(false);
  }, [disabled]);

  const drag = (e: DragEvent) => {
    if (e.dataTransfer.types.includes('Files')) {
      e.preventDefault();
      e.dataTransfer.dropEffect = disabled ? 'none' : 'copy';
      setDragging(!disabled);
    }
  };

  const paste = (e: ClipboardEvent) => {
    const files = Array.from(e.clipboardData.files);
    if (files.length) {
      e.preventDefault();
      e.stopPropagation();
      if (!disabled) onFiles(files);
    }
  };

  return (
    <div
      className="chat-image-drop"
      data-testid="chat-image-drop"
      onDragEnter={drag}
      onDragOver={drag}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
          setDragging(false);
        }
      }}
      onDrop={(e) => {
        setDragging(false);
        if (e.dataTransfer.types.includes('Files')) {
          e.preventDefault();
          e.stopPropagation();
          if (!disabled) onFiles(Array.from(e.dataTransfer.files));
        }
      }}
      onPasteCapture={paste}
    >
      {children}
      {dragging && (
        <div className="chat-drop-hint" role="status">
          松开添加作业截图
        </div>
      )}
    </div>
  );
}

export function ChatImageControls({
  state,
  disabled,
}: {
  state: ReturnType<typeof useChatImage>;
  disabled: boolean;
}) {
  const [menu, setMenu] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (disabled) setMenu(false);
  }, [disabled]);

  useEffect(() => {
    if (!menu) return;
    const click = (e: MouseEvent) => {
      if (!container.current?.contains(e.target as Node)) setMenu(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenu(false);
    };
    document.addEventListener('pointerdown', click);
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('pointerdown', click);
      document.removeEventListener('keydown', key);
    };
  }, [menu]);

  return (
    <>
      {state.images.length > 0 && (
        <div className="chat-image-preview">
          {state.images.map((item) => (
            <div key={item.id} className="chat-image-tile">
              <img src={item.url} alt="待发送的作业截图" />
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
          {state.images.length < MAX_IMAGE_COUNT && (
            <button
              type="button"
              className="chat-image-add"
              disabled={disabled}
              aria-label="继续添加作业截图"
              onClick={() => file.current?.click()}
            >
              <span aria-hidden="true">＋</span><span>添加图片</span>
            </button>
          )}
        </div>
      )}
      {state.error && <p role="alert">{state.error}</p>}
      <div className="chat-attachment-menu" ref={container}>
        <button
          className="workspace-text-button"
          type="button"
          disabled={disabled}
          aria-haspopup="menu"
          aria-expanded={menu}
          onClick={() => setMenu((v) => !v)}
        >
          <Paperclip size={16} />
          附件
        </button>
        {menu && (
          <div role="menu" aria-label="添加附件">
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setMenu(false);
                file.current?.click();
              }}
            >
              图片识别作业
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setMenu(false);
                window.dispatchEvent(
                  new CustomEvent('campus-start-import', {
                    detail: { method: 'school' },
                  })
                );
              }}
            >
              导入课表
            </button>
          </div>
        )}
        <input
          ref={file}
          hidden
          multiple
          disabled={disabled}
          aria-label="选择作业截图"
          type="file"
          accept={IMAGE_TYPES.join(',')}
          onChange={(e) => {
            if (e.target.files?.length) {
              void state.add(Array.from(e.target.files));
            }
            e.target.value = '';
          }}
        />
      </div>
    </>
  );
}
