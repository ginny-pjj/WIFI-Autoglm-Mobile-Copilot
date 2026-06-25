import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

type TaskMode = 'mock' | 'real';
type TaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled';
type TraceKind = 'observe' | 'think' | 'act' | 'result' | 'system';
type TabKey = 'console' | 'trace' | 'history';
type UiMode = 'user' | 'debug';

interface DeviceInfo {
  id?: string;
  serial?: string;
  state?: string;
  status?: string;
  model?: string;
}

interface TraceStep {
  kind: TraceKind | string;
  message: string;
}

interface StructuredStep {
  step_id: number;
  kind: TraceKind | string;
  title: string;
  message: string;
}

interface TaskRecord {
  task_id: string;
  task: string;
  mode: TaskMode;
  status: TaskStatus;
  logs: string[];
  trace?: TraceStep[];
  steps?: StructuredStep[];
  error?: string;
  created_at?: string;
  duration_ms?: number | null;
}

interface SkillTemplate {
  name: string;
  task: string;
  category: string;
}

const DEFAULT_BASE = 'http://127.0.0.1:8000';

const TRACE_COLORS: Record<string, string> = {
  observe: '#38bdf8',
  think: '#a78bfa',
  act: '#fbbf24',
  result: '#4ade80',
  system: '#94a3b8',
};

function normalizeBaseUrl(url: string): string {
  return url.trim().replace(/\/+$/, '');
}

function traceLabel(kind: string): string {
  switch (kind) {
    case 'observe':
      return 'OBSERVE';
    case 'think':
      return 'THINK';
    case 'act':
      return 'ACTION';
    case 'result':
      return 'RESULT';
    default:
      return 'SYSTEM';
  }
}

function formatDuration(ms?: number | null): string {
  if (!ms || ms <= 0) return '';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function statusText(status: TaskStatus | 'idle'): string {
  switch (status) {
    case 'running':
      return '执行中';
    case 'success':
      return '已完成';
    case 'failed':
      return '失败';
    case 'cancelled':
      return '已停止';
    case 'pending':
      return '排队中';
    default:
      return '待执行';
  }
}

export default function App() {
  const [uiMode, setUiMode] = useState<UiMode>('user');
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE);
  const [taskText, setTaskText] = useState('打开美团搜索蜜雪冰城');
  const [mode, setMode] = useState<TaskMode>('real');
  const [connected, setConnected] = useState(false);
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [steps, setSteps] = useState<StructuredStep[]>([]);
  const [durationMs, setDurationMs] = useState<number | null>(null);
  const [history, setHistory] = useState<TaskRecord[]>([]);
  const [templates, setTemplates] = useState<SkillTemplate[]>([]);
  const [supportedApps, setSupportedApps] = useState<string[]>([]);
  const [taskStatus, setTaskStatus] = useState<TaskStatus | 'idle'>('idle');
  const [connecting, setConnecting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKey>('console');
  const [prepareHome, setPrepareHome] = useState(true);
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const currentTaskIdRef = useRef<string | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const requestJson = useCallback(
    async <T,>(path: string, options?: RequestInit): Promise<T> => {
      const response = await fetch(`${normalizeBaseUrl(baseUrl)}${path}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json; charset=utf-8',
          ...(options?.headers ?? {}),
        },
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
      }
      return response.json() as Promise<T>;
    },
    [baseUrl],
  );

  const loadSkills = useCallback(async () => {
    try {
      const data = await requestJson<{
        templates: SkillTemplate[];
        supported_apps: string[];
      }>('/skills');
      setTemplates(data.templates ?? []);
      setSupportedApps(data.supported_apps ?? []);
    } catch {
      setTemplates([
        { name: '查看 WLAN', task: '打开设置查看WLAN', category: 'system' },
        { name: '美团搜索', task: '打开美团搜索蜜雪冰城', category: 'life' },
      ]);
    }
  }, [requestJson]);

  const loadHistory = useCallback(async () => {
    try {
      const data = await requestJson<TaskRecord[]>('/tasks');
      setHistory(data.slice(0, 10));
    } catch {
      // ignore
    }
  }, [requestJson]);

  const testConnection = useCallback(async () => {
    setConnecting(true);
    try {
      const health = await requestJson<{ status: string; api_key_configured?: boolean }>(
        '/health',
      );
      const deviceResp = await requestJson<{ devices: DeviceInfo[] }>('/devices');
      setConnected(health.status === 'ok');
      setDevices(deviceResp.devices ?? []);
      setLogs([
        `[连接成功] 后端状态: ${health.status}`,
        `[模型配置] API Key ${health.api_key_configured ? '已配置' : '未配置'}`,
        `[设备] 已连接 ${deviceResp.devices?.length ?? 0} 台`,
      ]);
      await loadSkills();
      await loadHistory();
    } catch (error) {
      setConnected(false);
      setDevices([]);
      if (uiMode === 'debug') {
        Alert.alert('连接失败', String(error));
      }
    } finally {
      setConnecting(false);
    }
  }, [loadHistory, loadSkills, requestJson, uiMode]);

  useEffect(() => {
    void testConnection();
    // only auto-connect once on launch
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pollTask = useCallback(
    (taskId: string) => {
      stopPolling();
      pollRef.current = setInterval(async () => {
        try {
          const task = await requestJson<TaskRecord>(`/tasks/${taskId}`);
          setLogs(task.logs ?? []);
          setTrace(task.trace ?? []);
          setSteps(task.steps ?? []);
          setDurationMs(task.duration_ms ?? null);
          setTaskStatus(task.status);
          if (task.status === 'success' || task.status === 'failed' || task.status === 'cancelled') {
            stopPolling();
            setSubmitting(false);
            setStopping(false);
            currentTaskIdRef.current = null;
            setCurrentTaskId(null);
            await loadHistory();
            if (task.error) {
              setLogs((prev) => [...prev, `[错误] ${task.error}`]);
            }
          }
        } catch (error) {
          stopPolling();
          setSubmitting(false);
          setStopping(false);
          setLogs((prev) => [...prev, `[轮询失败] ${String(error)}`]);
        }
      }, 1000);
    },
    [loadHistory, requestJson, stopPolling],
  );

  const runTask = useCallback(async () => {
    if (!taskText.trim()) {
      Alert.alert('提示', '请输入任务内容');
      return;
    }
    stopPolling();
    setSubmitting(false);
    setStopping(false);
    currentTaskIdRef.current = null;
    setCurrentTaskId(null);
    if (!connected) {
      await testConnection();
    }
    setSubmitting(true);
    setTaskStatus('running');
    setLogs([`[提交任务] ${taskText.trim()} (${mode})`]);
    setTrace([]);
    setSteps([]);
    setDurationMs(null);
    if (uiMode === 'debug') {
      setActiveTab('trace');
    }
    try {
      const created = await requestJson<{ task_id: string; status: TaskStatus }>('/tasks', {
        method: 'POST',
        body: JSON.stringify({
          task: taskText.trim(),
          mode,
          prepare_home: prepareHome,
        }),
      });
      setLogs((prev) => [...prev, `[任务ID] ${created.task_id}`]);
      currentTaskIdRef.current = created.task_id;
      setCurrentTaskId(created.task_id);
      setSubmitting(false);
      pollTask(created.task_id);
    } catch (error) {
      setSubmitting(false);
      setTaskStatus('failed');
      Alert.alert('任务提交失败', String(error));
    }
  }, [connected, mode, pollTask, prepareHome, requestJson, stopPolling, taskText, testConnection, uiMode]);

  const stopTask = useCallback(async () => {
    const taskId = currentTaskIdRef.current ?? currentTaskId;
    if (!taskId) {
      setTaskStatus('idle');
      setSubmitting(false);
      setStopping(false);
      currentTaskIdRef.current = null;
      setCurrentTaskId(null);
      Alert.alert('提示', '当前没有可停止的任务');
      return;
    }
    setStopping(true);
    try {
      const task = await requestJson<TaskRecord>(`/tasks/${taskId}/cancel`, {
        method: 'POST',
      });
      setLogs(task.logs ?? []);
      setTrace(task.trace ?? []);
      setSteps(task.steps ?? []);
      setDurationMs(task.duration_ms ?? null);
      setTaskStatus(task.status);
      stopPolling();
      setSubmitting(false);
      setStopping(false);
      currentTaskIdRef.current = null;
      setCurrentTaskId(null);
      await loadHistory();
    } catch (error) {
      stopPolling();
      setSubmitting(false);
      setStopping(false);
      currentTaskIdRef.current = null;
      setCurrentTaskId(null);
      setTaskStatus('idle');
      Alert.alert('停止失败', String(error));
    }
  }, [currentTaskId, loadHistory, requestJson, stopPolling]);

  const isTerminalStatus =
    taskStatus === 'success' || taskStatus === 'failed' || taskStatus === 'cancelled';

  const isTaskActive =
    stopping ||
    submitting ||
    (!isTerminalStatus && (taskStatus === 'running' || taskStatus === 'pending'));

  const statusColor =
    taskStatus === 'success'
      ? '#16a34a'
      : taskStatus === 'failed'
        ? '#dc2626'
        : taskStatus === 'cancelled'
          ? '#ea580c'
          : taskStatus === 'running'
            ? '#2563eb'
            : '#6b7280';

  const progressPercent =
    taskStatus === 'success' || taskStatus === 'failed' || taskStatus === 'cancelled'
      ? 100
      : taskStatus === 'running'
        ? Math.min(90, Math.max(12, steps.length * 18))
        : 0;

  const resultMessage =
    steps.filter((s) => s.kind === 'result').pop()?.message ||
    (taskStatus === 'success'
      ? '任务执行完成'
      : taskStatus === 'failed'
        ? '任务执行失败'
        : taskStatus === 'cancelled'
          ? '任务已手动停止'
          : '');

  const renderActionButtons = () => (
    <View style={styles.actionRow}>
      <Pressable
        style={[styles.buttonPrimary, styles.actionButton, isTaskActive && styles.buttonHalf]}
        onPress={runTask}
        disabled={isTaskActive || connecting || submitting || stopping}
      >
        {submitting ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.buttonText}>开始执行</Text>
        )}
      </Pressable>
      {isTaskActive && (
        <Pressable
          style={[styles.buttonDanger, styles.actionButton, styles.buttonHalf]}
          onPress={stopTask}
          disabled={stopping}
        >
          {stopping ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>停止任务</Text>
          )}
        </Pressable>
      )}
    </View>
  );

  const renderStopBanner = () => {
    if (!isTaskActive) {
      return null;
    }
    return (
      <Pressable style={styles.stopBanner} onPress={stopTask} disabled={stopping}>
        <Text style={styles.stopBannerText}>
          {stopping ? '正在停止…' : '⏹ 停止当前任务'}
        </Text>
      </Pressable>
    );
  };

  const renderStructuredSteps = (items: StructuredStep[]) => {
    if (items.length === 0) {
      return (
        <Text style={styles.logPlaceholder}>
          {taskStatus === 'running' ? 'Agent 正在思考与执行…' : '执行任务后，这里会显示结构化决策链路'}
        </Text>
      );
    }
    return items.map((step) => (
      <View key={`step-${step.step_id}`} style={styles.stepCard}>
        <View style={styles.stepHeader}>
          <Text style={[styles.stepBadge, { color: TRACE_COLORS[step.kind] ?? TRACE_COLORS.system }]}>
            {traceLabel(step.kind)}
          </Text>
          <Text style={styles.stepTitle}>{step.title}</Text>
        </View>
        <Text style={styles.stepMessage}>{step.message}</Text>
      </View>
    ));
  };

  const renderUserMode = () => (
    <>
      <View style={styles.heroCard}>
        <Text style={styles.heroTitle}>Mobile AI Agent</Text>
        <Text style={styles.heroSubtitle}>Open-AutoGLM + ADB + VLM · 可追踪决策链路</Text>
        <Text style={styles.heroMeta}>
          {connected ? `已连接 · ${devices.length} 台设备就绪` : '正在连接后端…'}
        </Text>
      </View>

      <Text style={styles.label}>你想让手机做什么？</Text>
      <TextInput
        style={[styles.input, styles.taskInput]}
        value={taskText}
        onChangeText={setTaskText}
        multiline
        placeholder="例如：打开美团搜索蜜雪冰城"
      />

      <Text style={styles.label}>快捷任务</Text>
      <View style={styles.templateRow}>
        {templates.slice(0, 4).map((tpl) => (
          <Pressable key={tpl.task} style={styles.templateChip} onPress={() => setTaskText(tpl.task)}>
            <Text style={styles.templateName}>{tpl.name}</Text>
          </Pressable>
        ))}
      </View>

      {renderActionButtons()}
      {renderStopBanner()}

      <View style={styles.card}>
        <View style={styles.progressHeader}>
          <Text style={styles.cardTitle}>执行进度</Text>
          <Text style={{ color: statusColor, fontWeight: '600' }}>{statusText(taskStatus)}</Text>
        </View>
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${progressPercent}%`, backgroundColor: statusColor }]} />
        </View>
        {durationMs ? (
          <Text style={styles.perfText}>
            总耗时 {formatDuration(durationMs)}（含模型推理 + ADB 执行）
          </Text>
        ) : taskStatus === 'running' ? (
          <Text style={styles.perfText}>REAL 模式单步约 5–15s，完整任务通常 30s–2min</Text>
        ) : null}
      </View>

      {(taskStatus === 'success' || taskStatus === 'failed' || taskStatus === 'cancelled') && (
        <View
          style={[
            styles.card,
            taskStatus === 'success' ? styles.resultCard : styles.resultCardMuted,
          ]}
        >
          <Text style={styles.cardTitle}>执行结果</Text>
          <Text style={[styles.resultText, { color: statusColor }]}>{resultMessage || statusText(taskStatus)}</Text>
        </View>
      )}

      <Text style={styles.label}>Agent 决策链路</Text>
      <View style={styles.traceBox}>{renderStructuredSteps(steps)}</View>

      {history.length > 0 && (
        <>
          <Text style={styles.label}>最近任务</Text>
          {history.slice(0, 3).map((item) => (
            <Pressable
              key={item.task_id}
              style={styles.historyItem}
              onPress={() => {
                setTaskText(item.task);
                setMode(item.mode);
              }}
            >
              <Text style={styles.historyTask}>{item.task}</Text>
              <Text style={styles.historyMeta}>
                {statusText(item.status)} · {formatDuration(item.duration_ms) || item.created_at || item.task_id}
              </Text>
            </Pressable>
          ))}
        </>
      )}
    </>
  );

  const renderDebugMode = () => (
    <>
      <View style={styles.tabRow}>
        {([
          ['console', '控制台'],
          ['trace', 'Agent Trace'],
          ['history', '历史'],
        ] as const).map(([key, label]) => (
          <Pressable
            key={key}
            style={[styles.tabChip, activeTab === key && styles.tabChipActive]}
            onPress={() => setActiveTab(key)}
          >
            <Text style={[styles.tabText, activeTab === key && styles.tabTextActive]}>{label}</Text>
          </Pressable>
        ))}
      </View>

      {activeTab === 'console' && (
        <>
          <Text style={styles.label}>后端地址</Text>
          <TextInput
            style={styles.input}
            value={baseUrl}
            onChangeText={setBaseUrl}
            autoCapitalize="none"
            autoCorrect={false}
            placeholder="http://127.0.0.1:8000"
          />
          <Pressable style={styles.buttonSecondary} onPress={testConnection} disabled={connecting || isTaskActive}>
            <Text style={styles.buttonText}>连接测试</Text>
          </Pressable>

          <View style={styles.card}>
            <Text style={styles.cardTitle}>设备状态</Text>
            <Text style={styles.cardText}>
              连接: {connected ? '✅ 已连接' : '❌ 未连接'} · 设备数: {devices.length}
            </Text>
            {supportedApps.length > 0 && (
              <Text style={styles.cardText}>支持 App: {supportedApps.length} 个</Text>
            )}
          </View>

          <Text style={styles.label}>任务输入</Text>
          <TextInput
            style={[styles.input, styles.taskInput]}
            value={taskText}
            onChangeText={setTaskText}
            multiline
            placeholder="例如：打开美团搜索蜜雪冰城"
          />

          <Text style={styles.label}>执行模式</Text>
          <View style={styles.modeRow}>
            {(['mock', 'real'] as TaskMode[]).map((item) => (
              <Pressable
                key={item}
                style={[styles.modeChip, mode === item && styles.modeChipActive]}
                onPress={() => setMode(item)}
              >
                <Text style={[styles.modeText, mode === item && styles.modeTextActive]}>
                  {item.toUpperCase()}
                </Text>
              </Pressable>
            ))}
          </View>

          <Pressable
            style={[styles.prepareRow, prepareHome && styles.prepareRowActive]}
            onPress={() => setPrepareHome((v) => !v)}
          >
            <Text style={styles.prepareText}>
              {prepareHome ? '✅' : '⬜'} 执行前自动回桌面（提高成功率）
            </Text>
          </Pressable>

          <Text style={styles.label}>技能中心</Text>
          <View style={styles.templateRow}>
            {templates.map((tpl) => (
              <Pressable key={tpl.task} style={styles.templateChip} onPress={() => setTaskText(tpl.task)}>
                <Text style={styles.templateName}>{tpl.name}</Text>
                <Text style={styles.templateText}>{tpl.task}</Text>
              </Pressable>
            ))}
          </View>

          {renderActionButtons()}
          {renderStopBanner()}

          <View style={styles.card}>
            <Text style={styles.cardTitle}>
              任务状态: <Text style={{ color: statusColor }}>{taskStatus}</Text>
              {durationMs ? ` · ${formatDuration(durationMs)}` : ''}
            </Text>
          </View>

          <Text style={styles.label}>原始日志</Text>
          <View style={styles.logBox}>
            {logs.length === 0 ? (
              <Text style={styles.logPlaceholder}>暂无日志</Text>
            ) : (
              logs.map((line, index) => (
                <Text key={`${index}-${line.slice(0, 20)}`} style={styles.logLine}>
                  {line}
                </Text>
              ))
            )}
          </View>
        </>
      )}

      {activeTab === 'trace' && (
        <>
          <Text style={styles.label}>结构化 Trace（产品视图）</Text>
          <View style={styles.traceBox}>{renderStructuredSteps(steps)}</View>

          <Text style={styles.label}>原始 Trace（调试）</Text>
          <View style={styles.traceBox}>
            {trace.length === 0 ? (
              <Text style={styles.logPlaceholder}>暂无原始 trace</Text>
            ) : (
              trace.map((step, index) => (
                <View key={`${index}-${step.message.slice(0, 16)}`} style={styles.traceItem}>
                  <Text
                    style={[
                      styles.traceBadge,
                      { color: TRACE_COLORS[step.kind] ?? TRACE_COLORS.system },
                    ]}
                  >
                    {traceLabel(step.kind)}
                  </Text>
                  <Text style={styles.traceMessage}>{step.message}</Text>
                </View>
              ))
            )}
          </View>
        </>
      )}

      {activeTab === 'history' && (
        <>
          <Text style={styles.label}>任务记忆（Memory）</Text>
          {history.length === 0 ? (
            <Text style={styles.logPlaceholder}>暂无历史任务</Text>
          ) : (
            history.map((item) => (
              <Pressable
                key={item.task_id}
                style={styles.historyItem}
                onPress={() => {
                  setTaskText(item.task);
                  setMode(item.mode);
                  setActiveTab('console');
                }}
              >
                <Text style={styles.historyTask}>{item.task}</Text>
                <Text style={styles.historyMeta}>
                  {item.mode.toUpperCase()} · {item.status} ·{' '}
                  {formatDuration(item.duration_ms) || item.created_at || item.task_id}
                </Text>
              </Pressable>
            ))
          )}
        </>
      )}
    </>
  );

  return (
    <View style={styles.root}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>AutoGLM Mobile Copilot</Text>
        <Text style={styles.subtitle}>
          {uiMode === 'user' ? '手机 AI Agent 助手' : 'Phone Agent 控制台 · Debug'}
        </Text>

        <View style={styles.modeRow}>
          {([
            ['user', '👤 用户模式'],
            ['debug', '🧪 调试模式'],
          ] as const).map(([key, label]) => (
            <Pressable
              key={key}
              style={[styles.uiModeChip, uiMode === key && styles.uiModeChipActive]}
              onPress={() => setUiMode(key)}
            >
              <Text style={[styles.uiModeText, uiMode === key && styles.uiModeTextActive]}>{label}</Text>
            </Pressable>
          ))}
        </View>

        {uiMode === 'user' ? renderUserMode() : renderDebugMode()}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0f172a' },
  container: { paddingTop: 56, paddingHorizontal: 16, paddingBottom: 32 },
  title: { fontSize: 24, fontWeight: '700', color: '#f8fafc' },
  subtitle: { marginTop: 4, marginBottom: 16, color: '#94a3b8', fontSize: 13 },
  tabRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  tabChip: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 10,
    backgroundColor: '#1e293b',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#334155',
  },
  tabChipActive: { backgroundColor: '#1d4ed8', borderColor: '#3b82f6' },
  tabText: { color: '#94a3b8', fontWeight: '600', fontSize: 13 },
  tabTextActive: { color: '#fff' },
  uiModeChip: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 10,
    backgroundColor: '#1e293b',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#334155',
    marginBottom: 8,
  },
  uiModeChipActive: { backgroundColor: '#0f766e', borderColor: '#14b8a6' },
  uiModeText: { color: '#94a3b8', fontWeight: '600', fontSize: 13 },
  uiModeTextActive: { color: '#fff' },
  heroCard: {
    backgroundColor: '#172554',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: '#1d4ed8',
    marginBottom: 8,
  },
  heroTitle: { color: '#f8fafc', fontSize: 20, fontWeight: '700' },
  heroSubtitle: { color: '#93c5fd', marginTop: 6, fontSize: 13, lineHeight: 18 },
  heroMeta: { color: '#64748b', marginTop: 8, fontSize: 12 },
  label: { color: '#cbd5e1', marginBottom: 8, marginTop: 12, fontSize: 14, fontWeight: '600' },
  input: {
    backgroundColor: '#1e293b',
    color: '#f8fafc',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: '#334155',
  },
  taskInput: { minHeight: 80, textAlignVertical: 'top' },
  buttonPrimary: {
    marginTop: 16,
    backgroundColor: '#2563eb',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
  },
  buttonDanger: {
    marginTop: 16,
    backgroundColor: '#dc2626',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
  },
  actionButton: {
    flex: 1,
  },
  buttonHalf: {
    marginTop: 16,
  },
  stopBanner: {
    marginTop: 10,
    backgroundColor: '#7f1d1d',
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#dc2626',
  },
  stopBannerText: { color: '#fecaca', fontWeight: '700', fontSize: 15 },
  buttonSecondary: {
    marginTop: 10,
    backgroundColor: '#334155',
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
  },
  buttonText: { color: '#fff', fontWeight: '600', fontSize: 15 },
  card: {
    marginTop: 14,
    backgroundColor: '#1e293b',
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: '#334155',
  },
  resultCard: { borderColor: '#166534', backgroundColor: '#052e16' },
  resultCardMuted: { borderColor: '#334155', backgroundColor: '#1e293b' },
  cardTitle: { color: '#e2e8f0', fontWeight: '600', marginBottom: 4 },
  cardText: { color: '#94a3b8', fontSize: 13 },
  resultText: { fontSize: 14, lineHeight: 20, marginTop: 4 },
  progressHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  progressTrack: {
    height: 8,
    backgroundColor: '#0f172a',
    borderRadius: 999,
    overflow: 'hidden',
    marginTop: 10,
  },
  progressFill: { height: 8, borderRadius: 999 },
  perfText: { color: '#64748b', fontSize: 12, marginTop: 8 },
  modeRow: { flexDirection: 'row', gap: 10 },
  modeChip: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: '#1e293b',
    borderWidth: 1,
    borderColor: '#334155',
  },
  modeChipActive: { backgroundColor: '#1d4ed8', borderColor: '#3b82f6' },
  modeText: { color: '#94a3b8', fontWeight: '600' },
  modeTextActive: { color: '#fff' },
  prepareRow: {
    marginTop: 12,
    padding: 12,
    borderRadius: 10,
    backgroundColor: '#1e293b',
    borderWidth: 1,
    borderColor: '#334155',
  },
  prepareRowActive: { borderColor: '#2563eb', backgroundColor: '#172554' },
  prepareText: { color: '#cbd5e1', fontSize: 13 },
  templateRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  templateChip: {
    backgroundColor: '#172554',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: '#1e40af',
  },
  templateName: { color: '#93c5fd', fontWeight: '700' },
  templateText: { color: '#bfdbfe', fontSize: 13 },
  logBox: {
    backgroundColor: '#020617',
    borderRadius: 10,
    padding: 12,
    minHeight: 180,
    borderWidth: 1,
    borderColor: '#1e293b',
  },
  traceBox: {
    backgroundColor: '#020617',
    borderRadius: 10,
    padding: 12,
    minHeight: 200,
    borderWidth: 1,
    borderColor: '#1e293b',
    gap: 10,
  },
  stepCard: {
    backgroundColor: '#111827',
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: '#1f2937',
    gap: 6,
  },
  stepHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  stepBadge: { fontWeight: '700', fontSize: 11 },
  stepTitle: { color: '#94a3b8', fontSize: 11, fontWeight: '600' },
  stepMessage: { color: '#e2e8f0', fontSize: 13, lineHeight: 20 },
  traceItem: { gap: 4 },
  traceBadge: { fontWeight: '700', fontSize: 12 },
  traceMessage: { color: '#cbd5e1', fontSize: 12, lineHeight: 18 },
  logPlaceholder: { color: '#64748b', fontSize: 13 },
  logLine: { color: '#cbd5e1', fontSize: 12, marginBottom: 4, fontFamily: 'monospace' },
  historyItem: {
    backgroundColor: '#1e293b',
    borderRadius: 10,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#334155',
  },
  historyTask: { color: '#f8fafc', fontWeight: '600', marginBottom: 4 },
  historyMeta: { color: '#94a3b8', fontSize: 12 },
});
