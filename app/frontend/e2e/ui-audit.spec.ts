import fs from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';

type ViewSpec = {
  viewId: string;
  slug: string;
  expectedHeading: string;
};

type NetworkEntry = {
  url: string;
  status: number | null;
  method?: string;
  errorText?: string;
};

type ViewResult = {
  view_id: string;
  slug: string;
  viewport: string;
  screenshot: string;
  active_view_id: string | null;
  active_nav_labels: string[];
  network: NetworkEntry[];
  issues: string[];
};

const RESULTS_ROOT = process.env.PLAYWRIGHT_RESULTS_ROOT || path.resolve(__dirname, '..', '..');
const PUBLIC_DIR = path.join(RESULTS_ROOT, 'e2e-snapshots-live');
const ADMIN_DIR = path.join(RESULTS_ROOT, 'e2e-admin-snapshots');

const PUBLIC_VIEWS: ViewSpec[] = [
  { viewId: 'view-search', slug: 'search', expectedHeading: 'Tra cứu văn bản' },
  { viewId: 'view-chat', slug: 'chat', expectedHeading: 'Hỏi đáp pháp luật' },
  { viewId: 'view-alert', slug: 'alert', expectedHeading: 'Thông báo pháp luật' },
  { viewId: 'view-bookmarks', slug: 'bookmarks', expectedHeading: 'Đã lưu' },
  { viewId: 'view-login', slug: 'login', expectedHeading: 'Đăng nhập' },
  { viewId: 'view-register', slug: 'register', expectedHeading: 'Đăng ký' },
];

const ADMIN_VIEWS: ViewSpec[] = [
  { viewId: 'view-kb', slug: 'kb', expectedHeading: 'Kho văn bản' },
  { viewId: 'view-hitl', slug: 'hitl', expectedHeading: 'Duyệt văn bản' },
  { viewId: 'view-dashboard', slug: 'dashboard', expectedHeading: 'Chất lượng AI' },
  { viewId: 'view-users', slug: 'users', expectedHeading: 'Người dùng' },
];

const FORBIDDEN_TEXT = [
  'Internal Server Error',
  'Not authenticated',
  'Unauthorized',
  'Admin role required',
  'Choose File',
  'mm/dd',
  'release check',
  'Coverage',
  'Faithfulness',
  'FAILED',
  'golden evaluation',
  'observation',
  'review-only',
  'answerable',
  'parser',
  'blocker',
  'incident',
];

const MOJIBAKE_MARKERS = ['Ã¡', 'Ã¢', 'Ã£', 'Ä‘', 'Æ¡', 'Æ°', 'á»', 'â€', 'ðŸ'];
const PLAIN_VIETNAMESE_MARKERS = ['Hieu luc tu'];

function ensureDir(dirPath: string) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function upsertSummary(filePath: string, items: ViewResult[]) {
  const existing = fs.existsSync(filePath)
    ? JSON.parse(fs.readFileSync(filePath, 'utf-8')) as { items?: ViewResult[] }
    : {};
  const byScreenshot = new Map<string, ViewResult>();
  for (const item of existing.items || []) {
    byScreenshot.set(item.screenshot, item);
  }
  for (const item of items) {
    byScreenshot.set(item.screenshot, item);
  }
  const mergedItems = Array.from(byScreenshot.values()).sort((left, right) =>
    left.screenshot.localeCompare(right.screenshot),
  );
  const failed = mergedItems.filter((item) => item.issues.length > 0).length;
  const summary = {
    generated_at: new Date().toISOString(),
    total: mergedItems.length,
    passed: mergedItems.length - failed,
    failed,
    items: mergedItems,
  };
  fs.writeFileSync(filePath, JSON.stringify(summary, null, 2), 'utf-8');
}

async function navigateToView(page: Page, viewId: string) {
  await page.evaluate((targetView) => {
    window.dispatchEvent(new CustomEvent('app:navigate', { detail: targetView }));
  }, viewId);
  await expect.poll(async () => {
    return page.evaluate(() => document.querySelector('.view-section.active')?.id || null);
  }).toBe(viewId);
}

async function collectSnapshot(page: Page) {
  return page.evaluate(() => {
    const activeSection = document.querySelector('.view-section.active');
    const activeNavLabels = Array.from(document.querySelectorAll('.nav-item.active span'))
      .map((node) => (node.textContent || '').trim())
      .filter(Boolean);
    const text = (document.body?.innerText || '').replace(/\s+/g, ' ').trim();
    const visibleIssueBadges = Array.from(document.querySelectorAll('body *'))
      .filter((node) => {
        if (!(node instanceof HTMLElement)) return false;
        if (node.offsetParent === null) return false;
        const content = (node.textContent || '').trim();
        return content === 'Issues' || /^\d+ Issues?$/.test(content);
      })
      .map((node) => (node.textContent || '').trim());

    return {
      activeViewId: activeSection?.id || null,
      activeNavLabels,
      text,
      hasNextPortal: Boolean(document.querySelector('nextjs-portal')),
      hasNextBadge: Boolean(document.querySelector('[data-next-badge-root], [data-nextjs-toast], [data-next-mark]')),
      visibleIssueBadges,
    };
  });
}

function detectIssues(snapshot: Awaited<ReturnType<typeof collectSnapshot>>, networkEntries: NetworkEntry[], expectedHeading: string) {
  const issues = new Set<string>();
  const lowered = snapshot.text.toLowerCase();

  for (const phrase of FORBIDDEN_TEXT) {
    if (lowered.includes(phrase.toLowerCase())) {
      issues.add(`text_forbidden:${phrase}`);
    }
  }

  for (const marker of MOJIBAKE_MARKERS) {
    if (snapshot.text.includes(marker)) {
      issues.add(`text_mojibake:${marker}`);
    }
  }

  for (const marker of PLAIN_VIETNAMESE_MARKERS) {
    if (lowered.includes(marker.toLowerCase())) {
      issues.add(`text_plain_vietnamese:${marker}`);
    }
  }

  if (snapshot.hasNextBadge) issues.add('overlay:next-badge');
  if (snapshot.hasNextPortal) issues.add('overlay:next-portal');
  if (snapshot.visibleIssueBadges.length > 0) issues.add('overlay:issue-badge');
  if (!snapshot.text.includes(expectedHeading)) issues.add(`missing-heading:${expectedHeading}`);

  for (const entry of networkEntries) {
    if (entry.status === null || entry.status >= 400) {
      issues.add(`network:${entry.status ?? 'failed'}:${entry.url}`);
    }
  }

  return Array.from(issues).sort();
}

async function recordViews(
  page: Page,
  projectName: string,
  outputDir: string,
  views: ViewSpec[],
  networkEntriesRef: { current: NetworkEntry[] },
) {
  ensureDir(outputDir);
  const results: ViewResult[] = [];

  for (const view of views) {
    networkEntriesRef.current = [];
    await navigateToView(page, view.viewId);
    await page.waitForLoadState('networkidle');
    if (view.viewId === 'view-kb' || view.viewId === 'view-hitl') {
      const activeView = page.locator(`#${view.viewId}`);
      await expect(activeView.locator('.kb-loading-copy')).toBeHidden({ timeout: 20000 });
      await expect(activeView.locator('.kb-list-skeleton')).toHaveCount(0, { timeout: 20000 });
    }
    const snapshot = await collectSnapshot(page);
    const screenshotPath = path.join(outputDir, `${projectName}-${view.slug}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true });
    const issues = detectIssues(snapshot, networkEntriesRef.current, view.expectedHeading);
    if (snapshot.activeViewId !== view.viewId) {
      issues.push(`active-view:${snapshot.activeViewId}!=${view.viewId}`);
    }
    results.push({
      view_id: view.viewId,
      slug: view.slug,
      viewport: projectName,
      screenshot: screenshotPath,
      active_view_id: snapshot.activeViewId,
      active_nav_labels: snapshot.activeNavLabels,
      network: [...networkEntriesRef.current],
      issues: Array.from(new Set(issues)).sort(),
    });
  }

  return results;
}

async function loginAsAdmin(page: Page) {
  const email = process.env.E2E_ADMIN_EMAIL;
  const password = process.env.E2E_ADMIN_PASSWORD;
  if (!email || !password) {
    throw new Error('Missing E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD for admin UI audit.');
  }

  await navigateToView(page, 'view-login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Mật khẩu').fill(password);
  await page.locator('#view-login').getByRole('button', { name: 'Đăng nhập' }).click();
  await expect.poll(async () => {
    return page.evaluate(() => {
      try {
        const raw = window.localStorage.getItem('legalai_auth');
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        return parsed?.user?.role || null;
      } catch {
        return null;
      }
    });
  }).toBe('ADMIN');
}

test.describe.configure({ mode: 'serial' });

test('public UI audit', async ({ page }, testInfo) => {
  const networkEntriesRef = { current: [] as NetworkEntry[] };
  page.on('response', (response) => {
    networkEntriesRef.current.push({
      url: response.url(),
      status: response.status(),
      method: response.request().method(),
    });
  });
  page.on('requestfailed', (request) => {
    networkEntriesRef.current.push({
      url: request.url(),
      status: null,
      method: request.method(),
      errorText: request.failure()?.errorText,
    });
  });

  await page.goto('/');
  const results = await recordViews(page, testInfo.project.name, PUBLIC_DIR, PUBLIC_VIEWS, networkEntriesRef);
  upsertSummary(path.join(PUBLIC_DIR, 'ui-audit-results.json'), results);
  const failures = results.filter((item) => item.issues.length > 0);
  expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
});

test('admin UI audit', async ({ page }, testInfo) => {
  const networkEntriesRef = { current: [] as NetworkEntry[] };
  page.on('response', (response) => {
    networkEntriesRef.current.push({
      url: response.url(),
      status: response.status(),
      method: response.request().method(),
    });
  });
  page.on('requestfailed', (request) => {
    networkEntriesRef.current.push({
      url: request.url(),
      status: null,
      method: request.method(),
      errorText: request.failure()?.errorText,
    });
  });

  await page.goto('/');
  await loginAsAdmin(page);
  const results = await recordViews(page, testInfo.project.name, ADMIN_DIR, ADMIN_VIEWS, networkEntriesRef);
  upsertSummary(path.join(ADMIN_DIR, 'admin-ui-audit-results.json'), results);
  const failures = results.filter((item) => item.issues.length > 0);
  expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
});
