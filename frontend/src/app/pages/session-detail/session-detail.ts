import { DatePipe } from '@angular/common';
import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { SessionDetail } from '../../core/models';
import { SessionsService } from '../../core/sessions.service';
import { RealtimeCall } from './realtime-call';

/** v1 = asynchronous walkie-talkie (record -> send). v2 = realtime call over WebSocket. */
type PracticeMode = 'v1' | 'v2';

@Component({
  selector: 'app-session-detail',
  imports: [
    DatePipe,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatIconModule,
    MatChipsModule,
    MatDividerModule,
    MatProgressSpinnerModule,
    RealtimeCall,
  ],
  templateUrl: './session-detail.html',
  styleUrl: './session-detail.scss',
})
export class SessionDetailPage implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly sessions = inject(SessionsService);

  protected readonly session = signal<SessionDetail | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

  protected readonly recording = signal(false);
  protected readonly submitting = signal(false);
  protected readonly recordError = signal<string | null>(null);

  /** Chosen when opening the session; persisted in the `?mode=` query param. */
  protected readonly mode = signal<PracticeMode>('v1');

  protected sessionId = '';
  private mediaRecorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.error.set('Session not found.');
      this.loading.set(false);
      return;
    }
    this.sessionId = id;
    this.mode.set(this.route.snapshot.queryParamMap.get('mode') === 'v2' ? 'v2' : 'v1');
    this.load();
  }

  setMode(mode: PracticeMode): void {
    if (mode === this.mode()) {
      return;
    }
    this.mode.set(mode);
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { mode },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  ngOnDestroy(): void {
    this.stopTracks();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.sessions.get(this.sessionId).subscribe({
      next: (detail) => {
        this.session.set(detail);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(
          err.status === 404 ? 'Session not found.' : 'Could not load this session.',
        );
        this.loading.set(false);
      },
    });
  }

  /** Audio URLs from the API are relative (`/sessions/...`); route them via the proxy. */
  audioSrc(url: string): string {
    return `/api${url}`;
  }

  async startRecording(): Promise<void> {
    this.recordError.set(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      this.recordError.set('Recording is not supported in this browser.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.chunks = [];
      this.mediaRecorder = new MediaRecorder(stream);
      this.mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          this.chunks.push(e.data);
        }
      };
      this.mediaRecorder.onstop = () => {
        const type = this.mediaRecorder?.mimeType || 'audio/webm';
        const blob = new Blob(this.chunks, { type });
        this.stopTracks();
        this.submitAudio(blob, 'recording.webm');
      };
      this.mediaRecorder.start();
      this.recording.set(true);
    } catch {
      this.recordError.set('Microphone access was denied.');
    }
  }

  stopRecording(): void {
    if (this.mediaRecorder && this.recording()) {
      this.recording.set(false);
      this.mediaRecorder.stop(); // triggers onstop -> submitAudio
    }
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = ''; // allow re-selecting the same file later
    if (file) {
      this.submitAudio(file, file.name);
    }
  }

  private submitAudio(audio: Blob, filename: string): void {
    this.submitting.set(true);
    this.recordError.set(null);
    this.sessions.addTurn(this.sessionId, audio, filename).subscribe({
      next: () => {
        this.submitting.set(false);
        this.load(); // reload to show the new turn + tutor reply + corrections
      },
      error: (err) => {
        this.submitting.set(false);
        this.recordError.set(
          err.status === 409
            ? 'This session is closed.'
            : 'Could not process the audio. Please try again.',
        );
      },
    });
  }

  private stopTracks(): void {
    this.mediaRecorder?.stream.getTracks().forEach((t) => t.stop());
    this.mediaRecorder = null;
  }
}
