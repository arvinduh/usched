/**
 * Domain types: server shapes re-exported from the generated API schema,
 * plus the few shapes only the client owns.
 *
 * Server types come from `api/schema.d.ts` (`npm run api` regenerates it),
 * so a server model change surfaces here as a type error rather than a
 * runtime surprise. Client-owned types describe the student's plan and the
 * ephemeral chat thread.
 */

import type { components } from '../api/schema';

type Schemas = components['schemas'];

export type Term = Schemas['Term'];
export type Course = Schemas['Course'];
export type Section = Schemas['Section'];
export type Meeting = Schemas['Meeting'];
export type Weekday = Schemas['Weekday'];
export type Instructor = Schemas['Instructor'];
export type Rating = Schemas['Rating'];
export type Units = Schemas['Units'];
export type CourseRef = Schemas['CourseRef'];
export type RequisiteGroup = Schemas['RequisiteGroup'];
export type Restriction = Schemas['Restriction'];
export type KnownCourse = Schemas['KnownCourse'];
export type ProgramSummary = Schemas['ProgramSummary'];
export type Program = Schemas['Program'];
export type Requirement = Schemas['Requirement'];
export type RequirementChoice = Schemas['RequirementChoice'];
export type ProgramAudit = Schemas['ProgramAudit'];
export type RequirementProgress = Schemas['RequirementProgress'];
export type RequirementStatus = Schemas['RequirementStatus'];
export type GeCategory = Schemas['GeCategory'];
export type GeProgress = Schemas['GeProgress'];
export type ApExam = Schemas['ApExam'];
export type ApCredit = Schemas['ApCredit'];
export type ChatRequest = Schemas['ChatRequest'];
export type Screen = Schemas['Screen'];
export type Variant = Schemas['Variant'];
export type ClosingEvent = Schemas['ClosingEvent'];
export type Chip = ClosingEvent['action_chips'][number];

/**
 * One schedule variant of a term: the sections the student picked.
 */
export interface ScheduleConfiguration {
  readonly id: string;
  readonly name: string;
  readonly section_ids: readonly string[];
}

/**
 * A message in the advisor thread; lives only until reload.
 */
export interface ChatMessage {
  readonly id: string;
  readonly role: 'user' | 'assistant';
  readonly content: string;
  readonly chips?: readonly Chip[];
  /** Courses the reply names that the catalog does not have. */
  readonly unverified?: readonly string[];
}
