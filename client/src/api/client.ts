/**
 * API client module for communicating with the usched backend services.
 *
 * Provides typed endpoints for course catalog discovery, schedule conflict
 * validation, degree audit evaluation, and streaming advisor chat via SSE.
 */

import type {
  ActionChip,
  ApExamDefinition,
  ChatMessage,
  Course,
  DegreeAuditResponse,
  DegreeProgram,
  GeAuditSummary,
  Section,
  UserApCredit,
} from '../types';

const API_BASE = '/api';

/**
 * Filter parameters for searching and narrowing courses in the catalog.
 */
export interface CourseQueryParams {
  readonly q?: string;
  readonly dept?: string;
  readonly ge?: string;
  readonly min_rmp?: number;
  readonly limit?: number;
  readonly offset?: number;
}

/**
 * Returns the canonical USC Schedule of Classes URL for a given course code.
 *
 * USC's Angular catalogue application routes directly to:
 * `https://classes.usc.edu/term/{term}/catalogue/course/{courseSmashed}`
 * (e.g. `https://classes.usc.edu/term/20271/catalogue/course/AAN500`).
 */
export function getUscCourseUrl(courseId: string, term = '20271'): string {
  const smashed = courseId.replace(/[^A-Za-z0-9]/g, '').toUpperCase();
  return `https://classes.usc.edu/term/${term}/catalogue/course/${smashed}`;
}

/**
 * Fetches course catalog offerings matching the supplied filter query.
 */
export async function getCourses(
  params?: CourseQueryParams,
): Promise<readonly Course[]> {
  const searchParams = new URLSearchParams();
  if (params?.q) {
    searchParams.set('q', params.q);
  }
  if (params?.dept) {
    searchParams.set('dept', params.dept);
  }
  if (params?.ge) {
    searchParams.set('ge', params.ge);
  }
  if (params?.min_rmp !== undefined && params.min_rmp > 0) {
    searchParams.set('min_rmp', params.min_rmp.toString());
  }
  if (params?.limit !== undefined && params.limit > 0) {
    searchParams.set('limit', params.limit.toString());
  }
  if (params?.offset !== undefined && params.offset > 0) {
    searchParams.set('offset', params.offset.toString());
  }

  const query = searchParams.toString();
  const url = `${API_BASE}/courses${query ? `?${query}` : ''}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch courses: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Retrieves detailed catalog metadata and section offerings for a course.
 */
export async function getCourseDetail(courseId: string): Promise<Course> {
  const encodedId = encodeURIComponent(courseId);
  const res = await fetch(`${API_BASE}/courses/${encodedId}`);
  if (!res.ok) {
    throw new Error(`Course not found: ${courseId}`);
  }
  return res.json();
}

/**
 * Retrieves detailed section objects for a list of section IDs.
 */
export async function getSections(
  sectionIds: readonly string[],
): Promise<readonly Section[]> {
  if (sectionIds.length === 0) {
    return [];
  }
  const param = encodeURIComponent(sectionIds.join(','));
  const res = await fetch(`${API_BASE}/schedule/sections?ids=${param}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch sections: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Lists every department code in the catalog, such as "CSCI".
 */
export async function getDepartments(): Promise<readonly string[]> {
  const res = await fetch(`${API_BASE}/courses/departments`);
  if (!res.ok) {
    throw new Error(`Failed to fetch departments: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Retrieves standard USC AP exam equivalency definitions.
 */
export async function getApExams(): Promise<readonly ApExamDefinition[]> {
  const res = await fetch(`${API_BASE}/ge/ap-exams`);
  if (!res.ok) {
    throw new Error(`Failed to fetch AP exams: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Audits student progress across USC General Education categories.
 */
export async function getGeAudit(
  completedCourses: readonly string[],
  apCredits: readonly UserApCredit[],
): Promise<GeAuditSummary> {
  const res = await fetch(`${API_BASE}/ge/audit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      completed_courses: completedCourses,
      ap_credits: apCredits,
    }),
  });
  if (!res.ok) {
    throw new Error(`GE audit failed: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Retrieves all registered degree program curricula.
 */
export async function getDegrees(): Promise<readonly DegreeProgram[]> {
  const res = await fetch(`${API_BASE}/degrees`);
  if (!res.ok) {
    throw new Error(`Failed to fetch degrees: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Computes graduation checklist fulfillment and prerequisite DAG status for
 * a target degree program against completed courses.
 */
export async function getDegreeAudit(
  degreeId: string,
  completedCourses: readonly string[] = [],
): Promise<DegreeAuditResponse> {
  const completedParam = encodeURIComponent(completedCourses.join(','));
  const encodedDegree = encodeURIComponent(degreeId);
  const url =
    `${API_BASE}/degrees/${encodedDegree}/audit` +
    `?completed=${completedParam}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Degree audit failed: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Initiates an SSE streaming dialogue with the AI academic advisor agent.
 *
 * Returns a cancellation callback to abort the in-flight connection.
 */
export async function streamAdvisorChat(
  message: string,
  history: readonly ChatMessage[],
  enrolledCourses: readonly string[],
  wishlistCourses: readonly string[],
  completedCourses: readonly string[],
  degreeId: string,
  onToken: (token: string) => void,
  onChips: (chips: readonly ActionChip[]) => void,
  onDone: () => void,
): Promise<() => void> {
  const controller = new AbortController();

  const body = {
    message,
    history: history.map((h) => ({ role: h.role, content: h.content })),
    enrolled_courses: enrolledCourses,
    wishlist_courses: wishlistCourses,
    completed_courses: completedCourses,
    degree_id: degreeId,
  };

  void (async () => {
    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        onToken('Sorry, I encountered an issue connecting to the advisor.');
        onDone();
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data:')) {
            continue;
          }

          const dataStr = trimmed.slice(5).trim();
          if (dataStr === '[DONE]') {
            onDone();
            return;
          }

          try {
            const parsed = JSON.parse(dataStr);
            if (typeof parsed.token === 'string') {
              onToken(parsed.token);
            }
            if (Array.isArray(parsed.action_chips)) {
              onChips(parsed.action_chips);
            }
          } catch {
            // Ignore non-JSON SSE heartbeat or metadata chunks safely.
          }
        }
      }
      onDone();
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== 'AbortError') {
        onToken('\n*(Advisor connection closed)*');
      }
      onDone();
    }
  })();

  return () => controller.abort();
}
