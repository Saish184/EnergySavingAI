/**
 * Work-order adapter. The backend owns the lifecycle; this file only maps its current statuses to labels and to the
 * actions its API accepts (mina: open -> sent -> repaired, then verification). Saish is reworking the lifecycle
 * (e.g. fault_found / dismissed): extend ACTIONS here; unknown statuses are shown verbatim with no actions,
 * so a new backend status never breaks the UI.
 */
import type { WorkOrderRaw } from './contracts';

export type WorkOrderAction =
  | { kind: 'patch'; status: string; label: string }
  | { kind: 'verify_simulated'; label: string };

export interface WorkOrderView {
  id: string;
  findingId: string;
  flatId: string;
  status: string;
  statusLabel: string;
  actions: WorkOrderAction[];
  verification: WorkOrderRaw['verification'];
  simulated: boolean;
}

const LABEL: Record<string, string> = {
  open: 'Open',
  sent: 'Sent to technician',
  repaired: 'Repaired, waiting for post-repair data',
};

const ACTIONS: Record<string, WorkOrderAction[]> = {
  open: [{ kind: 'patch', status: 'sent', label: 'Mark as sent to technician' }],
  sent: [{ kind: 'patch', status: 'repaired', label: 'Mark as repaired' }],
  repaired: [{ kind: 'verify_simulated', label: 'Run verification with SIMULATED post-repair data (demo)' }],
};

export function toView(w: WorkOrderRaw): WorkOrderView {
  const verified = w.verification != null;
  const simulated = Boolean(w.verification?.simulated);
  return {
    id: w.id,
    findingId: w.finding_id,
    flatId: w.flat_id,
    status: w.status,
    statusLabel: verified ? `${LABEL[w.status] ?? w.status} · verification ${w.verification?.status ?? ''}`.trim() : LABEL[w.status] ?? w.status,
    actions: verified ? [] : ACTIONS[w.status] ?? [],
    verification: w.verification,
    simulated,
  };
}

export function byFinding(list: WorkOrderRaw[]): Map<string, WorkOrderView> {
  return new Map(list.map((w) => [w.finding_id, toView(w)]));
}
