/** Who is signed in. Students are identified by flat only; managers by email. DEMO ONLY: not authentication. */
export type Session = { role: 'student'; flatId: string } | { role: 'manager'; email: string };

export interface Limitation {
  title: string;
  body: string;
}
