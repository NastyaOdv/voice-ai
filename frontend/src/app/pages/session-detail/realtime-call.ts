import { Component, OnDestroy, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

import { Correction } from '../../core/models';

type CallStatus = 'idle' | 'connecting' | 'live' | 'closed' | 'error';
/** What the call is doing right now, driven by server events. */
type Phase = 'idle' | 'listening' | 'user_speaking' | 'thinking' | 'tutor_speaking';

interface TurnView {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  corrections: Correction[];
}

// Raw PCM the server VAD expects: 16-bit LE, mono, 16 kHz.
const TARGET_RATE = 16000;
// Send ~100 ms of audio per WS message to keep the frame rate sane.
const FLUSH_SAMPLES = 1600;

/**
 * Realtime call (v2, E4) — streams the microphone as PCM16/16k and plays the tutor's
 * reply as it is spoken, sentence by sentence.
 *
 * The server runs VAD, streams the reply tokens (`reply_delta`), voices each finished
 * sentence (`audio_chunk`, base64 WAV) so the tutor starts talking before the model has
 * finished writing, then sends grammar notes (`corrections`) from a parallel pass.
 */
@Component({
  selector: 'app-realtime-call',
  imports: [MatCardModule, MatButtonModule, MatIconModule],
  template: `
    <mat-card appearance="outlined" class="call-card">
      <mat-card-content>
        <div class="call-head">
          <div class="call-title">
            <mat-icon>wifi_tethering</mat-icon>
            <span>Realtime call (v2)</span>
          </div>
          <span class="call-status" [attr.data-status]="status()">
            <span class="status-dot"></span>{{ status() }}
          </span>
        </div>

        @if (status() === 'live') {
          <div class="phase" [attr.data-phase]="phase()">
            <mat-icon>{{ phaseIcon() }}</mat-icon>
            <span>{{ phaseLabel() }}</span>
          </div>
        } @else {
          <p class="call-hint">
            Press call and just talk — the server detects when you pause, then the tutor
            replies out loud while the answer is still being written.
          </p>
        }

        @if (turns().length > 0 || liveReply()) {
          <div class="call-turns">
            @for (turn of turns(); track turn.id) {
              <div class="ct" [class.ct-user]="turn.role === 'user'"
                   [class.ct-assistant]="turn.role === 'assistant'">
                <span class="ct-role">{{ turn.role === 'user' ? 'You' : 'Tutor' }}</span>
                <p class="ct-text">{{ turn.text }}</p>
                @if (turn.corrections.length > 0) {
                  <div class="ct-corrections">
                    @for (c of turn.corrections; track c.id) {
                      <p class="ct-correction">
                        <span class="you-said">{{ c.you_said }}</span> →
                        <span class="better">{{ c.better }}</span>
                        <span class="note">{{ c.note }}</span>
                      </p>
                    }
                  </div>
                }
              </div>
            }
            @if (liveReply()) {
              <div class="ct ct-assistant ct-live">
                <span class="ct-role">Tutor</span>
                <p class="ct-text">{{ liveReply() }}</p>
              </div>
            }
          </div>
        }

        <div class="call-actions">
          @if (status() === 'live' || status() === 'connecting') {
            <button mat-flat-button color="warn" (click)="hangUp()">
              <mat-icon>call_end</mat-icon>
              Hang up
            </button>
          } @else {
            <button mat-flat-button color="primary" (click)="start()">
              <mat-icon>call</mat-icon>
              Start call
            </button>
          }
        </div>

        @if (error()) {
          <p class="call-error">{{ error() }}</p>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: `
    .call-card { margin-top: 8px; }
    .call-head {
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
    }
    .call-title { display: flex; align-items: center; gap: 8px; font-weight: 600; }
    .call-status {
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 12px; text-transform: capitalize; color: var(--mat-sys-outline, #888);
    }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #9e9e9e; }
    .call-status[data-status='live'] .status-dot { background: #2e7d32; }
    .call-status[data-status='connecting'] .status-dot { background: #f9a825; }
    .call-status[data-status='error'] .status-dot { background: #c62828; }
    .call-hint { color: var(--mat-sys-outline, #888); font-size: 13px; margin: 8px 0 12px; }
    .phase {
      display: flex; align-items: center; gap: 10px; margin: 12px 0;
      font-weight: 500; color: var(--mat-sys-on-surface, #222);
    }
    .phase[data-phase='user_speaking'] { color: #2e7d32; }
    .phase[data-phase='thinking'] { color: #f9a825; }
    .phase[data-phase='tutor_speaking'] { color: #3f51b5; }
    .phase mat-icon { animation: pulse 1.4s ease-in-out infinite; }
    @keyframes pulse { 50% { opacity: 0.3; } }
    .call-turns {
      display: flex; flex-direction: column; gap: 10px; margin: 12px 0;
      max-height: 260px; overflow-y: auto;
    }
    .ct { padding: 8px 12px; border-radius: 10px; background: rgba(0, 0, 0, 0.04); }
    .ct-assistant { background: rgba(63, 81, 181, 0.08); }
    .ct-live { opacity: 0.75; }
    .ct-role { font-size: 11px; text-transform: uppercase; opacity: 0.6; }
    .ct-text { margin: 4px 0 0; }
    .ct-corrections { margin-top: 6px; font-size: 13px; }
    .ct-correction { margin: 2px 0; }
    .you-said { text-decoration: line-through; opacity: 0.7; }
    .better { color: #2e7d32; font-weight: 600; }
    .note { display: block; opacity: 0.7; font-size: 12px; }
    .call-actions { display: flex; gap: 12px; margin-top: 12px; }
    .call-error { color: var(--mat-sys-error, #b3261e); font-size: 13px; margin-top: 10px; }
  `,
})
export class RealtimeCall implements OnDestroy {
  readonly sessionId = input.required<string>();

  protected readonly status = signal<CallStatus>('idle');
  protected readonly phase = signal<Phase>('idle');
  protected readonly turns = signal<TurnView[]>([]);
  protected readonly liveReply = signal('');
  protected readonly error = signal<string | null>(null);

  private ws: WebSocket | null = null;
  private micStream: MediaStream | null = null;
  private captureCtx: AudioContext | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private pcmBuffer: number[] = [];

  // Web Audio playback queue: decoded sentences are scheduled back-to-back for gapless
  // speech. `playHead` is the time the next chunk should start.
  private playbackCtx: AudioContext | null = null;
  private playHead = 0;

  ngOnDestroy(): void {
    this.teardown();
  }

  async start(): Promise<void> {
    this.error.set(null);
    this.turns.set([]);
    this.liveReply.set('');
    this.status.set('connecting');
    try {
      await this.openSocket();
      await this.startMic();
      this.status.set('live');
      this.phase.set('listening');
    } catch (err) {
      this.error.set(
        err instanceof Error && err.name === 'NotAllowedError'
          ? 'Microphone access was denied.'
          : 'Could not start the call.',
      );
      this.status.set('error');
      this.teardown();
    }
  }

  hangUp(): void {
    this.status.set('closed');
    this.phase.set('idle');
    this.teardown();
  }

  // --- WebSocket -------------------------------------------------------------

  private openSocket(): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.wsUrl());
      this.ws = ws;
      ws.onopen = () => resolve();
      ws.onerror = () => reject(new Error('WebSocket error'));
      ws.onmessage = (event) => this.onServerEvent(event);
      ws.onclose = () => {
        this.ws = null;
        if (this.status() === 'live' || this.status() === 'connecting') {
          this.status.set('closed');
          this.phase.set('idle');
          this.teardown();
        }
      };
    });
  }

  private onServerEvent(event: MessageEvent): void {
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    switch (data['type']) {
      case 'speech_start':
        this.phase.set('user_speaking');
        break;
      case 'speech_end':
        this.phase.set('thinking');
        break;
      case 'user_turn':
        this.turns.update((t) => [
          ...t,
          {
            id: String(data['id'] ?? crypto.randomUUID()),
            role: 'user',
            text: String(data['text'] ?? ''),
            corrections: [],
          },
        ]);
        break;
      case 'reply_delta':
        this.phase.set('tutor_speaking');
        this.liveReply.update((s) => s + String(data['text'] ?? ''));
        break;
      case 'audio_chunk':
        this.enqueueAudio(String(data['audio_b64'] ?? ''));
        break;
      case 'assistant_done':
        this.turns.update((t) => [
          ...t,
          {
            id: String(data['id'] ?? crypto.randomUUID()),
            role: 'assistant',
            text: String(data['text'] ?? this.liveReply()),
            corrections: [],
          },
        ]);
        this.liveReply.set('');
        this.phase.set('listening');
        break;
      case 'corrections':
        this.attachCorrections(
          String(data['turn_id'] ?? ''),
          (data['corrections'] as Correction[]) ?? [],
        );
        break;
    }
  }

  private attachCorrections(turnId: string, corrections: Correction[]): void {
    if (corrections.length === 0) {
      return;
    }
    this.turns.update((turns) =>
      turns.map((t) => (t.id === turnId ? { ...t, corrections } : t)),
    );
  }

  // --- Playback queue --------------------------------------------------------

  private enqueueAudio(b64: string): void {
    if (!b64) {
      return;
    }
    if (!this.playbackCtx) {
      this.playbackCtx = new AudioContext();
      this.playHead = this.playbackCtx.currentTime;
    }
    const ctx = this.playbackCtx;
    ctx.decodeAudioData(this.b64ToBytes(b64))
      .then((buffer) => {
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        source.connect(ctx.destination);
        const startAt = Math.max(this.playHead, ctx.currentTime);
        source.start(startAt);
        this.playHead = startAt + buffer.duration;
      })
      .catch(() => undefined);
  }

  private b64ToBytes(b64: string): ArrayBuffer {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }

  // --- Microphone capture ----------------------------------------------------

  private async startMic(): Promise<void> {
    this.micStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    this.captureCtx = new AudioContext();
    await this.captureCtx.audioWorklet.addModule(this.workletUrl());

    const source = this.captureCtx.createMediaStreamSource(this.micStream);
    this.workletNode = new AudioWorkletNode(this.captureCtx, 'pcm-capture');
    const inputRate = this.captureCtx.sampleRate;
    this.workletNode.port.onmessage = (e: MessageEvent<Float32Array>) =>
      this.onAudioBlock(e.data, inputRate);
    source.connect(this.workletNode);
    // Keep the node pulling without routing mic audio to the speakers (would echo).
    this.workletNode.connect(this.captureCtx.destination);
  }

  private onAudioBlock(block: Float32Array, inputRate: number): void {
    const resampled = this.resample(block, inputRate, TARGET_RATE);
    for (const s of resampled) {
      this.pcmBuffer.push(s);
    }
    if (this.pcmBuffer.length >= FLUSH_SAMPLES && this.ws?.readyState === WebSocket.OPEN) {
      const chunk = this.pcmBuffer;
      this.pcmBuffer = [];
      this.ws.send(this.toPcm16(chunk));
    }
  }

  private resample(input: Float32Array, inRate: number, outRate: number): Float32Array {
    if (inRate === outRate) {
      return input;
    }
    const ratio = inRate / outRate;
    const outLen = Math.floor(input.length / ratio);
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const idx = i * ratio;
      const i0 = Math.floor(idx);
      const i1 = Math.min(i0 + 1, input.length - 1);
      out[i] = input[i0] + (input[i1] - input[i0]) * (idx - i0);
    }
    return out;
  }

  private toPcm16(samples: number[]): ArrayBuffer {
    const pcm = new Int16Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return pcm.buffer;
  }

  /** An AudioWorklet that just forwards each mono block to the main thread. */
  private workletUrl(): string {
    const src = `
      class PcmCapture extends AudioWorkletProcessor {
        process(inputs) {
          const ch = inputs[0][0];
          if (ch) this.port.postMessage(ch.slice(0));
          return true;
        }
      }
      registerProcessor('pcm-capture', PcmCapture);
    `;
    return URL.createObjectURL(new Blob([src], { type: 'application/javascript' }));
  }

  private teardown(): void {
    this.workletNode?.port.close();
    this.workletNode?.disconnect();
    this.workletNode = null;
    this.micStream?.getTracks().forEach((t) => t.stop());
    this.micStream = null;
    void this.captureCtx?.close().catch(() => undefined);
    this.captureCtx = null;
    void this.playbackCtx?.close().catch(() => undefined);
    this.playbackCtx = null;
    this.pcmBuffer = [];
    if (this.ws) {
      this.ws.onopen = this.ws.onmessage = this.ws.onerror = this.ws.onclose = null;
      if (this.ws.readyState === WebSocket.OPEN) {
        this.ws.send('bye');
      }
      if (
        this.ws.readyState === WebSocket.OPEN ||
        this.ws.readyState === WebSocket.CONNECTING
      ) {
        this.ws.close(1000);
      }
      this.ws = null;
    }
  }

  private wsUrl(): string {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    return `${scheme}://${location.host}/api/sessions/${this.sessionId()}/call`;
  }

  protected phaseIcon(): string {
    switch (this.phase()) {
      case 'user_speaking':
        return 'graphic_eq';
      case 'thinking':
        return 'more_horiz';
      case 'tutor_speaking':
        return 'record_voice_over';
      default:
        return 'hearing';
    }
  }

  protected phaseLabel(): string {
    switch (this.phase()) {
      case 'user_speaking':
        return 'Listening to you…';
      case 'thinking':
        return 'Thinking…';
      case 'tutor_speaking':
        return 'Tutor is speaking…';
      default:
        return 'Ready — start talking';
    }
  }
}
