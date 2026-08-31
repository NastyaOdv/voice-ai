import { HttpInterceptorFn } from '@angular/common/http';

/**
 * Send the httponly auth cookies with every API request. Without this the browser
 * would drop the access/refresh cookies and every call would be unauthenticated.
 */
export const credentialsInterceptor: HttpInterceptorFn = (req, next) =>
  next(req.clone({ withCredentials: true }));
