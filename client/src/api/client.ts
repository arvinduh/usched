/**
 * Typed calls to the usched API, one function per route.
 *
 * Course and section routes are scoped by term. Shapes come from the
 * generated schema; this module owns only URLs, encoding,
 * and turning non-2xx responses into errors.
 */

import type { components } from './schema';
import { API_BASE_URL } from '../config';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`);
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`POST ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

/** Lists every term, newest first. */
export function getTerms(): Promise<readonly components['schemas']['Term'][]> {
  return get('/terms');
}

/** Filters for a course search; omitted fields do not filter. */
export interface CourseQuery {
  readonly q?: string;
  readonly ge?: string;
  readonly minRating?: number;
  readonly limit?: number;
  readonly offset?: number;
}

/** Searches a term's courses. */
export function searchCourses(
  term: number,
  query: CourseQuery,
): Promise<readonly components['schemas']['Course'][]> {
  const params = new URLSearchParams();
  if (query.q) {
    params.set('q', query.q);
  }
  if (query.ge) {
    params.set('ge', query.ge);
  }
  if (query.minRating) {
    params.set('min_rating', String(query.minRating));
  }
  if (query.limit) {
    params.set('limit', String(query.limit));
  }
  if (query.offset) {
    params.set('offset', String(query.offset));
  }
  const suffix = params.size ? `?${params}` : '';
  return get(`/terms/${term}/courses${suffix}`);
}

/** Loads the given courses as offered in a term, skipping the rest. */
export function getCourses(
  term: number,
  codes: readonly string[],
): Promise<readonly components['schemas']['Course'][]> {
  if (codes.length === 0) {
    return Promise.resolve([]);
  }
  return get(`/terms/${term}/courses?codes=${encodeURIComponent(codes.join(','))}`);
}

/** Loads one course as offered in a term; rejects when it is not. */
export function getCourse(
  term: number,
  code: string,
): Promise<components['schemas']['Course']> {
  return get(`/terms/${term}/courses/${encodeURIComponent(code)}`);
}

/** Loads a term's sections by number. */
export function getSections(
  term: number,
  ids: readonly string[],
): Promise<readonly components['schemas']['Section'][]> {
  if (ids.length === 0) {
    return Promise.resolve([]);
  }
  return get(`/terms/${term}/sections?ids=${encodeURIComponent(ids.join(','))}`);
}

/**
 * Recognizes course codes written any way, answering with the catalog's
 * spelling and title for each known course; unknown codes are left out.
 */
export function lookupCourses(
  codes: readonly string[],
): Promise<readonly components['schemas']['KnownCourse'][]> {
  return get(`/courses?codes=${encodeURIComponent(codes.join(','))}`);
}

/** Lists the current catalogue's programs. */
export function getPrograms(): Promise<readonly components['schemas']['ProgramSummary'][]> {
  return get('/programs');
}

/** Loads a program's requirement tree. */
export function getProgram(id: string): Promise<components['schemas']['Program']> {
  return get(`/programs/${encodeURIComponent(id)}`);
}

/** Audits a program against what the student did, as of a planning term. */
export function auditProgram(
  term: number,
  id: string,
  completed: readonly string[],
  apCredits: readonly components['schemas']['ApCredit'][],
  geCounted: Readonly<Record<string, number>>,
): Promise<components['schemas']['ProgramAudit']> {
  return post(`/terms/${term}/programs/${encodeURIComponent(id)}/audit`, {
    completed,
    ap_credits: apCredits,
    ge_counted: geCounted,
  });
}

/** Lists GE categories and how many courses each needs. */
export function getGeCategories(): Promise<readonly components['schemas']['GeCategory'][]> {
  return get('/ge-categories');
}

/** Shows how courses, AP exams, and seats counted by hand fill each GE. */
export function auditGe(
  completed: readonly string[],
  apCredits: readonly components['schemas']['ApCredit'][],
  geCounted: Readonly<Record<string, number>>,
): Promise<readonly components['schemas']['GeProgress'][]> {
  return post('/ge-audit', { completed, ap_credits: apCredits, ge_counted: geCounted });
}

/** Lists AP exams USC grants credit for. */
export function getApExams(): Promise<readonly components['schemas']['ApExam'][]> {
  return get('/ap-exams');
}

/** Callbacks for one streamed advisor reply. */
export interface ChatHandlers {
  readonly onToken: (token: string) => void;
  /** A tool the advisor started, in words ("Searching courses for …"). */
  readonly onStep: (step: string) => void;
  /** A piece of the advisor's reasoning summary. */
  readonly onThought: (text: string) => void;
  /** The reply's last event: chips and any unverified courses. */
  readonly onClose: (event: components['schemas']['ClosingEvent']) => void;
  readonly onDone: () => void;
}

/**
 * Streams the advisor's reply to `request` over Server-Sent Events.
 *
 * Returns a function that aborts the reply. `onDone` runs exactly once,
 * whether the stream ends, fails, or is aborted.
 */
export function streamChat(
  request: components['schemas']['ChatRequest'],
  { onToken, onStep, onThought, onClose, onDone }: ChatHandlers,
): () => void {
  const controller = new AbortController();
  let finished = false;
  const finish = (): void => {
    if (!finished) {
      finished = true;
      onDone();
    }
  };
  void (async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify(request),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        onToken('The advisor could not be reached.');
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done) {
          return;
        }
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop() ?? '';
        for (const event of events) {
          const data = event.replace(/^data: ?/, '');
          if (data === '[DONE]') {
            return;
          }
          const parsed = JSON.parse(data) as
            | { readonly token: string }
            | { readonly step: string }
            | { readonly thought: string }
            | components['schemas']['ClosingEvent'];
          if ('token' in parsed) {
            onToken(parsed.token);
          } else if ('step' in parsed) {
            onStep(parsed.step);
          } else if ('thought' in parsed) {
            onThought(parsed.thought);
          } else {
            onClose(parsed);
          }
        }
      }
    } catch (err: unknown) {
      if (!(err instanceof DOMException && err.name === 'AbortError')) {
        onToken('\n(The advisor connection closed.)');
      }
    } finally {
      finish();
    }
  })();
  return () => controller.abort();
}
