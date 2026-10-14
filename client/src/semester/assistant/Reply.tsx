/**
 * Renders one advisor reply's Markdown as paragraphs and lists.
 *
 * Models answer in loose Markdown: paragraphs, "-" or "1." lists, bold,
 * italics, inline code, and the odd heading. This covers that subset and
 * nothing more, so no Markdown dependency ships. Course codes become links
 * that open the course, marked the way the degree marks them (taken, or on
 * this term's week), except codes the server could not find in the
 * catalog, which stay plain and marked. The thread owns everything around
 * the text.
 */

import { CalendarDays, Check } from "lucide-react";
import React from "react";
import styles from "./Thread.module.css";

/** Course codes as prose writes them: "CSCI-104L", "CSCI 104L", "MUSC 200gmw". */
const CODE = /\b([A-Z]{2,5})[- ](\d{3}[A-Za-z]{0,4})\b/g;
const BULLET = /^\s*[-*•]\s+/;
const NUMBERED = /^\s*\d+[.)]\s+/;
const HEADING = /^\s*#{1,6}\s+/;
/** Bold, italic, and inline code spans; bold first so `**` wins over `*`. */
const SPAN = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;

type Block =
  | { readonly kind: "p" | "h"; readonly text: string }
  | { readonly kind: "ul" | "ol"; readonly items: string[] };

/**
 * Groups lines into blocks: consecutive list lines form one list, and a
 * blank line or a heading ends a paragraph.
 */
function parse(text: string): Block[] {
  const blocks: Block[] = [];
  let lines: string[] = [];
  const flush = (): void => {
    if (lines.length > 0) {
      blocks.push({ kind: "p", text: lines.join(" ") });
      lines = [];
    }
  };
  for (const line of text.split("\n")) {
    const list = BULLET.test(line) ? "ul" : NUMBERED.test(line) ? "ol" : null;
    if (list) {
      flush();
      const item = line.replace(list === "ul" ? BULLET : NUMBERED, "");
      const last = blocks.at(-1);
      if (last?.kind === list) {
        last.items.push(item);
      } else {
        blocks.push({ kind: list, items: [item] });
      }
    } else if (HEADING.test(line)) {
      flush();
      blocks.push({ kind: "h", text: line.replace(HEADING, "") });
    } else if (line.trim()) {
      lines.push(line.trim());
    } else {
      flush();
    }
  }
  flush();
  return blocks;
}

/**
 * Properties for one reply.
 */
export interface ReplyProps {
  readonly text: string;
  /** Codes as the server wrote them ("MUSC 200gmw") that no catalog has. */
  readonly unverified: ReadonlySet<string>;
  /** Opens a course mentioned in the reply, given as "DEPT-123X". */
  readonly onOpenCourse: (courseId: string) => void;
  /** Where a course stands in the student's plan, if anywhere. */
  readonly stateOf: (courseId: string) => CourseState;
}

/** A course the student took, or has on this term's week. */
export type CourseState = "taken" | "planned" | null;

/**
 * Renders the reply's blocks.
 */
export function Reply(props: ReplyProps): React.JSX.Element {
  const { text, unverified, onOpenCourse, stateOf } = props;
  const codes = (part: string): React.ReactNode[] => {
    const nodes: React.ReactNode[] = [];
    let last = 0;
    for (const m of part.matchAll(CODE)) {
      const at = m.index;
      nodes.push(part.slice(last, at));
      nodes.push(
        unverified.has(`${m[1]} ${m[2]}`) ? (
          <span
            key={at}
            className={styles.unknownCode}
            title="Not in USC's catalog"
          >
            {m[0]}
          </span>
        ) : (
          <CodeLink
            key={at}
            text={m[0]}
            state={stateOf(`${m[1]}-${m[2]}`)}
            onOpen={() => onOpenCourse(`${m[1]}-${m[2]}`)}
          />
        ),
      );
      last = at + m[0].length;
    }
    nodes.push(part.slice(last));
    return nodes;
  };

  const inline = (line: string): React.ReactNode =>
    line.split(SPAN).map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
        return <strong key={i}>{codes(part.slice(2, -2))}</strong>;
      }
      if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
        return (
          <React.Fragment key={i}>{codes(part.slice(1, -1))}</React.Fragment>
        );
      }
      if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
        return <em key={i}>{codes(part.slice(1, -1))}</em>;
      }
      return <React.Fragment key={i}>{codes(part)}</React.Fragment>;
    });

  return (
    <div className={styles.text}>
      {parse(text).map((block, i) => {
        switch (block.kind) {
          case "p":
            return <p key={i}>{inline(block.text)}</p>;
          case "h":
            return (
              <p key={i} className={styles.heading}>
                {inline(block.text)}
              </p>
            );
          case "ul":
          case "ol": {
            const List = block.kind;
            return (
              <List key={i}>
                {block.items.map((item, j) => (
                  <li key={j}>{inline(item)}</li>
                ))}
              </List>
            );
          }
        }
      })}
    </div>
  );
}

function CodeLink({
  text,
  state,
  onOpen,
}: {
  readonly text: string;
  readonly state: CourseState;
  readonly onOpen: () => void;
}): React.JSX.Element {
  const cls =
    state === "taken"
      ? styles.codeTaken
      : state === "planned"
        ? styles.codePlanned
        : "";
  return (
    <button
      type="button"
      className={`${styles.code} ${cls}`}
      title={
        state === "taken"
          ? "Taken"
          : state === "planned"
            ? "On your week"
            : undefined
      }
      onClick={onOpen}
    >
      {state === "taken" && <Check size={10} />}
      {state === "planned" && <CalendarDays size={10} />}
      {text}
    </button>
  );
}
