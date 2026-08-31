import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Session, SessionDetail, TopicMistakes, TurnResult } from './models';

@Injectable({ providedIn: 'root' })
export class SessionsService {
  private readonly http = inject(HttpClient);

  list(): Observable<Session[]> {
    return this.http.get<Session[]>('/api/sessions');
  }

  get(id: string): Observable<SessionDetail> {
    return this.http.get<SessionDetail>(`/api/sessions/${id}`);
  }

  start(): Observable<Session> {
    return this.http.post<Session>('/api/sessions', {});
  }

  /** The user's mistakes grouped by topic (default ordered by `topic`). */
  listMistakes(orderBy: string = 'topic'): Observable<TopicMistakes[]> {
    const params = new HttpParams().set('order_by', orderBy);
    return this.http.get<TopicMistakes[]>('/api/mistakes', { params });
  }

  /** Submit one spoken turn: runs STT -> LLM -> TTS on the backend. */
  addTurn(sessionId: string, audio: Blob, filename: string): Observable<TurnResult> {
    const form = new FormData();
    form.append('audio', audio, filename);
    return this.http.post<TurnResult>(`/api/sessions/${sessionId}/turns`, form);
  }
}
