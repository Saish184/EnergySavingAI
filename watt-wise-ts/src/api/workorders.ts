/**
 * Work-order adapter. The backend owns the lifecycle; this file maps its statuses to labels and to the requests its
 * API accepts. Current backend (mina + saish-llm-integration):
 *   open -> sent -> repaired -> verification;  technician outcome at open/sent:
 *   fault_found=true -> finding CONFIRMED;  fault_found=false -> finding DISMISSED, work order closed_no_fault.
 * Opening a work order does not confirm anything. Unknown statuses are shown verbatim with no actions.
 */
import type { WorkOrderPatch } from './client';
import type { WorkOrderRaw } from './contracts';

export type WorkOrderAction =
  | { kind: 'patch'; body: WorkOrderPatch; label: string; tone?: 'primary' | 'secondary' }
  | { kind: 'verify_simulated'; label: string };

export interface WorkOrderView {
  id: string;
  findingId: string;
  flatId: string;
  status: string;
  statusLabel: string;
  outcome: string;
  actions: WorkOrderAction[];
  verification: WorkOrderRaw['verification'];
  simulated: boolean;
}

const LABEL: Record<string, string> = {
  open: 'Open: technician not yet sent',
  sent: 'Sent to technician',
  repaired: 'Repaired, waiting for post-repair data',
  closed_no_fault: 'Closed: technician found no fault',
};

function outcomeActions(w: WorkOrderRaw): WorkOrderAction[] {
  if (w.fault_found != null) return [];
  return [
    { kind: 'patch', body: { fault_found: true }, label: 'Technician: fault found' },
    { kind: 'patch', body: { fault_found: false }, label: 'Technician: no fault found', tone: 'secondary' },
  ];
}

export function actionsFor(w: WorkOrderRaw): WorkOrderAction[] {
  if (w.verification) return [];
  switch (w.status) {
    case 'open':
      return [{ kind: 'patch', body: { status: 'sent' }, label: 'Mark as sent to technician' }, ...outcomeActions(w)];
    case 'sent':
      return [...outcomeActions(w), { kind: 'patch', body: { status: 'repaired' }, label: 'Mark as repaired' }];
    case 'repaired':
      return [{ kind: 'verify_simulated', label: 'Verify with SIMULATED post-repair data (demo)' }];
    default:
      return [];
  }
}

export function toView(w: WorkOrderRaw): WorkOrderView {
  const v = w.verification;
  return {
    id: w.id,
    findingId: w.finding_id,
    flatId: w.flat_id,
    status: w.status,
    statusLabel: LABEL[w.status] ?? w.status,
    outcome: w.fault_found === true ? 'Technician found a fault' : w.fault_found === false ? 'Technician found no fault' : 'No technician outcome yet',
    actions: actionsFor(w),
    verification: v,
    simulated: Boolean(v?.simulated),
  };
}

export function byFinding(list: WorkOrderRaw[]): Map<string, WorkOrderView> {
  return new Map(list.map((w) => [w.finding_id, toView(w)]));
}
