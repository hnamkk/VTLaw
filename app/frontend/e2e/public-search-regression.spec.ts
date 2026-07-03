import { expect, test } from '@playwright/test';

type PublicDocument = {
  doc_id: string;
  title: string;
  document_number: string | null;
  source_download_url: string | null;
  relations?: Array<{
    relation_id: string;
    counterpart_document_number: string | null;
    counterpart_title: string | null;
  }>;
};

type PublicDocumentResponse = {
  items: PublicDocument[];
  total: number;
};

test('Tra cứu văn bản hiển thị chi tiết, quan hệ và hộp thoại tải file theo dữ liệu public', async ({ page }) => {
  const apiResponse = await page.request.get('/api/v1/documents?page=1&page_size=20');
  expect(apiResponse.status()).toBe(200);
  const body = (await apiResponse.json()) as PublicDocumentResponse;
  expect(body.total).toBeGreaterThan(0);

  const relationDocument = body.items.find((item) => (item.relations?.length ?? 0) > 0);
  const targetDocument = relationDocument ?? body.items[0];
  const searchTerm = targetDocument.document_number || targetDocument.title.slice(0, 32);

  await page.goto('/');
  await page.getByLabel('Tìm kiếm văn bản').fill(searchTerm);
  await page.locator('#view-search').getByRole('button', { name: 'Tra cứu', exact: true }).click();
  await expect(page.locator('#view-search .document-card')).toHaveCount(1, { timeout: 15000 });

  const card = page.locator('#view-search .document-card').first();
  await card.locator('.document-card-main-button').click();
  await expect(card.getByText('Cơ quan ban hành')).toBeVisible();
  await expect(card.getByText('Nguồn gốc')).toBeVisible();

  if (relationDocument) {
    await expect(card.getByText('Quan hệ văn bản')).toBeVisible();
    await expect(card.getByText(`${relationDocument.relations?.length ?? 0} quan hệ đang được công bố`)).toBeVisible();
    const firstRelation = relationDocument.relations?.[0];
    if (firstRelation?.counterpart_document_number) {
      await expect(card.getByText(firstRelation.counterpart_document_number, { exact: false })).toBeVisible();
    }
  }

  if (targetDocument.source_download_url) {
    await card.getByRole('button', { name: 'Tải file nguồn' }).click();
    const dialog = page.getByRole('dialog', { name: 'Lưu ý khi tải file nguồn' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('button', { name: 'Tải file' })).toBeVisible();
    await dialog.getByRole('button', { name: 'Quay lại' }).click();
    await expect(dialog).toBeHidden();
  }

  expect(await page.locator('body').innerText()).not.toContain('Internal Server Error');
});
