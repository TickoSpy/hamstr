type WsEvent =
  | { type: "progress"; video_id: string; progress: number; status: string }
  | { type: "completed"; video_id: string; title: string | null; status: string }
  | { type: "error"; video_id: string; error: string; status: string }
  | { type: "status_change"; video_id: string; status: string }
  | { type: "transcoding"; video_id: string; codec: string }
  | { type: "transcoded"; video_id: string; codec: string; file_size_bytes: number }
  | { type: "transcode_error"; video_id: string }
  | { type: "transcode_queued"; video_id: string }
  | { type: "transcode_dequeued"; video_id: string };

type Listener = (event: WsEvent) => void;

class WsClient {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private retryDelay = 500;
  private shouldConnect = false;

  connect() {
    this.shouldConnect = true;
    // Small delay so the browser finishes the initial page load before the
    // first WS attempt — avoids the "interrupted while page was loading" log.
    setTimeout(() => { if (this.shouldConnect) this._connect(); }, 300);
  }

  disconnect() {
    this.shouldConnect = false;
    this.ws?.close();
    this.ws = null;
  }

  on(fn: Listener) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private _connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}/ws`;
    this.ws = new WebSocket(url);

    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as WsEvent;
        this.listeners.forEach((fn) => fn(data));
      } catch {}
    };

    this.ws.onclose = () => {
      if (!this.shouldConnect) return;
      setTimeout(() => {
        this.retryDelay = Math.min(this.retryDelay * 2, 30_000);
        this._connect();
      }, this.retryDelay);
    };

    this.ws.onopen = () => {
      this.retryDelay = 500;
    };
  }
}

export const wsClient = new WsClient();
