import type { Activity, Category, Demo, DraftResponse, DraftStep, Hospital, Id, Integrations, PublicResult, Specialty, Task, TaskInput, TaskStatus, Vaccine, VaccineDetail } from './types';

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

const STATUS_MESSAGES: Record<number, string> = {
  403: '이 시연 요청에 응답할 수 없습니다.',
  404: '요청한 시연 데이터를 찾을 수 없습니다.',
  409: '현재 상태에서는 처리할 수 없습니다. 담당 요청과 할 일 상태를 확인해 주세요.',
  422: '입력 내용이 올바르지 않습니다. 필수 항목과 형식을 확인해 주세요.',
  429: '요청이 많습니다. 잠시 후 다시 시도해 주세요.',
  502: '외부 정보를 확인하지 못했습니다. 다시 시도해 주세요.',
  503: '서버 또는 시연 연동을 현재 사용할 수 없습니다.',
};

function statusError(status: number): ApiError {
  return new ApiError(`${STATUS_MESSAGES[status] ?? '요청을 처리하지 못했습니다.'} (오류 ${status})`);
}

function connectionError(error: unknown): ApiError {
  if (error instanceof DOMException && error.name === 'TimeoutError') {
    return new ApiError('요청 시간이 초과되었습니다.');
  }
  return new ApiError('서버에 연결하지 못했습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.');
}

async function send(path: string, options?: RequestInit, timeout = 15000): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...options,
      signal: options?.signal ?? AbortSignal.timeout(timeout),
      headers: { 'Content-Type': 'application/json', ...options?.headers },
    });
  } catch (error) {
    throw connectionError(error);
  }
  if (!response.ok) throw statusError(response.status);
  return response;
}

async function request<T>(path: string, options?: RequestInit, timeout = 15000): Promise<T> {
  const response = await send(path, options, timeout);
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
  return object(value) && isIntegration(value.agent);
}

function isActivity(value: unknown): value is Activity[] {
  return Array.isArray(value) && value.every((item: unknown) =>
    object(item) && typeof item.event_id === 'string' && typeof item.task_id === 'string'
    && typeof item.kind === 'string' && typeof item.detail === 'string' && typeof item.created_at === 'string');
}

function isDraftStep(value: unknown): value is DraftStep {
  return hasStringFields(value, ['step', 'label', 'agent', 'at']);
}

function isDraftResponse(value: unknown): value is DraftResponse {
  return object(value) && Array.isArray(value.drafts) && value.drafts.length > 0 && value.drafts.length <= 3
    && value.drafts.every((item: unknown) => object(item) && typeof item.title === 'string'
      && typeof item.description === 'string' && typeof item.uncertainty === 'string'
      && ['benefit', 'vaccination_checkup', 'regular_visit'].includes(String(item.category))
      && isId(item.source_id))
    && object(value.source) && isId(value.source.id) && typeof value.source.title === 'string'
    && typeof value.source.provider === 'string' && typeof value.source.url === 'string'
    && (value.source.checked_at === null || typeof value.source.checked_at === 'string')
    && typeof value.source.summary === 'string'
    && (value.evidence === null || (object(value.evidence) && object(value.evidence.source)
      && typeof value.evidence.source.title === 'string' && typeof value.evidence.source.url === 'string'
      && typeof value.evidence.retrieved_at === 'string' && Array.isArray(value.evidence.items)
      && value.evidence.items.every((item: unknown) => hasStringFields(item, ['code', 'name']))))
    && (value.review === undefined || (object(value.review) && typeof value.review.approved === 'boolean'
      && typeof value.review.attempts === 'number' && typeof value.review.checked_by === 'string'))
    && (value.trace === undefined || (Array.isArray(value.trace)
      && value.trace.every((item: unknown) => hasStringFields(item, ['step', 'label', 'agent', 'status', 'detail', 'at']))));
}

function hasStringFields<K extends string>(value: unknown, fields: readonly K[]): value is Record<K, string> {
  return object(value) && fields.every((field) => typeof value[field] === 'string');
}

function publicResult<T>(value: unknown, validate: (item: unknown) => item is T): PublicResult<T> {
  if (!object(value) || !object(value.source) || typeof value.source.title !== 'string'
    || typeof value.source.url !== 'string' || typeof value.retrieved_at !== 'string'
    || !Array.isArray(value.items) || !value.items.every(validate)) {
    throw new ApiError('공공데이터 응답 형식이 올바르지 않습니다.');
  }
  return {
    source: { title: value.source.title, url: value.source.url },
    retrieved_at: value.retrieved_at,
    items: value.items,
  };
}

function verify<T>(value: unknown, validate: (value: unknown) => value is T): T {
  if (!validate(value)) throw new ApiError('서버 응답 형식이 올바르지 않습니다. 다시 시도해 주세요.');
  return value;
}

function parseSseBlock(block: string): { kind: string; data: unknown } | null {
  let kind = 'message';
  const dataLines: string[] = [];
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) kind = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    return { kind, data: JSON.parse(dataLines.join('\n')) as unknown };
  } catch {
    throw new ApiError('서버 응답을 읽지 못했습니다. 다시 시도해 주세요.');
  }
}

async function draftStream(category: Category, onStep: (step: DraftStep) => void): Promise<DraftResponse> {
  const response = await send('/api/agent/draft/stream', json('POST', { category, acknowledged: true }), 150000);
  if (!response.body) throw new ApiError('서버 응답을 읽지 못했습니다. 다시 시도해 주세요.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result: DraftResponse | null = null;
  const handle = (block: string) => {
    const event = parseSseBlock(block);
    if (!event) return;
    if (event.kind === 'step' && isDraftStep(event.data)) onStep(event.data);
    else if (event.kind === 'result') result = verify(event.data, isDraftResponse);
    else if (event.kind === 'error') {
      const status = object(event.data) && typeof event.data.status === 'number' ? event.data.status : 503;
      throw statusError(status);
    }
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      handle(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf('\n\n');
    }
  }
  if (buffer.trim()) handle(buffer);
  if (!result) throw new ApiError('AI 초안 응답이 끊어졌습니다. 다시 시도해 주세요.');
  return result;
}

export const api = {
  demo: async () => verify(await request<unknown>('/api/demo'), isDemo),
  integrations: async () => verify(await request<unknown>('/api/integrations'), isIntegrations),
  activity: async (id: Id) => verify(await request<unknown>(`/api/tasks/${encodeURIComponent(String(id))}/activity`), isActivity),
  draft: async (category: Category) => verify(await request<unknown>(
    '/api/agent/draft', json('POST', { category, acknowledged: true }), 150000,
  ), isDraftResponse),
  draftStream,
  hospitals: async (name: string) => publicResult<Hospital>(
    await request<unknown>('/api/public/hospitals', json('POST', { name })),
    (item): item is Hospital => hasStringFields(item, ['id', 'name', 'address', 'phone', 'type']),
  ),
  specialties: async (id: string) => publicResult<Specialty>(
    await request<unknown>('/api/public/hospital-specialties', json('POST', { hospital_id: id })),
    (item): item is Specialty => hasStringFields(item, ['name', 'specialists']),
  ),
  vaccines: async () => publicResult<Vaccine>(await request<unknown>('/api/public/vaccines'),
    (item): item is Vaccine => hasStringFields(item, ['code', 'name'])),
  vaccineDetail: async (code: string) => publicResult<VaccineDetail>(
    await request<unknown>(`/api/public/vaccines/${encodeURIComponent(code)}`),
    (item): item is VaccineDetail => hasStringFields(item, ['title', 'message'])),
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
