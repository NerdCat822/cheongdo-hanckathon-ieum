import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import {
  AlertCircle, ArrowRight, ArrowUpRight,
  Check, CheckCircle2, ChevronDown, ClipboardList, ExternalLink,
  Info, ListFilter, LoaderCircle, Pencil, Plus, RefreshCw, ShieldCheck,
  Sparkles, X,
} from 'lucide-react';
import { api } from './api';
import type { Activity, Category, Demo, Draft, DraftResponse, Hospital, Id, Integrations, Member, PublicResult, Source, Specialty, Task, TaskInput, TaskStatus, Vaccine, VaccineDetail } from './types';

const categories: Record<Category, string> = {
  benefit: '복지 혜택 · 제도',
  vaccination_checkup: '예방접종 · 검진',
  regular_visit: '정기 방문 · 안부',
};
const categoryIcons: Record<Category, string> = {
  benefit: '🏠',
  vaccination_checkup: '🌿',
  regular_visit: '💬',
};
const statuses: TaskStatus[] = ['확인 필요', '담당 요청', '진행 중', '완료', '해당 없음'];
type QuickFilter = 'all' | 'overdue' | 'upcoming' | 'unassigned';

function isOpen(task: Task) {
  return task.status !== '완료' && task.status !== '해당 없음';
}

function daysUntil(value: string | null): number | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split('-').map(Number);
  const due = Date.UTC(year, month - 1, day);
  const today = new Date();
  return Math.round((due - Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())) / 86400000);
}

function dueLabel(date: string | null) {
  const days = daysUntil(date);
  if (days === null) return date ? `날짜 확인 필요 (${date})` : '기한 미정';
  const formatted = date!.replaceAll('-', '. ');
  if (days < 0) return `${formatted} · ${Math.abs(days)}일 지남`;
  if (days === 0) return `${formatted} · 오늘`;
  if (days <= 7) return `${formatted} · ${days}일 남음`;
  return formatted;
}

function sameId(a: Id | null, b: Id | null) {
  return a !== null && b !== null && String(a) === String(b);
}

function memberName(members: Member[], id: Id | null) {
  if (id === null) return '미배정';
  return members.find((member) => sameId(member.id, id))?.name ?? '알 수 없는 구성원';
}

function safeSourceUrl(source: Source) {
  if (!source.checked_at || !source.provider) return null;
  try {
    const url = new URL(source.url);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
  } catch {
    return null;
  }
}

function ErrorMessage({ children }: { children: ReactNode }) {
  return <div className="error-message" role="alert"><AlertCircle size={17} aria-hidden="true" /> <span>{children}</span></div>;
}

function App() {
  const [demo, setDemo] = useState<Demo | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [integrations, setIntegrations] = useState<Integrations | null>(null);
  const [integrationLoading, setIntegrationLoading] = useState(true);
  const [integrationError, setIntegrationError] = useState('');
  const [quickFilter, setQuickFilter] = useState<QuickFilter>('all');
  const [category, setCategory] = useState('all');
  const [status, setStatus] = useState('all');
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [taskErrors, setTaskErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState('');
  const [editor, setEditor] = useState<{ task: Task | null; category?: Category; draft?: Draft; onDraftSaved?: () => void } | null>(null);
  const [boardView, setBoardView] = useState(false);

  const loadDemo = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const data = await api.demo();
      if (!data?.profile || !Array.isArray(data.tasks) || !Array.isArray(data.members) || !Array.isArray(data.sources)) {
        throw new Error('응답 형식이 올바르지 않습니다.');
      }
      setDemo(data);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : '시연 데이터를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadIntegrations = useCallback(async () => {
    setIntegrationLoading(true);
    setIntegrationError('');
    try {
      const data = await api.integrations();
      if (!data?.agent) throw new Error('연동 상태 응답 형식이 올바르지 않습니다.');
      setIntegrations(data);
    } catch (error) {
      setIntegrations(null);
      setIntegrationError(error instanceof Error ? error.message : '연동 상태를 불러오지 못했습니다.');
    } finally {
      setIntegrationLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDemo();
    void loadIntegrations();
  }, [loadDemo, loadIntegrations]);

  const counts = useMemo(() => {
    const active = demo?.tasks.filter(isOpen) ?? [];
    return {
      overdue: active.filter((task) => { const days = daysUntil(task.due_date); return days !== null && days < 0; }).length,
      upcoming: active.filter((task) => { const days = daysUntil(task.due_date); return days !== null && days >= 0 && days <= 7; }).length,
      unassigned: active.filter((task) => task.assignment_status !== 'accepted').length,
      progress: active.filter((task) => task.status === '진행 중').length,
    };
  }, [demo]);

  const filteredTasks = useMemo(() => (demo?.tasks ?? []).filter((task) => {
    const days = daysUntil(task.due_date);
    if (quickFilter === 'overdue' && !(isOpen(task) && days !== null && days < 0)) return false;
    if (quickFilter === 'upcoming' && !(isOpen(task) && days !== null && days >= 0 && days <= 7)) return false;
    if (quickFilter === 'unassigned' && !(isOpen(task) && task.assignment_status !== 'accepted')) return false;
    return (category === 'all' || task.category === category) && (status === 'all' || task.status === status);
  }), [category, demo, quickFilter, status]);

  const replaceTask = (task: Task, created = false) => {
    setDemo((current) => current && ({
      ...current,
      tasks: created ? [task, ...current.tasks] : current.tasks.map((item) => sameId(item.task_id, task.task_id) ? task : item),
    }));
  };

  const runTask = async (task: Task, action: () => Promise<Task>, success: string) => {
    const id = String(task.task_id);
    if (busy[id]) return;
    setBusy((current) => ({ ...current, [id]: true }));
    setTaskErrors((current) => ({ ...current, [id]: '' }));
    setNotice('');
    try {
      replaceTask(await action());
      setNotice(success);
    } catch (error) {
      setTaskErrors((current) => ({
        ...current,
        [id]: `${error instanceof Error ? error.message : '요청에 실패했습니다.'} 반영 여부는 목록을 새로고침해 확인해 주세요.`,
      }));
    } finally {
      setBusy((current) => ({ ...current, [id]: false }));
    }
  };

  const anyBusy = Object.values(busy).some(Boolean);
  const renderTask = (task: Task, index: number) => <TaskCard key={task.task_id} index={index + 1} task={task} members={demo!.members} sources={demo!.sources} busy={Boolean(busy[String(task.task_id)])} error={taskErrors[String(task.task_id)]} onEdit={() => setEditor({ task })} onChangeStatus={(next) => void runTask(task, () => api.updateTask(task.task_id, { status: next }), '시연 할 일의 상태를 변경했습니다.')} onRequest={(member) => void runTask(task, () => api.requestAssignment(task.task_id, member), '시연 담당 요청을 기록했습니다. 실제 알림은 보내지지 않습니다.')} onResponse={(member, decision) => void runTask(task, () => api.respondAssignment(task.task_id, member, decision), '시연 응답을 기록했습니다.')} />;

  return (
    <>
      <a className="skip-link" href="#tasks">할 일로 바로 가기</a>
      <header className="site-header">
        <div className="header-inner wrap">
          <a className="brand" href="#top" aria-label="이음 홈">
            <span className="brand-mark" aria-hidden="true">이</span>
            <span>이음</span>
          </a>
          <div className="profile-chip"><span className="profile-avatar" aria-hidden="true">🌼</span><span>가상 돌봄 공간</span></div>
        </div>
      </header>

      <main id="top" className="wrap content-wrap">
        <section className="welcome" aria-labelledby="welcome-title">
          <div>
            <p className="eyebrow">우리 가족 돌봄 체크리스트</p>
            <h1 id="welcome-title">오늘도 함께 챙겨요</h1>
            <p className="welcome-note">{demo?.profile.region ?? (loading ? '가상 공간 불러오는 중' : '가상 공간')} · 가상 가족 {demo ? `${demo.members.length}명` : '정보 없음'} · 시연용 예시</p>
          </div>
          <button className="button button-primary" type="button" onClick={() => setEditor({ task: null })} disabled={!demo || loading}><Plus size={21} aria-hidden="true" /> 할 일 추가하기</button>
        </section>

        <aside className="demo-notice" aria-label="공개 시연 안내">
          <ShieldCheck size={24} aria-hidden="true" />
          <p><strong>공개 시연 · 가상 데이터만 사용합니다.</strong> 실명, 연락처, 주소, 건강·소득 정보 등 실제 개인정보는 입력하지 마세요. 복지 자격이나 의료 정보를 판단하지 않습니다.</p>
        </aside>

        <DraftPanel integration={integrations?.agent} loading={integrationLoading} error={integrationError} onReview={(draft, onDraftSaved) => setEditor({ task: null, draft, onDraftSaved })} />

        <section className="tasks-section" id="tasks" aria-labelledby="tasks-title">
          <div className="section-heading">
            <div><h2 id="tasks-title">지금 챙길 일</h2><p className="section-subtitle">담당자와 진행 상태를 한눈에 확인해요.</p></div>
            <span className="section-subtitle" aria-live="polite">모두 {demo?.tasks.length ?? '–'}개</span>
          </div>
          <div className="quick-filters" aria-label="할 일 요약 및 빠른 필터">
            <button type="button" aria-pressed={quickFilter === 'overdue'} onClick={() => setQuickFilter(quickFilter === 'overdue' ? 'all' : 'overdue')}>기한 지남 <strong>{demo ? counts.overdue : '–'}</strong></button>
            <button type="button" aria-pressed={quickFilter === 'upcoming'} onClick={() => setQuickFilter(quickFilter === 'upcoming' ? 'all' : 'upcoming')}>7일 이내 <strong>{demo ? counts.upcoming : '–'}</strong></button>
            <button type="button" aria-pressed={quickFilter === 'unassigned'} onClick={() => setQuickFilter(quickFilter === 'unassigned' ? 'all' : 'unassigned')}>미배정 <strong>{demo ? counts.unassigned : '–'}</strong></button>
            <span>진행 중 <strong>{demo ? counts.progress : '–'}</strong></span>
          </div>
          <p className="filter-help">완료·해당 없음은 요약에서 제외하며, 수락 대기는 미배정에 포함합니다.</p>
          <div className="filter-bar">
            <div className="filter-heading"><ListFilter size={19} aria-hidden="true" /> <span>할 일 필터</span></div>
            <label><span className="sr-only">분야별 필터</span><select value={category} onChange={(event) => setCategory(event.target.value)}><option value="all">모든 분야</option>{Object.entries(categories).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><ChevronDown size={16} aria-hidden="true" /></label>
            <label><span className="sr-only">상태별 필터</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">모든 상태</option>{statuses.map((item) => <option key={item}>{item}</option>)}</select><ChevronDown size={16} aria-hidden="true" /></label>
            {(quickFilter !== 'all' || category !== 'all' || status !== 'all') && <button className="text-button" type="button" onClick={() => { setQuickFilter('all'); setCategory('all'); setStatus('all'); }}>필터 초기화</button>}
            <button className="refresh-button" type="button" onClick={() => void loadDemo()} disabled={loading || anyBusy} aria-label="할 일 목록 새로고침"><RefreshCw size={19} aria-hidden="true" /></button>
          </div>
          <div className="view-switch" aria-label="업무 보기 방식">
            <button type="button" aria-pressed={!boardView} onClick={() => setBoardView(false)}>목록 보기</button>
            <button type="button" aria-pressed={boardView} onClick={() => setBoardView(true)}>업무 보드</button>
          </div>
          <div className="live-message" aria-live="polite">{notice}</div>
          {loadError && <ErrorMessage>{loadError} {demo && '이전에 불러온 데이터가 남아 있을 수 있습니다.'} <button type="button" className="text-button" onClick={() => void loadDemo()}>다시 불러오기</button></ErrorMessage>}
          {loading && <div className="empty-state" role="status"><LoaderCircle className="spinner" size={25} aria-hidden="true" /><p>시연 데이터를 불러오고 있어요.</p></div>}
          {!loading && demo && filteredTasks.length === 0 && <div className="empty-state"><ClipboardList size={30} aria-hidden="true" /><h3>보여드릴 할 일이 없어요</h3><p>{demo.tasks.length ? '다른 필터를 선택하거나 필터를 초기화해 보세요.' : '시연용 할 일을 하나 추가해 보세요.'}</p></div>}
          {!loading && demo && filteredTasks.length > 0 && (boardView
            ? <div className="board" aria-label="진행 상태별 업무 보드">{statuses.map((stage) => {
              const stageTasks = filteredTasks.filter((task) => task.status === stage);
              return <section className="board-column" key={stage} aria-label={`${stage} ${stageTasks.length}개`}><h3>{stage} <span>{stageTasks.length}</span></h3>{stageTasks.length ? stageTasks.map(renderTask) : <p className="board-empty">할 일이 없어요</p>}</section>;
            })}</div>
            : <div className="task-list"><div className="task-header" aria-hidden="true"><span>할 일</span><span>담당자</span><span>진행 상태</span></div>{filteredTasks.map(renderTask)}</div>)}
        </section>

        <section className="categories-section" aria-labelledby="categories-title">
          <div className="section-heading"><div><h2 id="categories-title">분야별로 보기</h2><p className="section-subtitle">필요한 일을 분야별로 모아 두었어요.</p></div></div>
          {demo && <div className="category-grid">{(Object.keys(categories) as Category[]).map((key) => {
            const categoryTasks = demo.tasks.filter((task) => task.category === key);
            const source = demo.sources.find((item) => sameId(item.id, key));
            const url = source && safeSourceUrl(source);
            return <article className="category-card" key={key}>
              <div className="category-heading"><span className="category-icon" aria-hidden="true">{categoryIcons[key]}</span><h3>{categories[key]}</h3><span>{categoryTasks.length}개</span></div>
              <div className="category-items">{categoryTasks.length ? categoryTasks.slice(0, 3).map((task, index) => <div className="category-item" key={task.task_id}><span className="item-number" aria-hidden="true">{index + 1}</span><div><p className="item-name">{task.title}</p><p className="item-info">{task.assignment_status === 'accepted' ? memberName(demo.members, task.assignee_id) : task.assignment_status === 'pending' ? '담당 수락 대기' : '담당 미배정'} · {task.status}</p></div></div>) : <p className="empty-category">아직 등록한 일이 없어요.</p>}</div>
              <div className="category-source">{source ? <><p>안내 출처: {url ? <a href={url} target="_blank" rel="noopener noreferrer">{source.provider} ↗<span className="sr-only"> (새 창)</span></a> : '확인 필요'}</p><p>확인일: {source.checked_at || '확인 전'} · 시연용 참고</p></> : <p>안내 출처 확인 필요</p>}</div>
              <button className="category-add" type="button" onClick={() => setEditor({ task: null, category: key })}>＋ 이 분야 할 일 추가</button>
              <a className="category-view" href="#tasks" onClick={() => { setCategory(key); setStatus('all'); setQuickFilter('all'); }}>이 분야 전체 보기 <ArrowRight size={16} aria-hidden="true" /></a>
            </article>;
          })}</div>}
        </section>

        <section className="sources-section" id="sources" aria-labelledby="sources-title">
          <div className="section-heading"><div><h2 id="sources-title">확인이 필요한 정보</h2><p className="section-subtitle">실시간 정보가 아닌 시연용 참고 예시입니다.</p></div></div>
          <div className="source-disclaimer"><Info size={20} aria-hidden="true" /><p>복지 자격이나 접종·검진 대상, 의료 상태를 판단하지 않습니다. 실제 신청·예약도 할 수 없어요. 자세한 내용은 공식 기관에 확인해 주세요.</p></div>
          {loading && !demo && <p className="section-subtitle">출처 정보를 불러오는 중이에요.</p>}
          {!loading && !demo && <p className="section-subtitle">출처 정보를 불러오지 못했습니다. 할 일 목록에서 다시 불러와 주세요.</p>}
          {demo && demo.sources.length === 0 && <p className="section-subtitle">표시할 시연 출처가 없습니다.</p>}
          {demo && demo.sources.length > 0 && <div className="source-grid">{demo.sources.map((source) => <SourceCard key={source.id} source={source} />)}</div>}
        </section>

        <PublicDataPanel />

        {integrationError && <button className="text-button" type="button" onClick={() => void loadIntegrations()}>AI 연동 상태 다시 확인</button>}
        <div className="privacy-note"><ShieldCheck size={20} aria-hidden="true" /><p><strong>시연 범위를 기억해 주세요.</strong> 실제 가족 공유를 위한 동의·역할 권한 확인은 제공되지 않으며, 담당 요청이나 응답은 실제 가족에게 전달되지 않습니다.</p></div>
      </main>
      <footer className="footer"><div className="wrap footer-inner"><strong>이음</strong><p>합성 데이터 기반 공개 시연 · 실제 서비스 아님</p></div></footer>
      {editor && demo && <TaskEditor task={editor.task} draft={editor.draft} initialCategory={editor.category} sources={demo.sources} onClose={() => setEditor(null)} onSaved={(task, created) => { replaceTask(task, created); editor.onDraftSaved?.(); setNotice(created ? '시연 할 일을 추가했습니다.' : '시연 할 일을 수정했습니다.'); setEditor(null); }} />}
    </>
  );
}

function PublicAttribution({ source, retrievedAt }: { source: { title: string; url: string }; retrievedAt: string }) {
  const url = safeSourceUrl({ id: 'public', title: source.title, provider: source.title, url: source.url, checked_at: retrievedAt, summary: '' });
  return <p className="public-attribution">출처: {url ? <a href={url} target="_blank" rel="noopener noreferrer">{source.title} ↗</a> : source.title} · 조회: {new Date(retrievedAt).toLocaleString('ko-KR')}</p>;
}

function PublicDataPanel() {
  const [name, setName] = useState('');
  const [hospitals, setHospitals] = useState<PublicResult<Hospital> | null>(null);
  const [specialties, setSpecialties] = useState<PublicResult<Specialty> | null>(null);
  const [selectedHospital, setSelectedHospital] = useState('');
  const [vaccines, setVaccines] = useState<PublicResult<Vaccine> | null>(null);
  const [vaccineDetail, setVaccineDetail] = useState<PublicResult<VaccineDetail> | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const search = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim() || busy) return;
    setBusy('hospitals'); setError(''); setHospitals(null); setSpecialties(null); setSelectedHospital('');
    try { setHospitals(await api.hospitals(name.trim())); }
    catch (err) { setError(err instanceof Error ? err.message : '병원 정보를 조회하지 못했습니다.'); }
    finally { setBusy(''); }
  };
  const showSpecialties = async (hospital: Hospital) => {
    setBusy('specialties'); setError(''); setSpecialties(null); setSelectedHospital(hospital.name);
    try { setSpecialties(await api.specialties(hospital.id)); }
    catch (err) { setError(err instanceof Error ? err.message : '진료과목을 조회하지 못했습니다.'); }
    finally { setBusy(''); }
  };
  const loadVaccines = async () => {
    setBusy('vaccines'); setError(''); setVaccines(null); setVaccineDetail(null);
    try { setVaccines(await api.vaccines()); }
    catch (err) { setError(err instanceof Error ? err.message : '예방접종 정보를 조회하지 못했습니다.'); }
    finally { setBusy(''); }
  };
  const showVaccine = async (code: string) => {
    setBusy('vaccine-detail'); setError(''); setVaccineDetail(null);
    try { setVaccineDetail(await api.vaccineDetail(code)); }
    catch (err) { setError(err instanceof Error ? err.message : '상세 정보를 조회하지 못했습니다.'); }
    finally { setBusy(''); }
  };

  return <section className="public-section" aria-labelledby="public-title">
    <div className="section-heading"><div><h2 id="public-title">공공정보 찾아보기</h2><p className="section-subtitle">공식 API에서 직접 조회한 정보입니다. 실제 이용 가능 여부는 기관에 확인하세요.</p></div></div>
    <p className="public-warning">병원 이름만 검색하세요. 실명, 주소, 증상과 같은 개인정보는 입력하지 마세요. 검색한 병원 이름은 건강보험심사평가원에 전송됩니다.</p>
    {error && <ErrorMessage>{error}</ErrorMessage>}
    <div className="public-grid">
      <article className="public-card">
        <h3>병원과 진료과목</h3>
        <form className="public-search" onSubmit={(event) => void search(event)}>
          <label className="field"><span>병원 이름</span><input value={name} onChange={(event) => setName(event.target.value)} maxLength={100} placeholder="예: 청도" /></label>
          <button type="submit" className="button button-secondary" disabled={!name.trim() || Boolean(busy)}>{busy === 'hospitals' ? '조회 중' : '병원 검색'}</button>
        </form>
        {hospitals && <><PublicAttribution source={hospitals.source} retrievedAt={hospitals.retrieved_at} /><p>최대 10건을 표시합니다.</p>{hospitals.items.length === 0 && <p>검색 결과가 없습니다.</p>}
          <ul className="public-list">{hospitals.items.map((hospital, index) => <li key={`${hospital.id}-${index}`}><strong>{hospital.name || '이름 미제공'}</strong><span>{hospital.type} · {hospital.address || '주소 미제공'}</span><span>{hospital.phone || '전화번호 미제공'}</span><button type="button" className="text-button" disabled={!hospital.id || Boolean(busy)} onClick={() => void showSpecialties(hospital)}>진료과목 보기</button></li>)}</ul></>}
        {busy === 'specialties' && <p role="status">진료과목을 조회 중입니다.</p>}
        {specialties && <div className="public-detail"><strong>{selectedHospital} 진료과목</strong><PublicAttribution source={specialties.source} retrievedAt={specialties.retrieved_at} />{specialties.items.length ? <ul>{specialties.items.map((item, index) => <li key={`${item.name}-${index}`}>{item.name || '과목 미제공'}{item.specialists ? ` · 전문의 ${item.specialists}명` : ''}</li>)}</ul> : <p>제공된 진료과목이 없습니다.</p>}</div>}
      </article>
      <article className="public-card">
        <h3>예방접종 대상 감염병</h3>
        <p>일반 정보이며 개인별 접종 대상이나 의료 판단이 아닙니다.</p>
        <button type="button" className="button button-secondary" disabled={Boolean(busy)} onClick={() => void loadVaccines()}>{busy === 'vaccines' ? '조회 중' : '감염병 목록 조회'}</button>
        {vaccines && <><PublicAttribution source={vaccines.source} retrievedAt={vaccines.retrieved_at} />{vaccines.items.length === 0 && <p>조회 결과가 없습니다.</p>}
          <ul className="public-list">{vaccines.items.map((item, index) => <li key={`${item.code}-${index}`}><button type="button" className="text-button" disabled={!item.code || Boolean(busy)} onClick={() => void showVaccine(item.code)}>{item.name || '명칭 미제공'}</button></li>)}</ul></>}
        {busy === 'vaccine-detail' && <p role="status">상세 정보를 조회 중입니다.</p>}
        {vaccineDetail && <div className="public-detail"><PublicAttribution source={vaccineDetail.source} retrievedAt={vaccineDetail.retrieved_at} />{vaccineDetail.items.length ? vaccineDetail.items.map((item, index) => <div key={index}><strong>{item.title}</strong><p className="public-message">{item.message}</p></div>) : <p>제공된 상세 정보가 없습니다.</p>}</div>}
      </article>
      <article className="public-card">
        <h3>노인복지시설</h3>
        <p>국토교통부 공간정보 API의 상세 호출 조건을 확인할 수 없어 아직 연결하지 않았습니다.</p>
        <a href="https://www.data.go.kr/data/15056929/openapi.do" target="_blank" rel="noopener noreferrer">공식 안내 보기 ↗</a>
      </article>
    </div>
  </section>;
}

function DraftPanel({ integration, loading, error, onReview }: { integration?: Integrations['agent']; loading: boolean; error: string; onReview: (draft: Draft, onSaved: () => void) => void }) {
  const [category, setCategory] = useState<Category>('benefit');
  const [acknowledged, setAcknowledged] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<DraftResponse | null>(null);
  const [requestError, setRequestError] = useState('');

  const generate = async () => {
    setGenerating(true);
    setRequestError('');
    setResult(null);
    try {
      setResult(await api.draft(category));
    } catch (err) {
      setRequestError(err instanceof Error ? err.message : '초안을 만들지 못했습니다.');
    } finally {
      setGenerating(false);
    }
  };
  const url = result && safeSourceUrl(result.source);
  return <section className="draft-panel" aria-labelledby="draft-title">
    <div className="section-heading"><div><h2 id="draft-title"><Sparkles size={22} aria-hidden="true" /> AI로 확인할 일 찾기</h2><p className="section-subtitle">Microsoft Agent Framework와 GitHub Copilot으로 가상 업무 초안을 제안합니다.</p></div></div>
    <p>선택한 가상 분야만 Copilot에 전송합니다. 실제 이름, 건강정보 등은 입력하지 않습니다. 초안은 확인 후 직접 저장해야 합니다. 공개 시연은 전체 사용자 합산 하루 10회로 제한합니다.</p>
    {loading && <p role="status">AI 연동 상태를 확인 중입니다.</p>}
    {error && <ErrorMessage>{error}</ErrorMessage>}
    {!loading && integration && !integration.available && <p className="draft-disabled">현재 사용 불가: {integration.reason}</p>}
    <div className="draft-controls">
      <label className="field"><span>가상 분야</span><select value={category} disabled={generating} onChange={(event) => setCategory(event.target.value as Category)}>{Object.entries(categories).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label className="draft-consent"><input type="checkbox" checked={acknowledged} disabled={generating} onChange={(event) => setAcknowledged(event.target.checked)} /> 가상 분야를 Copilot에 보내 초안을 만드는 데 동의합니다.</label>
      <button className="button button-primary" type="button" disabled={!integration?.available || !acknowledged || generating} onClick={() => void generate()}>{generating ? <><LoaderCircle size={18} className="spinner" aria-hidden="true" /> 초안 만드는 중</> : <><Sparkles size={18} aria-hidden="true" /> AI 초안 만들기</>}</button>
    </div>
    {requestError && <ErrorMessage>{requestError}</ErrorMessage>}
    {result && <div className="draft-results" aria-live="polite">
      <p><strong>참고 홈페이지:</strong> {url ? <a href={url} target="_blank" rel="noopener noreferrer">{result.source.provider} · {result.source.title} ↗</a> : '출처 확인 필요'} · 확인일 {result.source.checked_at ?? '미확인'}</p>
      <p>{result.source.summary} 일반 홈페이지는 구체적인 제도 내용의 근거가 아닙니다. 실제 내용은 기관에 확인하세요.</p>
      {result.drafts.length === 0 && <p>모든 초안을 검토했습니다.</p>}
      {result.drafts.map((draft, index) => <article className="draft-item" key={`${index}-${draft.title}`}><div><h3>{draft.title}</h3><p>{draft.description}</p><p><strong>확인 필요:</strong> {draft.uncertainty}</p></div><div className="draft-actions"><button type="button" className="button button-secondary" onClick={() => onReview(draft, () => setResult((current) => current && ({ ...current, drafts: current.drafts.filter((_, itemIndex) => itemIndex !== index) })))}>검토·수정</button><button type="button" className="text-button" onClick={() => setResult((current) => current && ({ ...current, drafts: current.drafts.filter((_, itemIndex) => itemIndex !== index) }))}>거절</button></div></article>)}
    </div>}
  </section>;
}

function ActivityHistory({ task }: { task: Task }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true);
    setError('');
    api.activity(task.task_id).then((value) => { if (active) setItems(value); })
      .catch((err: unknown) => { if (active) setError(err instanceof Error ? err.message : '이력을 불러오지 못했습니다.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, task, retry]);

  return <details className="activity-history" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>변경 이력 보기</summary>
    {loading && <p role="status">이력을 불러오는 중입니다.</p>}
    {error && <><ErrorMessage>{error}</ErrorMessage><button className="text-button" type="button" onClick={() => setRetry((value) => value + 1)}>다시 불러오기</button></>}
    {!loading && !error && (items.length ? <ol>{items.map((item) => <li key={item.event_id}><span>{item.detail}</span><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString('ko-KR')}</time></li>)}</ol> : <p>기록된 이력이 없습니다. 기존 시연 데이터는 변경 시점부터 기록됩니다.</p>)}
  </details>;
}

function TaskCard({ index, task, members, sources, busy, error, onEdit, onChangeStatus, onRequest, onResponse }: { index: number; task: Task; members: Member[]; sources: Source[]; busy: boolean; error?: string; onEdit: () => void; onChangeStatus: (status: TaskStatus) => void; onRequest: (member: Id) => void; onResponse: (member: Id, decision: 'accept' | 'reject' | 'adjust') => void }) {
  const [selectedMember, setSelectedMember] = useState('');
  const member = members.find((item) => String(item.id) === selectedMember);
  const source = sources.find((item) => sameId(item.id, task.source_id));
  const days = daysUntil(task.due_date);
  const dueClass = isOpen(task) && days !== null && days < 0 ? 'due-overdue' : isOpen(task) && days !== null && days <= 7 ? 'due-soon' : '';
  return (
    <article className="task-card">
      <div className="task-row">
        <div className="task-title"><span className="task-number" aria-hidden="true">{index}</span><div><h3>{task.title}</h3><p className="task-meta">{categories[task.category]} · <span className={dueClass}>{dueLabel(task.due_date)}</span></p></div></div>
        <div className="assignee"><span className="mobile-label">담당자 </span>{task.assignment_status === 'accepted' ? `${memberName(members, task.assignee_id)} · 수락됨` : task.assignment_status === 'pending' ? `${memberName(members, task.requested_assignee_id)} · 수락 대기` : '담당 미배정'}</div>
        <label className="status-control"><span className="sr-only">{task.title} 진행 상태</span><select data-status={task.status} value={task.status} disabled={busy || task.assignment_status === 'pending'} onChange={(event) => onChangeStatus(event.target.value as TaskStatus)}>{statuses.filter((item) => item !== '담당 요청' || task.status === '담당 요청').map((item) => <option key={item}>{item}</option>)}</select><ChevronDown size={17} aria-hidden="true" /></label>
      </div>
      <details className="task-details">
        <summary>상세 내용과 담당 요청</summary>
        <div className="task-detail-content">
          <p className="task-description">{task.description}</p>
          {source && <a className="task-source" href="#sources"><ExternalLink size={16} aria-hidden="true" /> 참고 출처: {source.title}</a>}
          <button type="button" className="edit-button" disabled={busy} onClick={onEdit}><Pencil size={16} aria-hidden="true" /> 할 일 수정</button>
          {busy && <span className="saving"><LoaderCircle size={16} className="spinner" aria-hidden="true" /> 처리 중</span>}
          {task.assignment_status === 'pending' && task.requested_assignee_id !== null ? (
            <div className="assignment-box">
              <div><strong>{memberName(members, task.requested_assignee_id)}에게 시연 요청 중</strong><p>아직 담당이 확정되지 않았어요. 가상 가족으로 응답해 보세요.</p></div>
              <div className="response-buttons"><button type="button" disabled={busy} onClick={() => onResponse(task.requested_assignee_id!, 'accept')}><Check size={16} aria-hidden="true" /> 수락</button><button type="button" disabled={busy} onClick={() => onResponse(task.requested_assignee_id!, 'reject')}>거절</button><button type="button" disabled={busy} onClick={() => onResponse(task.requested_assignee_id!, 'adjust')}>조정</button></div>
            </div>
          ) : isOpen(task) ? (
            <div className="assignment-box">
              <div><strong>{task.assignment_status === 'accepted' ? '담당 요청 변경' : '누가 함께할까요?'}</strong><p>{task.assignment_status === 'accepted' ? '변경 요청 시 기존 담당이 해제되고 새 수락 전까지 미배정이에요.' : '요청은 수락 전까지 미배정이며, 실제 알림은 없어요.'}</p></div>
              <div className="request-controls"><label><span className="sr-only">{task.title}의 가상 가족 선택</span><select value={selectedMember} disabled={busy || members.length === 0} onChange={(event) => setSelectedMember(event.target.value)}><option value="">가상 가족 선택</option>{members.map((item) => <option key={item.id} value={String(item.id)}>{item.name}</option>)}</select></label><button type="button" disabled={busy || !member} onClick={() => { if (member) onRequest(member.id); }}>시연 요청 <ArrowRight size={16} aria-hidden="true" /></button></div>
            </div>
          ) : <p className="closed-task-note">완료 또는 해당 없음 상태에서는 담당을 요청할 수 없어요.</p>}
          <ActivityHistory task={task} />
        </div>
      </details>
      {error && <div className="task-error"><ErrorMessage>{error}</ErrorMessage></div>}
    </article>
  );
}

function SourceCard({ source }: { source: Source }) {
  const url = safeSourceUrl(source);
  return <article className="source-card"><div className="source-top"><span className="source-icon"><ClipboardList size={18} aria-hidden="true" /></span><span className="source-sample">참고 예시</span></div><h3>{source.title}</h3><p>{source.summary}</p><div className="source-details"><span>{source.provider || '제공기관 미확인'}</span><span>확인일 {source.checked_at || '미확인'}</span></div>{url ? <a href={url} target="_blank" rel="noopener noreferrer">기관 원문 보기 <ArrowUpRight size={15} aria-hidden="true" /><span className="sr-only"> (새 창)</span></a> : <span className="source-unavailable">출처 또는 확인일을 확인할 수 없어요</span>}</article>;
}

function TaskEditor({ task, draft, initialCategory, sources, onClose, onSaved }: { task: Task | null; draft?: Draft; initialCategory?: Category; sources: Source[]; onClose: () => void; onSaved: (task: Task, created: boolean) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [title, setTitle] = useState(task?.title ?? draft?.title ?? '');
  const [description, setDescription] = useState(task?.description ?? (draft ? `${draft.description}\n\n확인 필요: ${draft.uncertainty}` : ''));
  const [category, setCategory] = useState<Category>(task?.category ?? draft?.category ?? initialCategory ?? 'benefit');
  const [dueDate, setDueDate] = useState(task?.due_date ?? '');
  const [sourceId, setSourceId] = useState(task?.source_id != null ? String(task.source_id) : draft ? String(draft.source_id) : '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { dialog.current?.showModal(); }, []);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving || !title.trim() || !description.trim()) return;
    setSaving(true);
    setError('');
    const source = sources.find((item) => String(item.id) === sourceId);
    const input: TaskInput = { title: title.trim(), description: description.trim(), category, due_date: dueDate || null, source_id: source?.id ?? null };
    try {
      const result = task ? await api.updateTask(task.task_id, input) : await api.createTask(input);
      onSaved(result, !task);
    } catch (err) {
      setError(`${err instanceof Error ? err.message : '저장하지 못했습니다.'} 저장 여부가 불확실할 수 있습니다. 목록을 새로고침해 확인한 후 다시 시도해 주세요.`);
    } finally {
      setSaving(false);
    }
  };

  return <dialog className="editor-dialog" ref={dialog} onClose={onClose} onCancel={(event) => { if (saving) event.preventDefault(); }} aria-labelledby="editor-title">
    <div className="dialog-heading"><h2 id="editor-title">{task ? '시연 할 일 수정' : draft ? 'AI 초안 검토 및 수정' : '새 할 일 추가'}</h2><button className="icon-button" type="button" disabled={saving} onClick={() => dialog.current?.close()} aria-label="닫기"><X size={20} aria-hidden="true" /></button></div>
    <p className="editor-intro">가상의 확인 업무만 적어 주세요. 실제 예약이나 신청은 되지 않습니다.</p>
    {draft && <p className="editor-intro"><strong>AI 초안은 아직 저장되지 않았습니다.</strong> 내용을 확인·수정한 뒤 저장해 주세요. {draft.uncertainty}</p>}
    <div className="editor-warning"><ShieldCheck size={17} aria-hidden="true" /> 실명·연락처·건강·소득 등 실제 개인정보는 입력하지 마세요.</div>
    <form onSubmit={(event) => void submit(event)}>
      <label className="field"><span>할 일 제목 <b>*</b></span><input autoFocus required maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="예: 지역 프로그램 안내 확인하기" /></label>
      <label className="field"><span>간단한 설명 <b>*</b></span><textarea required rows={3} maxLength={2000} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="가상의 확인할 내용을 적어 주세요." /></label>
      <div className="field-row"><label className="field"><span>분야 <b>*</b></span><select value={category} onChange={(event) => setCategory(event.target.value as Category)}>{Object.entries(categories).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="field"><span>확인 기한 <small>선택</small></span><input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></label></div>
      <label className="field"><span>참고 출처 <small>선택</small></span><select value={sourceId} onChange={(event) => setSourceId(event.target.value)}><option value="">출처 선택 안 함</option>{sources.map((source) => <option key={source.id} value={String(source.id)}>{source.title}</option>)}</select></label>
      {error && <ErrorMessage>{error}</ErrorMessage>}
      <div className="dialog-actions"><button type="button" className="button button-secondary" disabled={saving} onClick={() => dialog.current?.close()}>취소</button><button type="submit" className="button button-primary" disabled={saving || !title.trim() || !description.trim()}>{saving ? <><LoaderCircle size={16} className="spinner" aria-hidden="true" /> 저장 중</> : <><CheckCircle2 size={17} aria-hidden="true" /> 시연 할 일 저장</>}</button></div>
    </form>
  </dialog>;
}

export default App;
