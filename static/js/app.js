/* AttendVision shared front-end helpers: API calls, toasts, camera, recorder. */
(function () {
  "use strict";

  const FLASH_KEY = "attendvision.flash";

  const Snap = {
    csrf() {
      const meta = document.querySelector('meta[name="csrf-token"]');
      return meta ? meta.content : "";
    },

    /** POST JSON or FormData and return the parsed body; throws Error(message) on failure. */
    async api(url, { json, form } = {}) {
      const headers = { "X-CSRFToken": this.csrf(), Accept: "application/json" };
      let body = form;
      if (json !== undefined) {
        headers["Content-Type"] = "application/json";
        body = JSON.stringify(json);
      }
      let response;
      try {
        response = await fetch(url, { method: "POST", headers, body, credentials: "same-origin" });
      } catch (err) {
        throw new Error("Network error. Check your connection and try again.");
      }
      let data = null;
      try {
        data = await response.json();
      } catch (err) {
        data = null;
      }
      if (!response.ok || !data || data.ok === false) {
        throw new Error((data && data.error) || `Request failed (${response.status}).`);
      }
      return data;
    },

    toast(message, type = "info", timeout = 4500) {
      if (window.Alpine && Alpine.store("toasts")) {
        Alpine.store("toasts").push(message, type, timeout);
      } else {
        document.addEventListener("alpine:initialized", () => Alpine.store("toasts").push(message, type, timeout), {
          once: true,
        });
      }
    },

    /** Store a message to show as a toast after the next full page load. */
    flash(message, type = "success") {
      try {
        sessionStorage.setItem(FLASH_KEY, JSON.stringify({ message, type }));
      } catch (err) {
        /* storage unavailable: ignore */
      }
    },

    consumeFlash() {
      try {
        const raw = sessionStorage.getItem(FLASH_KEY);
        if (!raw) return;
        sessionStorage.removeItem(FLASH_KEY);
        const { message, type } = JSON.parse(raw);
        this.toast(message, type);
      } catch (err) {
        /* ignore */
      }
    },

    reload(message, type = "success") {
      if (message) this.flash(message, type);
      window.location.reload();
    },

    /** Convert any recorded audio blob into a 16 kHz mono 16-bit PCM WAV blob. */
    async toWav(blob, sampleRate = 16000) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const ctx = new AudioCtx();
      const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
      ctx.close && ctx.close();
      const length = Math.max(1, Math.ceil(decoded.duration * sampleRate));
      const offline = new OfflineAudioContext(1, length, sampleRate);
      const source = offline.createBufferSource();
      source.buffer = decoded;
      source.connect(offline.destination);
      source.start(0);
      const rendered = await offline.startRendering();
      return encodeWav(rendered.getChannelData(0), sampleRate);
    },

    formatSeconds(total) {
      const m = Math.floor(total / 60);
      const s = total % 60;
      return `${m}:${String(s).padStart(2, "0")}`;
    },
  };

  function encodeWav(samples, sampleRate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const writeString = (offset, str) => {
      for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
    };
    writeString(0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true);
    writeString(8, "WAVE");
    writeString(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(36, "data");
    view.setUint32(40, samples.length * 2, true);
    let offset = 44;
    for (let i = 0; i < samples.length; i++, offset += 2) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return new Blob([view], { type: "audio/wav" });
  }

  window.Snap = Snap;

  document.addEventListener("alpine:init", () => {
    Alpine.store("toasts", {
      items: [],
      push(message, type = "info", timeout = 4500) {
        const id = Date.now() + Math.random();
        this.items.push({ id, message, type });
        setTimeout(() => this.remove(id), timeout);
      },
      remove(id) {
        this.items = this.items.filter((t) => t.id !== id);
      },
    });

    /** Webcam preview with JPEG capture. Use inside an element with x-ref="video". */
    Alpine.data("camera", (options = {}) => ({
      stream: null,
      ready: false,
      error: null,
      facing: options.facing || "user",

      async start() {
        this.error = null;
        this.ready = false;
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          this.error = "This browser can't access a camera. Try Chrome, Edge or Firefox over HTTPS.";
          return;
        }
        try {
          this.stop();
          this.stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: this.facing, width: { ideal: 1280 }, height: { ideal: 960 } },
            audio: false,
          });
          const video = this.$refs.video;
          video.srcObject = this.stream;
          await video.play();
          this.ready = true;
        } catch (err) {
          const name = err && err.name;
          this.error =
            name === "NotAllowedError"
              ? "Camera access was blocked. Allow the camera in your browser and try again."
              : name === "NotReadableError"
                ? "The camera is busy in another app. Close it and try again."
                : "No camera found. Connect one and reload the page.";
        }
      },

      stop() {
        if (this.stream) {
          this.stream.getTracks().forEach((t) => t.stop());
          this.stream = null;
        }
        this.ready = false;
      },

      async flip() {
        this.facing = this.facing === "user" ? "environment" : "user";
        await this.start();
      },

      /** Returns a JPEG Blob of the current frame. */
      capture(quality = 0.92) {
        const video = this.$refs.video;
        if (!this.ready || !video.videoWidth) return Promise.resolve(null);
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext("2d").drawImage(video, 0, 0);
        return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
      },

      destroy() {
        this.stop();
      },
    }));

    /** Microphone recorder that yields a WAV blob when stopped. */
    Alpine.data("recorder", (options = {}) => ({
      recording: false,
      processing: false,
      seconds: 0,
      blob: null,
      url: null,
      error: null,
      maxSeconds: options.maxSeconds || 120,
      _recorder: null,
      _chunks: [],
      _timer: null,
      _stream: null,

      get label() {
        return Snap.formatSeconds(this.seconds);
      },

      async start() {
        this.error = null;
        this.reset();
        if (!navigator.mediaDevices || !window.MediaRecorder) {
          this.error = "This browser can't record audio. Try Chrome, Edge or Firefox.";
          return;
        }
        try {
          this._stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (err) {
          this.error = "Microphone access was blocked. Allow the microphone and try again.";
          return;
        }
        this._chunks = [];
        this._recorder = new MediaRecorder(this._stream);
        this._recorder.ondataavailable = (e) => e.data.size && this._chunks.push(e.data);
        this._recorder.onstop = async () => {
          this._stream.getTracks().forEach((t) => t.stop());
          this.processing = true;
          try {
            const raw = new Blob(this._chunks, { type: this._recorder.mimeType || "audio/webm" });
            this.blob = await Snap.toWav(raw);
            this.url = URL.createObjectURL(this.blob);
          } catch (err) {
            this.error = "Couldn't process the recording. Please try again.";
          } finally {
            this.processing = false;
          }
        };
        this._recorder.start(250);
        this.recording = true;
        this.seconds = 0;
        this._timer = setInterval(() => {
          this.seconds += 1;
          if (this.seconds >= this.maxSeconds) this.stop();
        }, 1000);
      },

      stop() {
        clearInterval(this._timer);
        this._timer = null;
        if (this._recorder && this._recorder.state !== "inactive") this._recorder.stop();
        this.recording = false;
      },

      reset() {
        this.stop();
        if (this.url) URL.revokeObjectURL(this.url);
        this.blob = null;
        this.url = null;
        this.seconds = 0;
      },

      destroy() {
        this.reset();
      },
    }));
  });

  document.addEventListener("alpine:initialized", () => Snap.consumeFlash());
})();
