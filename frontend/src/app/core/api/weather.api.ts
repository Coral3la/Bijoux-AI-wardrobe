import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Weather } from '../../shared/models/weather.model';

@Injectable({ providedIn: 'root' })
export class WeatherApi {
  private readonly http = inject(HttpClient);

  // The coordinates are the caller's, not this service's. They come from
  // `users.home_lat`/`home_lon`, which DECISIONS.md 151 made one field in three
  // columns — so "which coordinates" is a question about the account, and the
  // one place that can answer it is the store holding the current user.
  get(lat: number, lon: number, date: string): Observable<Weather> {
    return this.http.get<Weather>(`${environment.apiUrl}/weather`, {
      params: { lat, lon, date },
    });
  }
}
