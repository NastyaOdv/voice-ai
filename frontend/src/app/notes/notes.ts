import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { TopicMistakes } from '../core/models';
import { SessionsService } from '../core/sessions.service';

@Component({
  selector: 'app-notes',
  imports: [
    MatExpansionModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './notes.html',
  styleUrl: './notes.scss',
})
export class Notes implements OnInit {
  private readonly sessions = inject(SessionsService);

  protected readonly topics = signal<TopicMistakes[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.sessions.listMistakes('topic').subscribe({
      next: (topics) => {
        this.topics.set(topics);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Could not load your notes.');
        this.loading.set(false);
      },
    });
  }
}
