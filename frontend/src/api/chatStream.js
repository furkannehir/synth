/** Keep HTTP snapshots and streamed updates ordered, including reconnects. */
export function connectChatStream({
  url, loadHistory, onHistory, onEvent, onError,
  EventSourceImpl = EventSource,
}) {
  const source = new EventSourceImpl(url);
  let disposed = false;
  let refreshing = false;
  let refreshAgain = false;
  let buffered = [];
  let replayThrough = -1;

  function applyUpdate({ event, revision }) {
    // History is fetched after the connection snapshot. Reapplying old events
    // could roll back edits or mark newer DMs as read using an old receipt.
    if (revision === null || revision > replayThrough) onEvent(event);
  }

  async function refreshHistory() {
    if (disposed) return;
    if (refreshing) {
      refreshAgain = true;
      return;
    }
    refreshing = true;
    do {
      refreshAgain = false;
      try {
        const history = await loadHistory();
        if (!disposed) onHistory(history);
      } catch (error) {
        if (!disposed) onError(error);
      }
      if (disposed) return;
      const pending = buffered;
      buffered = [];
      for (const update of pending) applyUpdate(update);
    } while (refreshAgain && !disposed);
    refreshing = false;
  }

  source.onopen = refreshHistory;
  source.onmessage = (message) => {
    if (disposed) return;
    let event;
    try {
      event = JSON.parse(message.data);
    } catch {
      return;
    }
    if (!event || typeof event.type !== "string") return;
    const parsedRevision = message.lastEventId ? Number(message.lastEventId) : null;
    const revision = Number.isSafeInteger(parsedRevision) ? parsedRevision : null;
    if (event.type === "connected") {
      if (Number.isSafeInteger(event.data?.revision)) {
        replayThrough = event.data.revision;
      }
      return;
    }
    if (event.type === "resync") {
      if (revision !== null) replayThrough = revision;
      refreshHistory();
    } else if (refreshing) {
      buffered.push({ event, revision });
    } else {
      applyUpdate({ event, revision });
    }
  };
  source.onerror = () => {}; // EventSource reconnects; onopen reloads history.
  refreshHistory();

  return () => {
    disposed = true;
    buffered = [];
    source.close();
  };
}
