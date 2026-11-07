import { expect, test, type Page } from '@playwright/test';

type ListItem = {
  document_id: string;
  relation_count: number;
};

type ListResponse = {
  items: ListItem[];
  total: number;
  page: number;
  page_size: number;
};

declare global {
  interface Window {
    __nativeConfirmCalls?: number;
    __openedReviewRevisionId?: string;
  }
}

async function navigateToView(page: Page, viewId: string) {
  await page.evaluate((targetView) => {
    window.dispatchEvent(new CustomEvent('app:navigate', { detail: targetView }));
  }, viewId);
  await expect(page.locator(`#${viewId}`)).toHaveClass(/active/);
}

async function loginAsAdmin(page: Page) {
  const email = process.env.E2E_ADMIN_EMAIL;
  const password = process.env.E2E_ADMIN_PASSWORD;
  if (!email || !password) {
    throw new Error('Thiếu E2E_ADMIN_EMAIL hoặc E2E_ADMIN_PASSWORD cho E2E quản trị.');
  }

  await page.goto('/');
  await navigateToView(page, 'view-login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Mật khẩu').fill(password);
  await page.locator('#view-login').getByRole('button', { name: 'Đăng nhập' }).click();
  await expect.poll(() => page.evaluate(() => {
    const raw = window.localStorage.getItem('legalai_auth');
    return raw ? JSON.parse(raw)?.user?.role : null;
  })).toBe('ADMIN');
}

async function fetchAdminJson(page: Page, path: string): Promise<{ status: number; body: ListResponse }> {
  return page.evaluate(async (requestPath) => {
    const raw = window.localStorage.getItem('legalai_auth');
    const token = raw ? JSON.parse(raw)?.access_token : null;
    const response = await fetch(requestPath, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    return { status: response.status, body: await response.json() };
  }, path);
}

async function fetchAllPages(page: Page, path: string) {
  const records: ListItem[] = [];
  let currentPage = 1;
  let total = 0;
  do {
    const separator = path.includes('?') ? '&' : '?';
    const result = await fetchAdminJson(page, `${path}${separator}page=${currentPage}&page_size=100`);
    expect(result.status, `${path} trang ${currentPage} phải trả 200`).toBe(200);
    records.push(...result.body.items);
    total = result.body.total;
    currentPage += 1;
  } while (records.length < total);
  return records;
}

async function fetchAllByStatus(page: Page, basePath: string, statuses: string[]) {
  const records = new Map<string, ListItem>();
  for (const status of statuses) {
    const separator = basePath.includes('?') ? '&' : '?';
    const items = await fetchAllPages(page, `${basePath}${separator}publication_status=${status}`);
    for (const item of items) records.set(item.document_id, item);
  }
  return records;
}

test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.__nativeConfirmCalls = 0;
    window.confirm = () => {
      window.__nativeConfirmCalls = (window.__nativeConfirmCalls || 0) + 1;
      return false;
    };
  });
  await loginAsAdmin(page);
});

test('Kho và Duyệt giữ relation_count đồng nhất cho toàn bộ dữ liệu giao nhau', async ({ page }) => {
  const repository = await fetchAllPages(page, '/api/v1/admin/legal-kb/documents');

  const revisions = await fetchAllByStatus(
    page,
    '/api/v1/admin/legal-kb/revisions',
    ['draft', 'published', 'suspended', 'archived'],
  );
  const repositoryByDocument = new Map(repository.map((item) => [item.document_id, item]));
  const sharedIds = [...repositoryByDocument.keys()].filter((documentId) => revisions.has(documentId));

  expect(sharedIds.length, 'Cần có ít nhất một văn bản chung để đối chiếu động').toBeGreaterThan(0);
  for (const documentId of sharedIds) {
    expect(
      revisions.get(documentId)?.relation_count,
      `relation_count không khớp cho document_id=${documentId}`,
    ).toBe(repositoryByDocument.get(documentId)?.relation_count);
  }
});

test('modal lưu dùng xác nhận tùy biến và không gọi window.confirm', async ({ page }) => {
  await navigateToView(page, 'view-hitl');
  await page.getByTestId('review-status-published').click();
  const editButton = page.getByRole('button', { name: 'Chỉnh sửa hồ sơ' }).first();
  await expect(editButton).toBeVisible();
  await editButton.click();

  const editorDialog = page.getByRole('dialog', { name: 'Chỉnh sửa hồ sơ văn bản' });
  await expect(editorDialog).toBeVisible();
  await expect(editorDialog.locator('.skeleton-panel')).toBeHidden({ timeout: 15000 });
  const informationSection = editorDialog.locator('details').filter({ hasText: 'Thông tin văn bản' }).first();
  await expect(informationSection).toBeVisible();
  await informationSection.locator('summary').click();
  const titleField = editorDialog.getByLabel('Tiêu đề văn bản').first();
  await expect(titleField).toBeVisible();
  const originalTitle = await titleField.inputValue();
  const e2eTitle = `${originalTitle} E2E-${Date.now()}`;
  await titleField.fill(e2eTitle);
  await expect(titleField).toHaveValue(e2eTitle);
  const saveButton = editorDialog.getByRole('button', { name: 'Lưu thông tin văn bản' });
  await expect(saveButton).toBeVisible();
  await saveButton.click();
  await expect(page.getByRole('alertdialog', { name: 'Lưu thông tin văn bản?' })).toBeVisible();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Hủy' }).click();
  expect(await page.evaluate(() => window.__nativeConfirmCalls || 0)).toBe(0);
});

test('modal duyệt chỉ hiển thị một lần khi cảnh báo bộ tách trùng với điều kiện chặn', async ({ page }) => {
  await page.route(/\/api\/v1\/admin\/legal-kb\/revisions\/[^/?]+$/, async (route) => {
    const upstream = await route.fetch();
    const body = await upstream.json();
    const duplicateWarning = 'parser emitted a technical warning';
    body.publish_blockers = [duplicateWarning];
    const createdEvent = body.review_events?.find((event: { decision?: string }) => event.decision === 'created');
    if (createdEvent) {
      createdEvent.details = { ...createdEvent.details, parser_warnings: [duplicateWarning] };
    } else {
      body.review_events = [
        ...(body.review_events || []),
        { decision: 'created', details: { parser_warnings: [duplicateWarning] } },
      ];
    }
    await route.fulfill({ response: upstream, json: body });
  });

  await navigateToView(page, 'view-hitl');
  await page.getByTestId('review-status-published').click();
  await page.getByRole('button', { name: 'Chỉnh sửa hồ sơ' }).first().click();

  const editorDialog = page.getByRole('dialog', { name: 'Chỉnh sửa hồ sơ văn bản' });
  await expect(editorDialog.locator('.skeleton-panel')).toBeHidden({ timeout: 15000 });
  await expect(editorDialog.locator('.kb-warning-card')).toHaveCount(1);
  await expect(editorDialog.locator('.kb-warning-card')).toContainText('Hồ sơ có cảnh báo kỹ thuật từ bộ tách nội dung');
});

test('mobile hiển thị đầy đủ category và không tràn ngang', async ({ page }, testInfo) => {
  test.skip(!testInfo.project.name.includes('mobile'), 'Kiểm tra này dành cho viewport mobile.');

  for (const viewId of ['view-kb', 'view-hitl']) {
    await navigateToView(page, viewId);
    await expect(page.locator(`#${viewId} .kb-loading-copy`)).toBeHidden({ timeout: 15000 });
    const selector = viewId === 'view-kb' ? '.kb-status-strip-embedded' : '.review-stat-row';
    const layout = await page.locator(`#${viewId} ${selector}`).evaluate((container) => {
      const viewportWidth = document.documentElement.clientWidth;
      const cards = Array.from(container.querySelectorAll('button')).map((card) => {
        const bounds = card.getBoundingClientRect();
        return { left: bounds.left, right: bounds.right, width: bounds.width };
      });
      return {
        pageOverflow: document.documentElement.scrollWidth > viewportWidth,
        containerOverflow: container.scrollWidth > container.clientWidth + 1,
        cards,
        viewportWidth,
      };
    });

    expect(layout.pageOverflow, `${viewId} không được tràn ngang`).toBe(false);
    expect(layout.containerOverflow, `${viewId} không được cắt category`).toBe(false);
    expect(layout.cards.length).toBeGreaterThan(0);
    for (const card of layout.cards) {
      expect(card.width).toBeGreaterThan(0);
      expect(card.left).toBeGreaterThanOrEqual(0);
      expect(card.right).toBeLessThanOrEqual(layout.viewportWidth + 1);
    }
  }
});

test('submit upload hiển thị tiến trình mà không ghi dữ liệu thật', async ({ page }) => {
  await navigateToView(page, 'view-hitl');
  await page.getByRole('button', { name: 'Thêm văn bản' }).click();

  await page.route('**/api/v1/admin/legal-kb/revisions/upload', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    await route.abort('aborted');
  });
  await page.locator('#legal-kb-file').setInputFiles({
    name: 'e2e-progress-only.docx',
    mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    buffer: Buffer.from('E2E progress fixture; never sent to backend.'),
  });
  await page.locator('#legal-kb-title').fill('Hồ sơ kiểm tra tiến trình E2E');
  await page.locator('#legal-kb-source-url').fill('https://example.invalid/e2e-progress-only');
  await page.locator('#legal-kb-note').fill('Chỉ kiểm tra giao diện tiến trình, không ghi dữ liệu.');
  await page.getByRole('button', { name: 'Tạo hồ sơ', exact: true }).click();

  await expect(page.getByLabel('Tiến trình tạo hồ sơ')).toBeVisible();
  await expect(page.getByText('Tải file', { exact: true }).first()).toBeVisible();
});

test('thay file nguồn cuộn được, khóa đóng khi xử lý và mở đúng revision', async ({ page }) => {
  await page.evaluate(() => {
    window.__openedReviewRevisionId = undefined;
    window.addEventListener('app:open-review-revision', ((event: CustomEvent<string>) => {
      window.__openedReviewRevisionId = event.detail;
    }) as EventListener, { once: true });
  });

  await navigateToView(page, 'view-kb');
  await expect(page.locator('#view-kb .kb-loading-copy')).toBeHidden({ timeout: 15000 });
  const firstRecord = page.locator('#view-kb .kb-record').first();
  await firstRecord.locator('.kb-record-toggle').click();
  await expect(firstRecord.getByRole('button', { name: 'Thay file nguồn' })).toBeVisible();
  await firstRecord.getByRole('button', { name: 'Thay file nguồn' }).click();

  const dialog = page.getByRole('dialog', { name: 'Thay file nguồn' });
  const body = dialog.locator('.replacement-dialog-body');
  const footer = dialog.locator('.replacement-dialog-footer');
  await expect(dialog).toBeVisible();
  await expect.poll(() => body.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
  await body.evaluate((element) => element.scrollTo({ top: element.scrollHeight }));
  await expect(footer).toBeVisible();

  const expectedRevisionId = 'e2e-replacement-revision-id';
  await page.route('**/api/v1/admin/legal-kb/documents/*/replacement-revisions/upload', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1800));
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        document: { document_id: 'e2e-document-id' },
        revision: { revision_id: expectedRevisionId },
        source_asset: {},
        parser_confidence: 1,
        parser_warnings: [],
        canonical_nodes: [],
      }),
    });
  });

  await dialog.locator('#kb-replacement-file').setInputFiles({
    name: 'e2e-replacement.docx',
    mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    buffer: Buffer.from('E2E replacement fixture; never sent to backend.'),
  });
  await dialog.getByText('Tôi xác nhận đây là file mới của đúng văn bản trên.').click();
  await dialog.getByRole('button', { name: 'Tạo hồ sơ thay file' }).click();

  await expect(dialog.getByLabel('Tiến trình tạo hồ sơ thay file')).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Đóng' })).toBeDisabled();
  await expect(dialog.getByRole('button', { name: 'Hủy' })).toBeDisabled();
  await page.locator('.replacement-dialog-backdrop').click({ position: { x: 2, y: 2 } });
  await expect(dialog).toBeVisible();

  await expect.poll(() => page.evaluate(() => window.__openedReviewRevisionId)).toBe(expectedRevisionId);
  await expect(page.locator('#view-hitl')).toHaveClass(/active/);
});
