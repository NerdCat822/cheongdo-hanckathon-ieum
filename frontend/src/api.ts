import type { Demo, Id, Integrations, Task, TaskInput, TaskStatus } from './types';

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options?.headers },
    });
  } catch {
    throw new ApiError('서버에 연결하지 못했습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.');
  }
  if (!response.ok) {
    const detail: Record<number, string> = {
      403: '이 시연 요청에 응답할 수 없습니다.',
      404: '요청한 시연 데이터를 찾을 수 없습니다.',
      409: '현재 상태에서는 처리할 수 없습니다. 담당 요청과 할 일 상태를 확인해 주세요.',
      422: '입력 내용이 올바르지 않습니다. 필수 항목과 형식을 확인해 주세요.',
      503: '서버 또는 시연 연동을 현재 사용할 수 없습니다.',
    };
    throw new ApiError(`${detail[response.status] ?? '요청을 처리하지 못했습니다.'} (오류 ${response.status})`);
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError('서버 응답을 읽지 못했습니다. 다시 시도해 주세요.');
  }
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  body: JSON.stringify(body),
});

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isId(value: unknown): value is Id {
  return typeof value === 'string' || typeof value === 'number';
}

function isTask(value: unknown): value is Task {
  return object(value)
    && isId(value.task_id)
    && typeof value.title === 'string'
    && typeof value.description === 'string'
    && ['benefit', 'vaccination_checkup', 'regular_visit'].includes(String(value.category))
    && (value.due_date === null || typeof value.due_date === 'string')
    && ['확인 필요', '담당 요청', '진행 중', '완료', '해당 없음'].includes(String(value.status))
    && (value.assignee_id === null || isId(value.assignee_id))
    && (value.requested_assignee_id === null || isId(value.requested_assignee_id))
    && ['unassigned', 'pending', 'accepted'].includes(String(value.assignment_status))
    && (value.source_id === null || isId(value.source_id));
}

function isDemo(value: unknown): value is Demo {
  return object(value)
    && object(value.profile) && typeof value.profile.alias === 'string' && typeof value.profile.region === 'string'
    && Array.isArray(value.tasks) && value.tasks.every(isTask)
    && Array.isArray(value.members) && value.members.every((member: unknown) =>
      object(member) && isId(member.id) && typeof member.name === 'string')
    && Array.isArray(value.sources) && value.sources.every((source: unknown) =>
      object(source) && isId(source.id) && typeof source.title === 'string' && typeof source.provider === 'string'
      && typeof source.url === 'string' && (source.checked_at === null || typeof source.checked_at === 'string')
      && typeof source.summary === 'string');
}

function isIntegrations(value: unknown): value is Integrations {
  const isIntegration = (item: unknown) =>
    object(item) && typeof item.available === 'boolean' && typeof item.reason === 'string';
  return object(value) && isIntegration(value.agent) && isIntegration(value.jira);
}

function verify<T>(value: unknown, validate: (value: unknown) => value is T): T {
  if (!validate(value)) throw new ApiError('서버 응답 형식이 올바르지 않습니다. 다시 시도해 주세요.');
  return value;
}

export const api = {
  demo: async () => verify(await request<unknown>('/api/demo'), isDemo),
  integrations: async () => verify(await request<unknown>('/api/integrations'), isIntegrations),
  createTask: (input: TaskInput) =>
    request<unknown>('/api/tasks', json('POST', {
      title: input.title,
      description: input.description,
      category: input.category,
      ...(input.due_date ? { due_date: input.due_date } : {}),
      ...(input.source_id != null ? { source_id: input.source_id } : {}),
    })).then((value) => verify(value, isTask)),
  updateTask: (id: Id, input: Partial<TaskInput> & { status?: TaskStatus }) =>
    request<unknown>(`/api/tasks/${encodeURIComponent(String(id))}`, json('PATCH', input)).then((value) => verify(value, isTask)),
  requestAssignment: (id: Id, assigneeId: Id) =>
    request<unknown>(`/api/tasks/${encodeURIComponent(String(id))}/assignment-request`, json('POST', { assignee_id: assigneeId })).then((value) => verify(value, isTask)),
  respondAssignment: (id: Id, memberId: Id, decision: 'accept' | 'reject' | 'adjust') =>
    request<unknown>(`/api/tasks/${encodeURIComponent(String(id))}/assignment-response`, json('POST', { member_id: memberId, decision })).then((value) => verify(value, isTask)),
};
