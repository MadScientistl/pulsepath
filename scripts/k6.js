import http from 'k6/http';
import { check } from 'k6';
export const options = { vus: 20, duration: '2m' };
export default function () {
  const r = http.get(__ENV.TARGET_URL || 'http://localhost:8080/');
  check(r, { 'HTTP 2xx/3xx': x => x.status < 400 });
}
