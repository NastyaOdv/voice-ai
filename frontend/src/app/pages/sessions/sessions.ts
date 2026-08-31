import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { RouterLink } from '@angular/router';

import { Session } from '../../core/models';
import { SessionsService } from '../../core/sessions.service';

@Component({
  selector: 'app-sessions',
  imports: [
    DatePipe,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    RouterLink,
  ],
  templateUrl: './sessions.html',
  styleUrl: './sessions.scss',
})
export class Sessions implements OnInit {
  private readonly sessions = inject(SessionsService);

  protected readonly items = signal<Session[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly starting = signal(false);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.sessions.list().subscribe({
      next: (list) => {
        this.items.set(list);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Could not load your sessions.');
        this.loading.set(false);
      },
    });
  }

  startSession(): void {
    if (this.starting()) {
      return;
    }
    this.starting.set(true);
    this.sessions.start().subscribe({
      next: (session) => {
        this.items.update((list) => [session, ...list]);
        this.starting.set(false);
      },
      error: () => {
        this.error.set('Could not start a new session.');
        this.starting.set(false);
      },
    });
  }
}
