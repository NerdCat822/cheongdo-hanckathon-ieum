export type Category = 'benefit' | 'vaccination_checkup' | 'regular_visit';
export type TaskStatus = '확인 필요' | '담당 요청' | '진행 중' | '완료' | '해당 없음';
export type AssignmentStatus = 'unassigned' | 'pending' | 'accepted';
export type Id = string | number;

export interface Task {
  task_id: Id;
  title: string;
  description: string;
  category: Category;
  due_date: string | null;
  status: TaskStatus;
  assignee_id: Id | null;
  requested_assignee_id: Id | null;
  assignment_status: AssignmentStatus;
  source_id: Id | null;
}

export interface Member {
  id: Id;
  name: string;
}

export interface Source {
  id: Id;
  title: string;
  provider: string;
  url: string;
  checked_at: string | null;
  summary: string;
}

export interface Demo {
  profile: { alias: string; region: string };
  members: Member[];
  tasks: Task[];
  sources: Source[];
}

export interface Integrations {
  agent: { available: boolean; reason: string };
  jira: { available: boolean; reason: string };
}

export interface TaskInput {
  title: string;
  description: string;
  category: Category;
  due_date: string | null;
  source_id: Id | null;
}
