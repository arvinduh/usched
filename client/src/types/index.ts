/**
 * Domain type definitions for the usched course planning and audit platform.
 *
 * Declares typed schemas for courses, sections, instructors, schedule
 * conflicts, degree requirements, prerequisite DAG nodes, and advisor chat
 * messages.
 */

/**
 * Instructor profile with RateMyProfessors evaluation metrics.
 */
export interface Instructor {
  readonly id: string;
  readonly name: string;
  readonly department: string;
  readonly rmp_id: string | null;
  readonly rmp_rating: number | null;
  readonly rmp_difficulty: number | null;
  readonly rmp_num_ratings: number;
  readonly rmp_take_again_percent: number | null;
}

/**
 * Course section offering with scheduled meeting times and registration state.
 */
export interface Section {
  readonly id: string;
  readonly course_id: string;
  readonly section_type: string;
  readonly term: string;
  readonly days: readonly string[];
  readonly start_time: string;
  readonly end_time: string;
  readonly start_minute: number;
  readonly end_minute: number;
  readonly location: string;
  readonly instructor: Instructor | null;
  readonly enrolled: number;
  readonly capacity: number;
  readonly waitlist: number;
  readonly is_wishlist?: boolean;
}

/**
 * Academic course catalog entity including prerequisite structures and
 * available sections.
 */
export interface Course {
  readonly id: string;
  readonly department: string;
  readonly number: string;
  readonly title: string;
  readonly description: string;
  readonly units: number;
  readonly prerequisites_raw: string;
  readonly prerequisites_json: readonly (readonly string[])[];
  readonly corequisites_raw: string;
  readonly ge_category: string | null;
  readonly ge_categories?: readonly string[];
  readonly sections: readonly Section[];
}

/**
 * Prerequisite eligibility status for a course in the degree dependency tree.
 */
export type PrereqStatus = 'completed' | 'eligible' | 'locked';

/**
 * Node in the directed acyclic prerequisite dependency graph.
 */
export interface PrereqNode {
  readonly course_id: string;
  readonly title: string;
  readonly units: number;
  readonly status: PrereqStatus;
  /** Groups that must all be met; any one course satisfies a group. */
  readonly prerequisites: readonly (readonly string[])[];
}

/**
 * Degree requirement grouping checklist.
 */
export interface DegreeCategory {
  readonly name: string;
  readonly required_units: number;
  readonly completed_units: number;
  readonly required_courses: readonly string[];
  readonly completed_courses: readonly string[];
  readonly status: string;
}

/**
 * Degree program curriculum specification.
 */
export interface DegreeProgram {
  readonly id: string;
  readonly title: string;
  readonly school: string;
  readonly total_units: number;
  readonly categories: readonly DegreeCategory[];
}

/**
 * Degree audit evaluation response containing progress and prerequisite graph.
 */
export interface DegreeAuditResponse {
  readonly degree: DegreeProgram;
  readonly total_completed_units: number;
  readonly percent_complete: number;
  readonly prereq_graph: readonly PrereqNode[];
  readonly unfulfilled_prerequisites: readonly string[];
}

/**
 * Schedule option variation with an enrolled section selection.
 */
export interface ScheduleConfiguration {
  readonly id: string;
  readonly name: string;
  readonly is_active?: boolean;
  readonly section_ids: readonly string[];
}

/**
 * Standard AP exam definition with GE fulfillment and course waivers.
 */
export interface ApExamDefinition {
  readonly id: string;
  readonly name: string;
  readonly fulfills_ge_category: string | null;
  readonly waives_courses: readonly string[];
  readonly units: number;
}

/**
 * Student earned AP exam credit score.
 */
export interface UserApCredit {
  readonly exam_id: string;
  readonly score: number;
  readonly added_at?: string;
}

/**
 * Progress for a single USC General Education requirement category.
 */
export interface GeCategoryProgress {
  readonly category: string;
  readonly name: string;
  readonly required_count: number;
  readonly completed_count: number;
  readonly satisfying_courses: readonly string[];
  readonly satisfying_ap: readonly string[];
  readonly is_satisfied: boolean;
}

/**
 * Comprehensive General Education requirement fulfillment summary.
 */
export interface GeAuditSummary {
  readonly total_required: number;
  readonly total_satisfied: number;
  readonly categories: readonly GeCategoryProgress[];
  readonly is_complete: boolean;
}

/**
 * Interactive quick action button attached to an advisor chat message.
 */
export interface ActionChip {
  readonly label: string;
  readonly action: string;
  readonly target?: string;
  readonly course_id?: string;
  readonly section_id?: string;
  readonly section_ids?: readonly string[];
  readonly config_id?: string;
  readonly config_name?: string;
  readonly degree_id?: string;
  readonly payload?: Record<string, unknown>;
}

/**
 * Conversational role of a chat message sender.
 */
export type ChatRole = 'user' | 'assistant' | 'system';

/**
 * Message in the academic advisor conversation history.
 */
export interface ChatMessage {
  readonly id?: string;
  readonly role: ChatRole;
  readonly content: string;
  readonly action_chips?: readonly ActionChip[];
}
