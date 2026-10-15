// A single MV3 worker owns the storage read/modify/write queue. Rejected events
// must not poison later restores, captures, cancellation or expiration.
export function serialQueue() {
  let tail: Promise<unknown> = Promise.resolve();
  return <T>(work: () => Promise<T>): Promise<T> => {
    const result = tail.then(work);
    tail = result.catch(() => undefined);
    return result;
  };
}
