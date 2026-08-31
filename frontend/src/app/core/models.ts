// Shared API types, mirroring the backend Pydantic schemas.

export interface User {
  id: string;
  email: string;
  google_sub: string | null;
}

export type SessionStatus = 'active' | 'closed';

export interface Session {
  id: string;
  user_id: string;
  status: SessionStatus;
  summary: string | null;
  created_at: string;
}

export interface Correction {
  id: string;
  topic: string;
  you_said: string;
  better: string;
  note: string;
}

export interface Turn {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  language: string | null;
  corrections: Correction[];
  audio_url: string | null;
  created_at: string;
}

export interface SessionDetail extends Session {
  turns: Turn[];
}

export interface Mistake {
  example: string;
  better: string;
  note: string;
  created_at: string;
}

export interface TopicMistakes {
  topic: string;
  count: number;
  mistakes: Mistake[];
}

export interface TurnResult {
  turn_id: string;
  transcript: string;
  language: string | null;
  spoken_reply: string;
  corrections: Correction[];
  audio_url: string;
}
